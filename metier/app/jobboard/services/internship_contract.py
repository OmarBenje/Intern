"""Corroborate ATS contract labels and surface literal conflicting evidence."""

import re

# Evidence must describe this placement, not a past experience or generic benefit.
PLACEMENT = re.compile(
    r"\b(?:(?:ce|le|votre|du|un|une|de)\s+stage\b|stage\s+(?:de\s+)?(?:fin d.[ée]tudes|\d{1,2}\s*mois)"
    r"|(?:this|the|an?|paid|extracurricular)\s+internship\b"
    r"|(?:bieten|absolvieren)[^.]{0,65}\bPraktikum\b"
    r"|(?:im|ein|das|dein)\s+Praktikum\b"
    r"|convenio\s+de\s+prácticas\b|tirocinio\s+(?:curriculare|extracurriculare)\b"
    r"|contrat\s*:\s*stage\b|Vertragsart\s*:\s*Praktikum\b|trainee lawyer\b)",
    re.IGNORECASE,
)
PRIOR = re.compile(
    r"\b(?:previous|prior|past|premi[èe]re|pr[ée]c[ée]dente|exp[ée]rience|erfahrung|effectu[ée]|completed|absolviert)\b",
    re.IGNORECASE,
)
CONTRACT = re.compile(
    r"\b(?:CDI|CDD|contrat\s+[àa]\s+dur[ée]e\s+ind[ée]termin[ée]e"
    r"|contract\s+van\s+onbepaalde\s+duur"
    r"|permanent\s+(?:employment|contract|position|role)"
    r"|unbefristete[snrm]?\s+(?:Arbeitsvertrag|Anstellung|Stelle))\b",
    re.IGNORECASE,
)
FUTURE = re.compile(
    r"\b(?:possibilit[ée]s?|possibles?|perspectives?|[ée]volutions?|d[ée]boucher|d[ée]bouchant"
    r"|apr[èe]s|issue|suite|after|following|potential|conversion|option|opportunit[ée]s?|opportunity|offer afterwards|[ée]volutif|[ée]volutive|might|could|should|path to|lead to|vers un poste|pas d|no permanent|not a permanent)\b",
    re.IGNORECASE,
)


def metadata_review(title, description, has_title_signal, contract_type):
    """Return an override and reason, or None to retain ordinary title rules."""
    # Preserve paragraph boundaries for isolated contract labels and conversion clauses.
    text = re.sub(r"<(?:br\s*/?|/p|/div)>", "\n", description, flags=re.IGNORECASE)
    text = re.sub(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*?)?/?>", " ", text)
    chunks = [re.sub(r"\s+", " ", c).strip() for c in re.split(r"[\n.!?;]+", text)]
    placement = next(
        (
            m.group()
            for c in chunks
            if (m := PLACEMENT.search(c))
            and not PRIOR.search(c[max(0, m.start() - 65) : m.start()])
        ),
        None,
    )
    direct_contract = re.compile(
        r"^(?:(?:type de contrat|contrat|emploi|statut)\s*[:–-]?\s*)?(?:CDI|CDD)\b"
        r"|\b(?:poste|contrat|recrutons)\b.{0,65}\b(?:CDI|CDD)\b"
        r"|contract van onbepaalde duur|permanent (?:employment|contract|position|role)"
        r"|unbefristete[snrm]? (?:Arbeitsvertrag|Anstellung|Stelle)",
        re.IGNORECASE,
    )
    conflict = next(
        (
            m.group()
            for c in [title, *chunks]
            if (c == title or direct_contract.search(c))
            and not FUTURE.search(c)
            and (m := CONTRACT.search(c))
        ),
        None,
    )
    if conflict:
        status = "uncertain" if has_title_signal or placement else "not_internship"
        return status, "contract_conflict", conflict
    if contract_type == "internship":
        if has_title_signal:
            return "confirmed", "title_and_contract", title
        if placement:
            return "confirmed", "placement_description", placement
        return "uncertain", "uncorroborated_ats_contract", "internship"
    return None
