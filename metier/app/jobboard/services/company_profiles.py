"""Recover explicit company presentations from existing employer postings offline."""

import re
from types import SimpleNamespace

from django.db import transaction

from jobboard.models import Company, CompanyProfile
from jobboard.services.company_profiles_schema import public_url
from jobboard.services.offer_content import block_texts, build_content, normalized_text


def company_heading(heading, name):
    heading = normalized_text(heading or "").strip(" :?\u202f").casefold()
    name = normalized_text(name).casefold()
    return heading in {
        "about us",
        "who we are",
        "qui sommes-nous",
        "qui sommes nous",
        "à propos de nous",
        "a propos de nous",
        "über uns",
        "companydescription",
        "company description",
        "présentation de l’entreprise",
        "présentation de l'entreprise",
        "about " + name,
        "à propos de " + name,
        "a propos de " + name,
    }


def extract_presentation(description, company_name, payload=None):
    revisions = [SimpleNamespace(pk=1, payload=payload)] if payload else []
    content, _ = build_content(description, revisions)
    blocks = {block["id"]: block for block in content["blocks"]}
    for section in content["sections"]:
        if company_heading(section["original_heading"], company_name) or (
            section["kind"] == "about_company" and section["original_heading"] is None
        ):
            text = "\n\n".join(
                text
                for key in section["block_ids"]
                for text in block_texts(blocks[key])
            ).strip()
            if 80 <= len(text) <= 12000:
                return text
    # Company-specific headings are not all in the shared offer parser vocabulary.
    lines = description.splitlines()
    for index, line in enumerate(lines):
        if not company_heading(line.strip("# *"), company_name):
            continue
        collected = []
        for following in lines[index + 1 :]:
            value = following.strip()
            from jobboard.services.offer_content import section_kind

            if value and (
                section_kind(value.strip("# *")) != "other"
                or re.match(r"^#{1,6} ", value)
            ):
                break
            collected.append(following)
        text = "\n".join(collected).strip()
        # Stop at the first paragraph when an unrecognized role-specific heading follows.
        text = re.split(r"\n\s*\n", text)[0].strip()
        if 80 <= len(text) <= 12000:
            return text
    return None


@transaction.atomic
def enrich_company_from_offer(offer, source, revision=None):
    if not public_url(source.apply_url) or not source.last_checked_at:
        return False
    presentation = extract_presentation(
        offer.description, offer.company.name, revision.payload if revision else None
    )
    if not presentation:
        return False
    Company.objects.select_for_update().get(pk=offer.company_id)
    profile, _ = CompanyProfile.objects.get_or_create(company=offer.company)
    # Never replace an editorial/employer profile or a presentation already available.
    if any(
        entry.get("key") == "presentation"
        for entry in profile.sections
        if isinstance(entry, dict)
    ):
        return False
    profile.sections = [
        *profile.sections,
        {
            "key": "presentation",
            "value": presentation,
            "source_url": source.apply_url,
            "observed_at": source.last_checked_at.isoformat(),
            "source_kind": "job_posting",
            "scope": "Présentation extraite d’une offre de l’entreprise",
            "offer_id": offer.pk,
        },
    ]
    profile.full_clean()
    profile.save(update_fields=["sections", "updated_at"])
    return True
