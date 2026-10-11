"""Bounded public reads. Only links attributed to the matching JobPosting are evidence."""

import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import PublicHTMLParser, fetch_html, plain_text
from jobboard.models import DiscoveryQuery, DiscoveryResult

PROVIDER = "job_link_evidence"


def source_signature(source):
    return hashlib.sha256(
        json.dumps(
            [
                source.origin_url,
                source.apply_url,
                source.content_hash,
                source.offer.title,
                source.offer.company.name,
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def attributed_job(html, title, company):
    from jobboard.services.targeted_merges import normalized

    parser = PublicHTMLParser()
    parser.feed(html)
    pending = list(parser.documents)
    matches = []
    for _ in range(1000):
        if not pending:
            break
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            types = node.get("@type", [])
            if (
                types == "JobPosting"
                or isinstance(types, list)
                and "JobPosting" in types
            ):
                org = node.get("hiringOrganization") or {}
                if (
                    isinstance(org, dict)
                    and normalized(plain_text(node.get("title"))) == normalized(title)
                    and normalized(plain_text(org.get("name"))) == normalized(company)
                ):
                    matches.append(node)
            elif "@graph" in node:
                pending.append(node["@graph"])
    return matches[0] if len(matches) == 1 and not pending else None


def resolve(source, blocked_hosts):
    from jobboard.services.targeted_merges import ATS, job_link

    query, _ = DiscoveryQuery.objects.get_or_create(
        provider=PROVIDER,
        country="",
        language="en",
        domain="all",
        term="public-job-identity",
        defaults={"enabled": False},
    )
    payload = {
        "source_id": source.pk,
        "source_signature": source_signature(source),
        "links": [],
        "references": [],
    }
    status, error = "unresolved", ""
    host = urlsplit(source.origin_url).hostname
    if source.board.provider in ATS:
        payload["links"] = [
            u for u in (source.origin_url, source.apply_url) if job_link(u)
        ]
        payload["references"] = [
            {
                "namespace": source.board.provider + ":" + source.board.board_key,
                "value": source.external_requisition_id or source.external_id,
            }
        ]
        payload["method"] = "stored_ats_identity"
        status = "resolved" if payload["links"] else "unresolved"
    elif host in blocked_hosts:
        status, error = "blocked", "host_blocked_this_run"
    else:
        try:
            final, html = fetch_html(
                source.origin_url, None, deadline=time.monotonic() + 15
            )
            payload["page_sha256"] = hashlib.sha256(html.encode()).hexdigest()
            payload["final_url"] = final
            job = attributed_job(html, source.offer.title, source.offer.company.name)
            if job:
                # Never use arbitrary page anchors: they may belong to recommended jobs.
                for field in ("url", "applicationUrl", "application_url"):
                    value = job.get(field)
                    if isinstance(value, str):
                        link = urljoin(final, value)
                        if job_link(link):
                            payload["links"].append(link)
                identity = job.get("identifier")
                if isinstance(identity, dict) and isinstance(
                    identity.get("value"), (str, int)
                ):
                    payload["references"].append(
                        {
                            "namespace": str(
                                identity.get("name") or source.offer.company.name
                            )[:240],
                            "value": str(identity["value"])[:300],
                        }
                    )
                payload["method"] = "matching_jobposting_jsonld"
                status = "resolved" if payload["links"] else "unresolved"
            else:
                error = "matching_jobposting_not_found"
        except CatalogueImportError as exc:
            status, error = "blocked", exc.code
            blocked_hosts.add(host)
    DiscoveryResult.objects.update_or_create(
        query=query,
        external_id=str(source.pk),
        defaults={
            "source_url": source.origin_url,
            "company_name": source.offer.company.name,
            "payload": payload,
            "attribution": source.origin_url,
            "status": status,
            "error_code": error,
            "last_attempt_at": timezone.now(),
            "last_seen_at": timezone.now(),
        },
    )
    return {
        "source_id": source.pk,
        "offer_id": source.offer_id,
        "status": status,
        "error": error,
        **payload,
    }


def attach_evidence(offers):
    offers = list(offers)
    by_id = {offer.pk: offer for offer in offers}
    sources = {s.pk: s for offer in offers for s in offer.sources.all()}
    for offer in offers:
        offer._resolved_source_links = {}
    for row in DiscoveryResult.objects.filter(
        query__provider=PROVIDER,
        status="resolved",
        external_id__in=[str(pk) for pk in sources],
        last_attempt_at__gte=timezone.now() - timedelta(days=7),
    ):
        source = sources.get(row.payload.get("source_id"))
        if source and row.payload.get("source_signature") == source_signature(source):
            by_id[source.offer_id]._resolved_source_links[source.pk] = row.payload.get(
                "links", []
            )
