"""Language clauses with local modality, source wording and explicit alternatives.

Mentioning a language, country or CEFR level alone does not make it mandatory.
No nationality inference or proficiency equivalence is performed here.
"""

import re

from .stage_details import envelope

LANGUAGE_RULE_VERSION = "languages-2"

LANGUAGES = {
    "en": "english|anglais|englisch(?:kenntnisse)?",
    "fr": "french|français|francais|französisch",
    "de": "german|deutsch(?:kenntnisse)?|allemand",
    "es": "spanish|espagnol|español|spanisch",
    "it": "italian|italien|italiano|italienisch",
    "pt": "portuguese|portugais|português|portugiesisch",
    "nl": "dutch|néerlandais|nederlands|niederländisch",
    "pl": "polish|polonais|polski|polnisch",
    "sv": "swedish|suédois|svenska|schwedisch",
    "da": "danish|danois|dansk|dänisch",
    "no": "norwegian|norvégien|norsk|norwegisch",
    "fi": "finnish|finnois|suomi|finnisch",
    "cs": "czech|tchèque|čeština|tschechisch",
    "el": "greek|grec|grecque|griechisch",
    "ro": "romanian|roumain|română|rumänisch",
    "hu": "hungarian|hongrois|magyar|ungarisch",
    "uk": "ukrainian|ukrainien|українська|ukrainisch",
    "ru": "russian|russe|русский|russisch",
    "ar": "arabic|arabe|arabisch",
    "ja": "japanese|japonais|japanisch",
    "ko": "korean|coréen|koreanisch",
    "zh": "chinese|mandarin|chinois|chinesisch",
    "tr": "turkish|turc|türkisch",
    "he": "hebrew|hébreu|hebräisch",
    "hi": "hindi",
    "ca": "catalan|català|katalanisch",
    "eu": "basque|euskara|baskisch",
    "sk": "slovak|slovaque|slovenčina|slowakisch",
    "bg": "bulgarian|bulgare|български|bulgarisch",
    "hr": "croatian|croate|hrvatski|kroatisch",
}
LANGUAGE = r"\b(?:" + "|".join(LANGUAGES.values()) + r")\b"
REQUIRED = (
    r"\brequired\b|mandatory|\bmust\b|fluent|fluency|proficien|bilingual|bilingue|native speaker|native[- ]level|mother tongue|obligatoire|exig[ée]|courant|couramment|ma[iî]tris|langue maternelle|locuteur natif|erforderlich|fließend|fliessend|verhandlungssicher|muttersprach|(?:very )?good (?:in|command|knowledge)|sehr gute|gute .*kenntnisse|(?:excellent|strong) [\w -]*communication skills|"
    + LANGUAGE
    + r"\s+native\b|\bnative\s+"
    + LANGUAGE
)
PREFERRED = r"preferred|preferably|optional|nice.to.have|(?:a|un) plus\b|souhait|appréci|appreciat|desired|desirable|helpful|advantage|bonus|atout|wünschenswert|von vorteil"
NEGATED = r"not (?:required|mandatory|necessary)|non obligatoire|pas (?:requis|obligatoire|nécessaire)|nicht erforderlich|\bno\b[^,.;]*\brequired\b|\boptional\b|facultati[fv]"
BARE_LIST = (
    r"\s*(?:[-•*]\s*)?"
    + LANGUAGE
    + r"(?:\s+(?:and|or|et|ou|und|oder|&)\s+"
    + LANGUAGE
    + r")*\s*"
)


def languages(text):
    # Source order, not dictionary order, also makes duplicate evidence predictable.
    found = []
    for match in re.finditer(LANGUAGE, text, re.IGNORECASE):
        if re.match(
            r"\s+(?:company|office|market|national(?:ity)?|citizen|cuisine|firm|headquarters)\b",
            text[match.end() :],
            re.IGNORECASE,
        ):
            continue
        if match[0].casefold() == "polish" and re.match(
            r"\s+(?:your|the|our|this|code|skills|work)\b",
            text[match.end() :],
            re.IGNORECASE,
        ):
            continue
        code = next(
            code
            for code, aliases in LANGUAGES.items()
            if re.fullmatch(aliases, match[0], re.IGNORECASE)
        )
        if code not in found:
            found.append(code)
    return found


def modality(text):
    if re.search(NEGATED, text, re.IGNORECASE):
        return "optional"
    if re.search(PREFERRED, text, re.IGNORECASE):
        return "preferred"
    if re.search(REQUIRED, text, re.IGNORECASE):
        return "required"
    return "unknown"


def split_conjunctions(text):
    for match in re.finditer(r"\s+\b(?:and|et|und)\b\s+", text, re.IGNORECASE):
        left, right = text[: match.start()], text[match.end() :]
        # A qualifier shared by 'English and French' belongs to the whole group.
        # Two qualified clauses have their own scope, even in the same sentence.
        if (
            languages(left)
            and languages(right)
            and modality(left) != "unknown"
            and modality(right) != "unknown"
        ):
            return split_conjunctions(left) + split_conjunctions(right)
    return [text]


def clauses(description):
    for sentence in re.split(
        r"[.;!?\n]|\b(?:but|mais|however|aber)\b", description, flags=re.IGNORECASE
    ):
        parts = []
        for match in re.finditer(r"[^,]+", sentence):
            start, end = match.span()
            part = match[0].strip()
            if not languages(part):
                parts.append((start, end))
                continue
            previous = sentence[parts[-1][0] : parts[-1][1]].strip() if parts else ""
            if (
                previous
                and languages(previous)
                and (
                    re.fullmatch(BARE_LIST, previous, re.IGNORECASE)
                    or re.fullmatch(BARE_LIST, part, re.IGNORECASE)
                )
            ):
                parts[-1] = (parts[-1][0], end)
            else:
                parts.append((start, end))
        for start, end in parts:
            yield from split_conjunctions(sentence[start:end].strip())


def language_facts(description, version):
    if re.search(
        r"<(?:p|div|h[1-6]|ul|ol|li|br|section)\b", description, re.IGNORECASE
    ):
        from .offer_content import block_texts, html_blocks

        description = "\n\n".join(
            text for block in html_blocks(description) for text in block_texts(block)
        )
    # Keep paragraph/list boundaries, but undo line wrapping inside source prose.
    description = re.sub(r"\n(?=\s*[-•*]\s)", "\n\n", description)
    description = "\n\n".join(
        " ".join(part.split()) for part in re.split(r"\n\s*\n", description)
    )
    # ATS text often wraps the proficiency qualifier separately from its languages.
    # Join that explicit dependency, rather than treating every newline as a sentence.
    description = re.sub(
        r"((?:fluency|fluent|proficiency|proficient|bilingual|native[- ]level|maîtrise|courant|fließend)(?:\s+(?:in|en|of))?)\s*\n\s*(?="
        + LANGUAGE
        + r")",
        r"\1 ",
        description,
        flags=re.IGNORECASE,
    )
    groups = []
    for clause in clauses(description):
        codes = languages(clause)
        if not codes:
            continue
        mentions = list(re.finditer(LANGUAGE, clause, re.IGNORECASE))
        between_languages = clause[mentions[0].start() : mentions[-1].end()]
        any_of = len(codes) > 1 and bool(
            re.search(r"\b(?:or|ou|oder)\b", between_languages, re.IGNORECASE)
        )
        mixed = (
            any_of
            and len(codes) > 2
            and bool(re.search(r"\b(?:and|et|und)\b", clause, re.IGNORECASE))
        )
        groups.append(
            {
                "codes": codes,
                "modality": "unknown" if mixed else modality(clause),
                "operator": "any" if any_of else "all",
                "level_text": " / ".join(
                    dict.fromkeys(
                        match[0]
                        for match in re.finditer(
                            r"\b[ABC][12]\b|\bnative\b(?:[- ]level)?|mother tongue|fluent|fluency|proficien\w*|bilingual|bilingue|couramment|courant\w*|langue maternelle|locuteur natif|fließend|fliessend|verhandlungssicher|muttersprach\w*",
                            clause,
                            re.IGNORECASE,
                        )
                    )
                )
                or None,
                "evidence_text": clause,
            }
        )
    if not groups:
        return {}

    def evidence(items):
        return " | ".join(dict.fromkeys(item["evidence_text"] for item in items))

    result = {"language_requirements": envelope(groups, evidence(groups), version)}
    # Contradictory explicit clauses stay in the matrix and cannot become mandatory.
    conflicted = {
        code
        for code in {code for group in groups for code in group["codes"]}
        if any(
            code in group["codes"] and group["modality"] == "optional"
            for group in groups
        )
        and any(
            code in group["codes"]
            and group["modality"] == "required"
            and group["operator"] == "all"
            for group in groups
        )
    }
    for field, wanted in [
        ("required_languages", "required"),
        ("preferred_languages", "preferred"),
    ]:
        records = {}
        for group in groups:
            if (
                group["modality"] != wanted
                or wanted == "required"
                and group["operator"] == "any"
            ):
                continue
            for code in group["codes"]:
                if code not in conflicted:
                    records.setdefault(
                        code, {"code": code, "evidence_text": group["evidence_text"]}
                    )
        if records:
            if wanted == "preferred":
                for item in result.get("required_languages", {}).get("value", []):
                    records.pop(item["code"], None)
            values = list(records.values())
            if values:
                result[field] = envelope(
                    values, evidence(values), version, required=wanted == "required"
                )
    alternatives = [
        group
        for group in groups
        if group["modality"] == "required"
        and group["operator"] == "any"
        and not conflicted.intersection(group["codes"])
    ]
    if alternatives:
        result["language_alternatives"] = envelope(
            alternatives, evidence(alternatives), version, required=True
        )
    if conflicted:
        result["language_conflicts"] = envelope(
            sorted(conflicted),
            evidence(
                [group for group in groups if conflicted.intersection(group["codes"])]
            ),
            version,
            status="conflict",
        )
    for fact in result.values():
        fact["language_rule_version"] = LANGUAGE_RULE_VERSION
    return result
