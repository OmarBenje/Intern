"""Conservative temporal facts with precision, modality and literal evidence."""

import re
from datetime import date, datetime

MONTHS = {
    1: "january|janvier|januar",
    2: "february|février|fevrier|februar",
    3: "march|mars|märz|maerz",
    4: "april|avril",
    5: "may|mai",
    6: "june|juin|juni",
    7: "july|juillet|juli",
    8: "august|août|aout",
    9: "september|septembre",
    10: "october|octobre|oktober",
    11: "november|novembre",
    12: "december|décembre|decembre|dezember",
}
MONTH_PATTERN = "(?:" + "|".join(MONTHS.values()) + ")"
DATE_PATTERN = (
    r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|"
    + rf"\d{{1,2}}(?:st|nd|rd|th|er)?\s+{MONTH_PATTERN}\s+\d{{4}}|"
    + rf"{MONTH_PATTERN}\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+\d{{4}}|"
    + rf"{MONTH_PATTERN}\s+\d{{4}}|"
    + r"(?:summer|spring|autumn|fall|winter|été|ete|printemps|automne|hiver|sommer|wintersemester)\s+\d{4}"
)
START = r"(?:start(?:ing)?(?:\s+date)?|début(?: du stage)?|beginn|inizio|(?:à partir|a partir) d(?:e|['’])|commencing)\s*(?:(?:is|on|in|from|le|en|:|-)\s*)?"
PREFERRED = r"preferred|ideally|optional|souhait|idéal|appréci|preferibil|wünschenswert|idealerweise"
FLEXIBLE = PREFERRED + r"|flexible|negotiable|indicatif|not required"
UNITS = r"months?|mois|monate?n?|maanden?|miesiące|miesięcy|mes(?:es)?|mesi|weeks?|semaines?|wochen|settimane|semanas|days?|jours?|tage"
NUMBER_WORDS = {
    "three": "3",
    "four": "4",
    "six": "6",
    "ten": "10",
    "twelve": "12",
    "trois": "3",
    "quatre": "4",
}
NUMBER = r"(?:\d{1,3}|three|four|six|ten|twelve|trois|quatre)"


def envelope(value, evidence, version, *, required=False, status="explicit", path=None):
    return {
        "value": value,
        "evidence_text": evidence,
        "json_path": path,
        "method": "structured" if path else "rule",
        "extractor_version": version,
        "required": required,
        "status": status,
        "source_revision_id": None,
    }


def parse_date(value):
    text = value.strip().casefold()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return {"precision": "day", "value": date.fromisoformat(text).isoformat()}
        except ValueError:
            return None
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        return {"precision": "ambiguous", "value": value}
    month = next(
        (
            number
            for number, names in MONTHS.items()
            if re.search(r"\b(?:" + names + r")\b", text)
        ),
        None,
    )
    year = re.search(r"\b(20\d{2})\b", text)
    if not year:
        return None
    if month:
        remaining = re.sub(MONTH_PATTERN, "", text)
        remaining = remaining.replace(year[1], "")
        day = re.search(r"\d{1,2}", remaining)
        if day:
            try:
                return {
                    "precision": "day",
                    "value": date(int(year[1]), month, int(day[0])).isoformat(),
                }
            except ValueError:
                return None
        return {"precision": "month", "value": f"{year[1]}-{month:02d}"}
    season = re.search(
        r"summer|spring|autumn|fall|winter|été|ete|printemps|automne|hiver|sommer", text
    )
    if season:
        return {"precision": "season", "value": season[0], "year": int(year[1])}
    return None


def sentence_context(text, position):
    # Do not split inside German dates, abbreviations or decimals.
    boundaries = [m.end() for m in re.finditer(r"[.!?](?:\s+|$)|\n", text)]
    start = max((p for p in boundaries if p <= position), default=0)
    end = min((p for p in boundaries if p > position), default=len(text))
    return text[start:end]


def conflict(candidates, version):
    return envelope(
        None,
        " | ".join(dict.fromkeys(item["evidence_text"] for item in candidates)),
        version,
        status="conflict",
    )


def duration_facts(text, version):
    candidates, preferences = [], []
    pattern = re.compile(
        rf"\b(?P<minimum>{NUMBER})(?:\s*(?:-|–|to|à|bis|a)\s*(?P<maximum>{NUMBER}))?\s*[- ]?\s*(?P<unit>{UNITS})\b",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    for match in matches:
        context = sentence_context(text, match.start())
        before = text[max(0, match.start() - 65) : match.start()]
        after = text[match.end() : match.end() + 60]
        # A recurring quantity is attendance/workload, never elapsed duration.
        # Check beside this quantity so a real duration elsewhere in the same
        # sentence ("6 months, 2 days per week") remains available.
        if re.match(
            r"\s*(?:(?:on[- ]?site|in (?:the )?office|sur site|en présentiel|"
            r"de présence|au bureau|vor Ort|im Büro)\s+)?"
            r"(?:per|a|each|every|par|chaque|pro|por|alla|a la|à la|/)\s*"
            r"(?:weeks?|months?|years?|semaines?|mois|ans?|années?|"
            r"Woche[n]?|Monat[e]?|Jahr[e]?|semanas?|mes(?:es)?|"
            r"settimane?|mese|mesi)\b",
            after,
            re.IGNORECASE,
        ):
            continue
        # Internship-specific cue, or explicit bounded-duration phrasing in an
        # internship description. Experience/technology history is never duration.
        if re.match(
            r"\s*(?:of )?(?:experience|expérience|erfahrung|of (?:python|java|react))\b",
            after,
            re.IGNORECASE,
        ):
            continue
        relevant = re.search(
            r"duration|durée|dauer|duración|durata|duração|duur|czas trwania|internship|stage|praktikum|minimum|at least|au moins|ideally|idéalement|maximum|at most",
            context,
            re.IGNORECASE,
        )
        if not relevant:
            continue
        def number(value):
            return int(NUMBER_WORDS.get(value.casefold(), value))

        minimum = number(match["minimum"])
        maximum = number(match["maximum"]) if match["maximum"] else minimum
        if not 0 < minimum <= maximum <= 3650:
            continue
        unit = (
            "weeks"
            if re.match(
                r"week|semaine|wochen|settimane|semana", match["unit"], re.IGNORECASE
            )
            else "days"
            if re.match(r"day|jour|tage", match["unit"], re.IGNORECASE)
            else "months"
        )
        # Only adjacent modifiers apply: 'minimum 3, ideally 6' is not all preferred.
        prefix = re.split(r"[,;.]", before)[-1]
        if re.search(r"extension|prolongation|verlängerung", prefix, re.IGNORECASE):
            continue
        preferred = bool(
            re.search(
                r"(?:" + PREFERRED + r")(?:\s+(?:duration|length|durée|dauer))?[\s:]*$",
                prefix,
                re.IGNORECASE,
            )
            or re.match(
                r"\s*(?:preferred|souhaités?|idéalement)\b", after, re.IGNORECASE
            )
        )
        lower_only = bool(
            re.search(
                r"(?:minimum(?: of)?|at least|au moins|mindestens)\s*$",
                prefix,
                re.IGNORECASE,
            )
            or re.match(r"\s*(?:minimum|at least)\b", after, re.IGNORECASE)
        )
        upper_only = bool(
            re.search(
                r"(?:maximum(?: of)?|at most|au plus|up to|höchstens)\s*$",
                prefix,
                re.IGNORECASE,
            )
        )
        evidence_start = (
            match.start() - len(prefix)
            if lower_only or upper_only or preferred
            else match.start()
        )
        trailing_modifier = re.match(
            r"\s*(?:preferred|souhaités?|minimum)\b", after, re.IGNORECASE
        )
        evidence = text[
            evidence_start : match.end()
            + (trailing_modifier.end() if trailing_modifier else 0)
        ].strip()
        value = {
            "minimum": None if upper_only else minimum,
            "maximum": None if lower_only and not match["maximum"] else maximum,
            "unit": unit,
            "original_unit": match["unit"],
        }
        item = envelope(value, evidence, version, required=not preferred)
        (preferences if preferred else candidates).append(item)
    result = {}
    for field, items in [("duration", candidates), ("preferred_duration", preferences)]:
        unique = {
            str(
                {key: item["value"][key] for key in ("minimum", "maximum", "unit")}
            ): item
            for item in items
        }
        if len(unique) == 1:
            result[field] = next(iter(unique.values()))
        elif len(unique) > 1:
            units = {item["value"]["unit"] for item in items}
            lower = max((item["value"]["minimum"] or 0 for item in items), default=0)
            upper = min(
                (
                    item["value"]["maximum"]
                    for item in items
                    if item["value"]["maximum"] is not None
                ),
                default=None,
            )
            if (
                field == "duration"
                and len(units) == 1
                and (upper is None or lower <= upper)
            ):
                value = {
                    **items[0]["value"],
                    "minimum": lower or None,
                    "maximum": upper,
                }
                result[field] = envelope(
                    value,
                    " | ".join(item["evidence_text"] for item in items),
                    version,
                    required=True,
                )
            else:
                result[field] = conflict(items, version)
    if "duration" not in result and "preferred_duration" in result:
        result["duration"] = result["preferred_duration"]
    return result


def temporal_facts(text, version):
    result = duration_facts(text, version)
    starts = []
    period_spans = []
    for match in re.finditer(
        START
        + rf"(?P<first>{MONTH_PATTERN})(?:\s+(?P<first_year>20\d{{2}}))?\s*(?:à|to|bis|–|-)\s*(?P<last>{MONTH_PATTERN})\s+(?P<year>20\d{{2}})\b",
        text,
        re.IGNORECASE,
    ):
        first = parse_date(
            match["first"] + " " + (match["first_year"] or match["year"])
        )
        last = parse_date(match["last"] + " " + match["year"])
        if first and last and first["value"] <= last["value"]:
            parsed = {
                "precision": "month_range",
                "earliest": first["value"],
                "latest": last["value"],
            }
            starts.append(envelope(parsed, match[0], version))
            period_spans.append(match.span())
    for match in re.finditer(
        START + rf"(?P<date>{DATE_PATTERN})\b", text, re.IGNORECASE
    ):
        if any(start <= match.start() < end for start, end in period_spans):
            continue
        parsed = parse_date(match["date"])
        if not parsed:
            continue
        parsed["relation"] = (
            "from"
            if re.search(r"from|à partir|a partir", match[0], re.IGNORECASE)
            else "at"
        )
        required = not bool(
            re.search(FLEXIBLE, sentence_context(text, match.start()), re.IGNORECASE)
        )
        starts.append(
            envelope(
                parsed,
                match[0],
                version,
                required=required,
                status="ambiguous"
                if parsed["precision"] == "ambiguous"
                else "explicit",
            )
        )
    # Only ranges in a stage/program sentence, never application windows. Both
    # years must be present; no guessed year or month-length conversion.
    for match in re.finditer(
        rf"(?:du|from)\s+(?P<first>{DATE_PATTERN})\s+(?:au|to|until|–|-)\s+(?P<last>{DATE_PATTERN})\b",
        text,
        re.IGNORECASE,
    ):
        context = sentence_context(text, match.start())
        if not re.search(
            r"internship|stage|praktikum|program", context, re.IGNORECASE
        ) or re.search(
            r"application|candidature|deadline|bewerbung", context, re.IGNORECASE
        ):
            continue
        first, last = parse_date(match["first"]), parse_date(match["last"])
        if (
            first
            and last
            and first["precision"] == last["precision"] == "day"
            and first["value"] < last["value"]
        ):
            starts.append(
                envelope({**first, "relation": "at"}, match[0], version, required=True)
            )
            result["end_date"] = envelope(last, match[0], version)
            if "duration" not in result:
                days = (
                    date.fromisoformat(last["value"])
                    - date.fromisoformat(first["value"])
                ).days
                result["duration"] = envelope(
                    {
                        "minimum": days,
                        "maximum": days,
                        "unit": "days",
                        "original_unit": "date_range",
                    },
                    match[0],
                    version,
                    required=True,
                )
    if not starts:
        for match in re.finditer(
            r"(?:summer|spring|autumn|fall|winter|été|printemps|automne|hiver|sommer)\s+20\d{2}",
            text,
            re.IGNORECASE,
        ):
            if re.search(
                r"intern|stage|praktik",
                text[max(0, match.start() - 35) : match.end() + 35],
                re.IGNORECASE,
            ):
                starts.append(envelope(parse_date(match[0]), match[0], version))
                break
    if not starts and (
        match := re.search(
            START + r"(?:asap|immediately|dès que possible|dès maintenant|sofort)\b",
            text,
            re.IGNORECASE,
        )
    ):
        starts.append(
            envelope({"precision": "immediate", "value": None}, match[0], version)
        )
    unique = {str(item["value"]): item for item in starts}
    if len(unique) == 1:
        item = next(iter(unique.values()))
        if (
            item["value"]["precision"] == "day"
            and item["value"].get("relation") == "at"
        ):
            result["start_date"] = {**item, "value": item["value"]["value"]}
        else:
            result["start_period"] = item
    elif len(unique) > 1:
        result["start_period"] = conflict(starts, version)
    for field, marker in [
        (
            "application_deadline",
            r"application deadline|applications? (?:close|closing)|deadline|date limite(?: de candidature)?|postuler avant|bewerbungsfrist",
        ),
        ("end_date", r"end date|ending|fin du stage"),
    ]:
        found = []
        for match in re.finditer(
            rf"(?:{marker})\s*[:\-]?\s*(?P<date>{DATE_PATTERN})\b", text, re.IGNORECASE
        ):
            parsed = parse_date(match["date"])
            if parsed:
                trailing = re.match(
                    r"\s*(?:at|à|@)\s*\d{1,2}[:h]\d{2}(?:\s*(?:am|pm))?(?:\s*(?:ET|PT|UTC|GMT|CET|CEST))?",
                    text[match.end() :],
                    re.IGNORECASE,
                )
                if trailing:
                    parsed["time_text"] = trailing[0].strip()
                found.append(
                    envelope(
                        parsed, match[0] + (trailing[0] if trailing else ""), version
                    )
                )
        if found:
            result[field] = (
                found[0]
                if len({str(item["value"]) for item in found}) == 1
                else conflict(found, version)
            )
    return result


def structured_facts(payload, version):
    result = {}
    for key, field in [
        ("application_deadline", "application_deadline"),
        ("first_published", "publication_date"),
        ("publishedAt", "publication_date"),
        ("datePosted", "publication_date"),
        ("jobStartDate", "start_date"),
    ]:
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        try:
            parsed = (
                datetime.fromisoformat(value)
                if "T" in value
                else date.fromisoformat(value)
            )
        except ValueError:
            continue
        if field == "start_date" and isinstance(parsed, datetime):
            continue
        result[field] = envelope(
            parsed.isoformat(), value, version, path=key, required=field == "start_date"
        )
    if payload.get("jobImmediateStart") is True:
        result["start_period"] = envelope(
            {"precision": "immediate", "value": None},
            "jobImmediateStart: true",
            version,
            path="jobImmediateStart",
        )
    value = payload.get("jobDuration")
    if (
        isinstance(value, str)
        and (match := re.fullmatch(r"P(\d{1,3})([MWD])", value))
        and int(match[1]) > 0
    ):
        unit = {"M": "months", "W": "weeks", "D": "days"}[match[2]]
        result["duration"] = envelope(
            {
                "minimum": int(match[1]),
                "maximum": int(match[1]),
                "unit": unit,
                "original_unit": match[2],
            },
            value,
            version,
            required=True,
            path="jobDuration",
        )
    return result


def merge_structured(facts, incoming, version):
    def comparable(value):
        return (
            {key: item for key, item in value.items() if key != "original_unit"}
            if isinstance(value, dict)
            else value
        )

    for field, item in incoming.items():
        previous = facts.get(field)
        if previous and comparable(previous["value"]) != comparable(item["value"]):
            # Presentation-only date objects may agree with the exact ATS datetime.
            value = previous["value"]
            if (
                isinstance(value, dict)
                and value.get("value") == str(item["value"])[:10]
                and not value.get("time_text")
            ):
                facts[field] = item
            else:
                facts[field] = conflict([previous, item], version)
        elif field == "start_date" and "start_period" in facts:
            period = facts["start_period"]["value"]
            if (
                isinstance(period, dict)
                and period.get("precision") == "month"
                and str(item["value"]).startswith(period["value"])
            ):
                facts[field] = item
            else:
                facts["start_period"] = conflict([facts["start_period"], item], version)
        else:
            facts[field] = item
