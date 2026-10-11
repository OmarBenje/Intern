"""Offline, explainable compatibility against confirmed candidate criteria."""

import calendar
from datetime import date, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from .engine_quality import EUROPE_SCOPE_VERSION, EXTRACTOR_VERSION

MATCHER_VERSION = "rules-2"


def _get(profile, key, default=None):
    return (
        profile.get(key, default)
        if isinstance(profile, dict)
        else getattr(profile, key, default)
    )


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _add_months(start, months):
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    return date(
        year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1])
    )


def evaluate_match(offer, profile, criteria=None):
    """No writes, provider calls or inference from nationality/CV/prose language.

    Criteria represent explicitly saved user choices. Model fields such as an
    available_from date are candidate-supplied; authorization requires confirmed_at.
    Preferences (domain, countries, skills) are not mandatory eligibility rules.
    """
    criteria = criteria or {}
    try:
        enrichment = offer.enrichment
    except (ObjectDoesNotExist, AttributeError):
        enrichment = None
    facts = enrichment.facts if enrichment else {}
    reasons, unknowns = [], []

    def unknown(field, message):
        if field not in unknowns:
            unknowns.append(field)
            reasons.append(
                {
                    "field": field,
                    "status": "unknown",
                    "message": message,
                    "evidence": None,
                }
            )

    def reason(field, status, message, fact=None):
        reasons.append(
            {"field": field, "status": status, "message": message, "evidence": fact}
        )

    def mandatory(field):
        value = facts.get(field)
        if (
            not value
            or not value.get("required")
            or value.get("status") in {"conflict", "ambiguous"}
            or value.get("value") is None
        ):
            return None
        if not value.get("source_revision_id") or not value.get("evidence_text"):
            unknown(field, "Condition non reliée à une preuve source conservée.")
            return None
        return value

    if offer.status != "open":
        reason(
            "status",
            "incompatible",
            "Cette offre n’est pas ouverte.",
            {"value": offer.status},
        )
    if not enrichment:
        unknown("enrichment", "Offre en attente de classification et d’extraction.")
    else:
        if enrichment.classification == "not_internship":
            reason(
                "classification",
                "incompatible",
                "Le poste n’est pas classé comme stage.",
                facts.get("classification"),
            )
        elif enrichment.classification != "confirmed":
            unknown("classification", "Le type de contrat reste à vérifier.")
        if enrichment.europe_status == "unknown":
            unknown(
                "europe_scope",
                "Localisation ou pays autorisés en télétravail à vérifier.",
            )
        elif enrichment.europe_status == "out_of_scope":
            reason(
                "europe_scope",
                "incompatible",
                "Les lieux connus sont hors du périmètre européen.",
                facts.get("country_codes"),
            )

    available_from = _date(
        criteria.get("available_from") or _get(profile, "available_from")
    )
    available_until = _date(
        criteria.get("available_until") or _get(profile, "available_until")
    )
    start_fact = mandatory("start_date")
    start = _date(start_fact["value"]) if start_fact else None
    if available_from or available_until:
        if not start:
            unknown("start_date", "La date de début n’est pas précisée ou prouvée.")
        elif (available_from and start < available_from) or (
            available_until and start > available_until
        ):
            reason(
                "start_date",
                "incompatible",
                "Le début imposé est hors de ta disponibilité.",
                start_fact,
            )
        else:
            reason(
                "start_date",
                "compatible",
                "Le début indiqué respecte ta disponibilité.",
                start_fact,
            )
    elif start:
        unknown("candidate_availability", "Ta disponibilité n’est pas renseignée.")

    duration = mandatory("duration")
    duration_max_months = criteria.get(
        "duration_max_months", _get(profile, "duration_max_months")
    )
    if duration and (duration_max_months is not None or available_until):
        value = duration["value"]
        # Compare like units. Calendar months are not approximated as four weeks.
        minimum, unit = value["minimum"], value["unit"]
        if minimum is None:
            # An upper bound alone cannot prove the minimum length required.
            unknown("duration", "La durée minimale du stage n’est pas précisée.")
            minimum = 0
        mismatch = False
        if duration_max_months is not None:
            if unit == "months":
                mismatch = minimum > duration_max_months
            elif start and isinstance(duration_max_months, int):
                mismatch = start + timedelta(**{unit: minimum}) > _add_months(
                    start, duration_max_months
                )
            else:
                unknown(
                    "duration",
                    "Une date de début est nécessaire pour comparer semaines et mois.",
                )
        if available_until:
            if start:
                earliest_end = (
                    _add_months(start, minimum)
                    if unit == "months"
                    else start + timedelta(**{unit: minimum})
                )
                mismatch |= earliest_end > available_until
            else:
                unknown("duration", "Le début manque pour vérifier la fin du stage.")
        if mismatch:
            reason(
                "duration",
                "incompatible",
                "La durée minimale imposée dépasse ta disponibilité.",
                duration,
            )
        elif "duration" not in unknowns:
            reason(
                "duration",
                "compatible",
                "La durée minimale respecte ta disponibilité.",
                duration,
            )
    elif duration_max_months is not None or available_until:
        unknown("duration", "La durée du stage n’est pas précisée ou prouvée.")

    if facts.get("language_conflicts"):
        unknown(
            "language_conflicts",
            "Les exigences de langue se contredisent dans l’annonce.",
        )
    required_languages = mandatory("required_languages")
    if required_languages:
        languages = criteria.get("languages", _get(profile, "languages"))
        if languages is None:
            unknown("languages", "Tes langues confirmées ne sont pas renseignées.")
        else:
            # A list of codes confirms knowledge, not an advertised proficiency level.
            for item in required_languages["value"]:
                if item["code"] not in languages:
                    unknown(
                        "language_" + item["code"],
                        "Confirme ta maîtrise de la langue exigée : "
                        + item["code"]
                        + ".",
                    )
                else:
                    unknown(
                        "language_level_" + item["code"],
                        "Vérifie le niveau de langue exigé dans l’extrait source.",
                    )

    alternatives = mandatory("language_alternatives")
    if alternatives:
        known_languages = criteria.get("languages", _get(profile, "languages"))
        for group in alternatives["value"]:
            if known_languages is None or not set(group["codes"]).intersection(
                known_languages
            ):
                unknown(
                    "language_alternative",
                    "Confirme au moins une des langues acceptées : "
                    + " / ".join(group["codes"])
                    + ".",
                )
            else:
                unknown(
                    "language_alternative_level",
                    "Vérifie le niveau exigé pour la langue choisie dans l’extrait source.",
                )

    sponsor = mandatory("sponsorship_available")
    needs_sponsorship = criteria.get("needs_sponsorship")
    if (
        needs_sponsorship is None
        and profile
        and not isinstance(profile, dict)
        and enrichment
        and len(enrichment.country_codes) == 1
    ):
        # Only use a confirmation when the role has one unambiguous country.
        authorization = next(
            (
                item
                for item in profile.work_authorizations.all()
                if item.country_code == enrichment.country_codes[0]
                and item.confirmed_at
            ),
            None,
        )
        if authorization:
            needs_sponsorship = authorization.needs_sponsorship
    if needs_sponsorship is True:
        if sponsor and sponsor["value"] is False:
            reason(
                "sponsorship_available",
                "incompatible",
                "L’annonce exclut le sponsoring dont tu as besoin.",
                sponsor,
            )
        elif facts.get("sponsorship_available", {}).get("value") is not True:
            unknown(
                "sponsorship_available", "Le sponsoring nécessaire n’est pas confirmé."
            )
    elif sponsor and sponsor["value"] is False and needs_sponsorship is None:
        unknown("candidate_sponsorship", "Confirme si tu as besoin de sponsoring.")

    if profile is None:
        unknown("profile", "Complète ton profil pour personnaliser la comparaison.")
    incompatible = any(item["status"] == "incompatible" for item in reasons)
    return {
        "compatibility": "incompatible_explicit"
        if incompatible
        else "needs_verification"
        if unknowns
        else "compatible_known",
        "reasons": reasons,
        "unknown_fields": unknowns,
        "versions": {
            "offer": enrichment.content_version if enrichment else 0,
            "profile": _get(profile, "profile_version", 0),
            "search": criteria.get("search_version", 1),
            "matcher": MATCHER_VERSION,
            "extractor": enrichment.extractor_version
            if enrichment
            else EXTRACTOR_VERSION,
            "europe_scope": EUROPE_SCOPE_VERSION,
        },
    }


def preselect_offers(queryset, criteria=None):
    """Indexed/SQL shortlist; unknown inclusion is explicit and does not invent facts."""
    criteria = criteria or {}
    from .job_taxonomy import filter_taxonomy

    queryset = filter_taxonomy(queryset, criteria)
    include_unknown = criteria.get("unknown_policy", "include") == "include"
    missing = Q(enrichment__isnull=True)
    if criteria.get("country_codes"):
        countries = Q(pk__in=[])
        for code in criteria["country_codes"]:
            countries |= Q(enrichment__country_codes__contains=[code])
        if include_unknown:
            countries |= missing | Q(enrichment__country_codes=[])
        queryset = queryset.filter(countries)
    if criteria.get("domain"):
        domain = Q(enrichment__domain=criteria["domain"])
        if include_unknown:
            domain |= missing | Q(enrichment__domain="unclassified")
        queryset = queryset.filter(domain)
    if criteria.get("classification"):
        classification = Q(enrichment__classification=criteria["classification"])
        # Classification selects an explicit review bucket. Missing eligibility
        # facts may be included, but never widen confirmed internships to all jobs.
        queryset = queryset.filter(classification)
    if criteria.get("europe_scope"):
        scope = Q(enrichment__europe_status=criteria["europe_scope"])
        # Geography of the catalogue cannot be relaxed by missing eligibility facts.
        queryset = queryset.filter(scope)
    if criteria.get("q"):
        from .catalogue_search import search_offers

        queryset = search_offers(queryset, criteria["q"])
    for field in ("contract_type", "work_mode"):
        if criteria.get(field):
            condition = Q(**{field: criteria[field]})
            if include_unknown:
                condition |= Q(**{field: "unknown"})
            queryset = queryset.filter(condition)
    return queryset
