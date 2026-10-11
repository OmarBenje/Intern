"""Bounded public HTML reads with DNS validation and pinned TLS connections."""

import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .greenhouse_catalogue import CatalogueImportError

MAX_BYTES = 2 * 1024 * 1024


def validate_url(url, allowed_hosts):
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme == "https"
            and parts.hostname in allowed_hosts
            and not parts.username
            and not parts.password
            and parts.port in (None, 443)
            and not parts.fragment
            and len(url) <= 2048
            and not any(ord(c) < 33 for c in url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise CatalogueImportError("unsafe_public_url")
    return parts


def resolve_public(host):
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(row[4][0]).is_global for row in addresses
        ):
            raise CatalogueImportError("non_public_address")
        return addresses[0]
    except (socket.gaierror, ValueError) as exc:
        raise CatalogueImportError("dns_failed") from exc


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        family, kind, proto, _, sockaddr = self.address
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(self.timeout)
            sock.connect(sockaddr)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def fetch_public(url, allowed_hosts=None, deadline=None, *, image=False):
    deadline = deadline or time.monotonic() + 25
    for hop in range(4):
        parts = validate_url(
            url,
            allowed_hosts if allowed_hosts is not None else {urlsplit(url).hostname},
        )
        address = resolve_public(parts.hostname)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CatalogueImportError("fetch_budget_exceeded")
        conn = PinnedHTTPSConnection(parts.hostname, address, min(8, remaining))
        expired = threading.Event()

        def expire_connection(connection=conn, timeout_event=expired):
            # A per-read socket timeout permits indefinitely slow HTTP headers.
            # Interrupt the live socket at the absolute request deadline too.
            timeout_event.set()
            if connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        watchdog = threading.Timer(remaining, expire_connection)
        watchdog.daemon = True
        watchdog.start()
        try:
            target = parts.path or "/"
            if parts.query:
                target += "?" + parts.query
            conn.request(
                "GET",
                target,
                headers={
                    "User-Agent": "InternCatalogue/1.0",
                    "Accept": "image/*" if image else "text/html",
                    "Accept-Encoding": "identity",
                },
            )
            response = conn.getresponse()
            if expired.is_set() or time.monotonic() >= deadline:
                raise CatalogueImportError("fetch_budget_exceeded")
            if response.status in (301, 302, 303, 307, 308):
                if hop == 3 or not response.getheader("Location"):
                    raise CatalogueImportError("redirect_limit")
                url = urljoin(url, response.getheader("Location"))
                continue
            if response.status != 200:
                raise CatalogueImportError("public_http_error")
            content_type = response.getheader("Content-Type", "").lower().split(";")[0]
            if image:
                if content_type not in {
                    "image/png",
                    "image/jpeg",
                    "image/webp",
                    "image/gif",
                    "image/x-icon",
                    "image/vnd.microsoft.icon",
                    "application/octet-stream",
                }:
                    raise CatalogueImportError("unsupported_logo_type")
            elif "text/html" not in content_type:
                raise CatalogueImportError("not_html")
            if response.getheader("Content-Encoding", "identity") not in (
                "",
                "identity",
            ):
                raise CatalogueImportError("unsupported_encoding")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CatalogueImportError("fetch_budget_exceeded")
                if conn.sock:
                    conn.sock.settimeout(min(8, remaining))
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                size += len(chunk)
                if size > MAX_BYTES:
                    raise CatalogueImportError("html_too_large")
                if not chunk:
                    data = b"".join(chunks)
                    return url, data if image else data.decode(
                        "utf-8", errors="replace"
                    )
                chunks.append(chunk)
        except (OSError, http.client.HTTPException) as exc:
            raise CatalogueImportError(
                "fetch_budget_exceeded" if expired.is_set() else "public_fetch_failed"
            ) from exc
        finally:
            watchdog.cancel()
            conn.close()
    raise CatalogueImportError("redirect_limit")


def fetch_html(url, allowed_hosts, deadline=None):
    return fetch_public(url, allowed_hosts, deadline)


class PublicHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.documents, self.text = [], [], []
        self.script = None
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in ("script", "style"):
            self.hidden += 1
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.script = []

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            try:
                self.documents.append(json.loads("".join(self.script)))
            except (ValueError, RecursionError):
                pass
            self.script = None
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if not self.hidden:
            self.text.append(data)


def plain_text(value):
    parser = PublicHTMLParser()
    parser.feed(value if isinstance(value, str) else "")
    return " ".join(" ".join(parser.text).split())


def parse_job_postings(html):
    parser = PublicHTMLParser()
    parser.feed(html)
    pending = list(parser.documents)
    result = []
    for _ in range(1000):
        if not pending:
            break
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            kind = value.get("@type", [])
            if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
                company = value.get("hiringOrganization", {})
                result.append(
                    {
                        "title": plain_text(value.get("title"))[:300],
                        "company_name": plain_text(company.get("name"))[:240]
                        if isinstance(company, dict)
                        else "",
                        "description": plain_text(value.get("description")),
                    }
                )
            elif "@graph" in value:
                pending.append(value["@graph"])
    if pending:
        raise CatalogueImportError("job_posting_graph_too_large")
    return result
