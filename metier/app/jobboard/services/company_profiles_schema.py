"""Bounded, sourced public fields. Text stays text, including employer markup."""

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime

FACT_LABELS = {
    "industry": "Secteur",
    "size": "Effectif",
    "headquarters": "Siège social",
    "founded": "Année de création",
    "stage": "Type d’entreprise",
    "funding": "Financement",
    "investors": "Investisseurs",
    "revenue": "Chiffre d’affaires",
    "leadership": "Direction",
    "international_presence": "Présence internationale",
    "average_age": "Âge moyen",
    "gender_balance": "Parité",
}
SECTION_LABELS = {
    "presentation": "Présentation",
    "culture": "Culture et valeurs",
    "benefits": "Avantages et conditions de travail",
    "recruitment": "Processus de recrutement",
    "early_careers": "Stages et jeunes talents",
    "technology": "Technologies et métiers",
    "commitments": "Engagements et RSE",
    "news": "Actualités",
    "media": "Photos, vidéos et témoignages",
}


def public_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme in {"http", "https"}
            and url.hostname
            and not url.username
            and not url.password
        ):
            return value
    except ValueError:
        pass
    return None


def validate_entries(entries, labels):
    if not isinstance(entries, list) or len(entries) > 80:
        raise ValidationError("Use a list of at most 80 sourced entries.")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {
            "key",
            "value",
            "source_url",
            "observed_at",
            "source_kind",
            "scope",
            "offer_id",
        }:
            raise ValidationError("Invalid public company entry.")
        if entry.get("key") not in labels:
            raise ValidationError("Unknown company information key.")
        value = entry.get("value")
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
            raise ValidationError("Provide a text value of at most 12000 characters.")
        if not public_url(entry.get("source_url")):
            raise ValidationError(
                "Provide a public HTTP(S) source URL without credentials."
            )
        try:
            observed = parse_datetime(entry.get("observed_at", ""))
        except (ValueError, TypeError):
            observed = None
        if not observed or observed.tzinfo is None:
            raise ValidationError("Provide an observation timestamp with a timezone.")
        if entry.get("source_kind") not in {"employer", "job_posting", "editorial"}:
            raise ValidationError(
                "Specify employer, job_posting or editorial source_kind."
            )
        scope = entry.get("scope", "")
        if not isinstance(scope, str) or len(scope) > 300:
            raise ValidationError("Scope must be text of at most 300 characters.")
        if "offer_id" in entry and (
            type(entry["offer_id"]) is not int or entry["offer_id"] < 1
        ):
            raise ValidationError("Invalid offer reference.")


def validate_facts(entries):
    validate_entries(entries, FACT_LABELS)


def validate_sections(entries):
    validate_entries(entries, SECTION_LABELS)


def publish_entries(entries, labels):
    """Fail closed for malformed data written outside validated admin/import paths."""
    if not isinstance(entries, list):
        return []
    result = []
    for entry in entries[:80]:
        try:
            validate_entries([entry], labels)
        except ValidationError:
            continue
        result.append({**entry, "label": labels[entry["key"]]})
    return result
