"""Public Teamtailor RSS. Preserve every location; never infer feed completeness."""

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from .greenhouse_catalogue import CatalogueImportError
from .personio_catalogue import html_text, read_xml, xml_root
from .public_catalogue import CatalogueSnapshot, _posting

NS = {"tt": "https://teamtailor.com/locations"}


def tenant(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value
    ):
        raise CatalogueImportError("invalid_board_key")
    return value


def normalize_teamtailor(payload):
    root = xml_root(payload, "rss")
    channel = root.find("channel")
    if channel is None or len(channel.findall("item")) > 20000:
        raise CatalogueImportError("invalid_snapshot")
    rows, errors, seen = [], [], set()
    for item in channel.findall("item"):
        url = item.findtext("link", "").strip()
        identity = re.fullmatch(r"/jobs/([0-9]+)(?:-[^/]*)?/?", urlsplit(url).path)
        if not identity or identity[1] in seen:
            raise CatalogueImportError("invalid_job_identity")
        identity = identity[1]
        seen.add(identity)
        try:
            details = []
            for loc in item.findall("tt:locations/tt:location", NS):
                country = loc.findtext("tt:country", "", NS).strip()
                city = loc.findtext("tt:city", "", NS).strip()
                label = ", ".join(x for x in (city, country) if x)
                label = label or loc.findtext("tt:name", "", NS).strip()
                if len(country) > 240:
                    raise CatalogueImportError("invalid_location")
                if label:
                    details.append({"name": label, "country": country})
            raw = {"rss_item": ET.tostring(item, encoding="unicode")}
            description = html_text(item.findtext("description", ""))
            if len(description.strip()) < 40:
                raise CatalogueImportError("missing_description")
            row = _posting(
                raw,
                identity,
                item.findtext("title"),
                description,
                url,
                url,
                [x["name"] for x in details],
            )
            row["location_details"] = details
            row["work_mode"] = {
                "fully": "remote",
                "hybrid": "hybrid",
                "none": "onsite",
            }.get(item.findtext("remoteStatus", ""), "unknown")
            rows.append(row)
        except CatalogueImportError as exc:
            errors.append({"external_id": identity, "code": exc.code})
    # RSS has no trustworthy total/cursor. Absence cannot close existing offers.
    return CatalogueSnapshot(rows, complete=False, errors=errors)


def fetch_teamtailor(key):
    return normalize_teamtailor(
        read_xml(f"https://{tenant(key)}.teamtailor.com/jobs.rss")
    )
