"""Narrow fallback for an explicit role-specific list behind a generic Lever place."""

import re

# Country names absent from the core multilingual aliases. No city geocoding.
ADDITIONAL_COUNTRIES = {
    "estonia": "EE",
    "latvia": "LV",
    "lithuania": "LT",
    "slovakia": "SK",
    "ukraine": "UA",
    "hungary": "HU",
    "bulgaria": "BG",
    "moldova": "MD",
    "kosovo": "XK",
    "serbia": "RS",
    "north macedonia": "MK",
    "armenia": "AM",
    "georgia": "GE",
    "uzbekistan": "UZ",
    "croatia": "HR",
    "united states of america": "US",
    "bosnia and herzegovina": "BA",
}


def explicit_role_locations(description, locations):
    from jobboard.services.engine_quality import COUNTRY_ALIASES

    if len(locations) != 1 or not re.fullmatch(
        r"All [\w &.-]{1,100} locations", locations[0], re.IGNORECASE
    ):
        return None
    pattern = (
        r"^This (?:position|role) is open across "
        + re.escape(locations[0])
        + r": ([^\n.!?]{1,1000})\.?[ \t]*$"
    )
    matches = list(re.finditer(pattern, description, re.IGNORECASE | re.MULTILINE))
    if len(matches) != 1:
        return None
    aliases = {name: code for code, names in COUNTRY_ALIASES.items() for name in names}
    aliases.update(ADDITIONAL_COUNTRIES)
    names = [name.strip() for name in matches[0][1].split(",")]
    # Keep compound country names intact; only split a final conjunction if needed.
    if names[-1].casefold() not in aliases:
        names[-1:] = re.split(r"\s+and\s+", names[-1], flags=re.IGNORECASE)
    details = []
    for name in names:
        code = aliases.get(name.casefold())
        if not code:
            return None
        place = {"name": name, "country": code}
        if place not in details:
            details.append(place)
    return {"details": details, "evidence": matches[0][0]}
