"""Offline, source-preserving description projection. Never render employer HTML."""

import hashlib
import json
import re
from html import unescape
from html.parser import HTMLParser

SCHEMA_VERSION = "offer-content-1"
SECTION_PATTERNS = {
    "about_role": r"about the (?:role|job|team)|(?:à|a) propos du poste|le poste|the role|job description|beschreibung|jobdescription",
    "about_company": r"about us|(?:à|a) propos de (?!toi|vous).+|über uns|companydescription",
    "responsibilities": r"(?:main |key |principales? )?(?:responsibilities|responsabilités)|(?:vos |tes |your )?missions|what you(?:.ll| will) do|your (?:tasks|impact)|aufgaben|deine aufgaben|tätigkeiten",
    "requirements": r"(?:required |minimum |basic )?(?:requirements|qualifications|skills)|(?:votre |ton |your )?(?:profil(?: recherché)?|profile)|(?:à|a) propos de (?:toi|vous)|what (?:we.re looking for|you bring)|who you are|anforderungen|qualifikationen|voraussetzungen",
    "preferred": r"(?:desired|preferred|additional) (?:qualifications|skills)|nice to have|bonus(?: points)?|un plus|(?:compétences|qualités) (?:appréciées|souhaitées)|atouts|wünschenswert",
    "conditions": r"(?:internship|stage|program(?:me)?) (?:details|conditions|information|start date)|conditions(?: du stage)?|informations pratiques|durée.*|duration.*|start date.*|additionalinformation|praktikumsdetails",
    "benefits": r"benefits|what we offer|(?:ce que )?nous (?:offrons|proposons)|avantages|pourquoi nous (?:rejoindre|choisir)|wir bieten",
    "recruitment": r"(?:recruitment|hiring|interview|application) process|(?:processus|étapes) (?:de recrutement|de sélection)|how to apply|bewerbung.*",
}


def normalized_text(value):
    return " ".join(unescape(value).split())


def section_kind(heading):
    heading = normalized_text(heading).strip(" :?\u202f").casefold()
    for kind, pattern in SECTION_PATTERNS.items():
        if re.fullmatch(pattern, heading, re.IGNORECASE):
            return kind
    return "other"


class BlockParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.buffer = []
        self.heading = False
        self.lists = []
        self.hidden_depth = 0

    def flush(self):
        text = normalized_text("".join(self.buffer))
        self.buffer = []
        if not text:
            return
        if self.lists:
            current = self.lists[-1]
            if not current["items"]:
                current["items"].append({"text": "", "children": []})
            item = current["items"][-1]
            item["text"] = normalized_text(item["text"] + " " + text)
        else:
            heading = self.heading or len(text) < 120 and section_kind(text) != "other"
            self.blocks.append(
                {"kind": "heading" if heading else "paragraph", "text": text}
            )

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        if tag in {"ul", "ol"}:
            self.flush()
            self.lists.append(
                {"kind": "ordered_list" if tag == "ol" else "bullet_list", "items": []}
            )
        elif tag == "li":
            self.flush()
            if self.lists:
                self.lists[-1]["items"].append({"text": "", "children": []})
        elif tag in {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "div",
            "br",
            "section",
            "article",
        }:
            self.flush()
            self.heading = tag.startswith("h") and len(tag) == 2

    def handle_endtag(self, tag):
        if self.hidden_depth:
            # Hidden elements normally have no nested markup; void tags have no end.
            if tag in {"script", "style", "template", "noscript"}:
                self.hidden_depth -= 1
            return
        if tag in {"ul", "ol"} and self.lists:
            self.flush()
            block = self.lists.pop()
            if self.lists:
                parent = self.lists[-1]["items"]
                if parent:
                    parent[-1]["children"].append(block)
            elif block["items"]:
                self.blocks.append(block)
        elif tag in {
            "li",
            "p",
            "div",
            "section",
            "article",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        }:
            self.flush()
            self.heading = False

    def handle_data(self, data):
        if not self.hidden_depth:
            self.buffer.append(data)


def html_blocks(value):
    parser = BlockParser()
    parser.feed(unescape(value))
    parser.flush()
    while parser.lists:
        parser.handle_endtag("ul")
    blocks = []
    for block in parser.blocks:
        if (
            blocks
            and block["kind"] in {"bullet_list", "ordered_list"}
            and blocks[-1]["kind"] == block["kind"]
        ):
            blocks[-1]["items"].extend(block["items"])
        else:
            blocks.append(block)
    return blocks


def text_blocks(value):
    blocks, paragraph = [], []

    def flush():
        if paragraph:
            blocks.append(
                {"kind": "paragraph", "text": normalized_text(" ".join(paragraph))}
            )
            paragraph.clear()

    for line in unescape(value).splitlines():
        line = line.strip()
        if not line:
            flush()
        elif len(line) < 120 and section_kind(line) != "other":
            flush()
            blocks.append({"kind": "heading", "text": line})
        elif match := re.match(r"^(?:[•*–-]|\d+[.)])\s+(.+)", line):
            flush()
            kind = "ordered_list" if re.match(r"^\d", line) else "bullet_list"
            if not blocks or blocks[-1]["kind"] != kind:
                blocks.append({"kind": kind, "items": []})
            blocks[-1]["items"].append({"text": match[1], "children": []})
        else:
            paragraph.append(line)
    flush()
    return blocks


def blocks_from(value):
    if re.search(r"<(?:p|div|h[1-6]|ul|ol|li|br|section)\b", value, re.IGNORECASE):
        return html_blocks(value)
    return text_blocks(value)


def block_texts(block):
    if "text" in block:
        yield block["text"]
    for item in block.get("items", []):
        yield item["text"]
        for child in item.get("children", []):
            yield from block_texts(child)


def fingerprint(blocks):
    # Preserve technology punctuation and word boundaries: C++ is not C.
    text = normalized_text(
        " ".join(text for block in blocks for text in block_texts(block))
    )
    return re.sub(r"\s+([,.:;!?])", r"\1", text).casefold()


def payload_blocks(payload):
    # Explicit field paths, not arbitrary recursive HTML found in unrelated fields.
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("lists"), list) and isinstance(
        payload.get("descriptionPlain"), str
    ):
        # Lever's description excludes its lists and closing copy. Choosing only
        # its HTML body would silently omit qualifications and defeat source matching.
        blocks = blocks_from(payload.get("description") or payload["descriptionPlain"])
        for group in payload.get("lists", []):
            if not isinstance(group, dict):
                continue
            if isinstance(group.get("text"), str):
                blocks.append({"kind": "heading", "text": group["text"]})
            if isinstance(group.get("content"), str):
                content = group["content"]
                blocks.extend(
                    html_blocks(
                        content
                        if re.match(r"\s*<(?:ul|ol)\b", content)
                        else "<ul>" + content + "</ul>"
                    )
                )
        extra = payload.get("additional") or payload.get("additionalPlain")
        if isinstance(extra, str):
            blocks.extend(blocks_from(extra))
        return blocks
    for key in ("descriptionHtml", "content", "jobDescription", "description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return blocks_from(value)
    info = payload.get("jobPostingInfo")
    if isinstance(info, dict):
        return payload_blocks(info)
    ad = payload.get("jobAd", {})
    sections = ad.get("sections", {}) if isinstance(ad, dict) else {}
    if isinstance(sections, dict) and sections:
        blocks = []
        for key in (
            "companyDescription",
            "jobDescription",
            "qualifications",
            "additionalInformation",
        ):
            section = sections.get(key, {})
            if isinstance(section, dict) and isinstance(section.get("text"), str):
                # The connector's current text omits these structural keys; add
                # their headings only after matching the actual section bodies.
                section_blocks = blocks_from(section["text"])
                if section_blocks:
                    section_blocks[0]["section_kind"] = {
                        "companyDescription": "about_company",
                        "jobDescription": "about_role",
                        "qualifications": "requirements",
                        "additionalInformation": "conditions",
                    }[key]
                blocks.extend(section_blocks)
        return blocks
    description = payload.get("descriptionPlain")
    if isinstance(description, str):
        blocks = text_blocks(description)
        for group in payload.get("lists", []):
            if isinstance(group, dict):
                if isinstance(group.get("text"), str):
                    blocks.append({"kind": "heading", "text": group["text"]})
                if isinstance(group.get("content"), str):
                    content = group["content"]
                    blocks.extend(html_blocks("<ul>" + content + "</ul>"))
        if isinstance(payload.get("additionalPlain"), str):
            blocks.extend(text_blocks(payload["additionalPlain"]))
        return blocks
    return []


def requirement(text, kind, block_id):
    negation = r"not required|not mandatory|non obligatoire|pas (?:requis|obligatoire)|nicht erforderlich|\bno\b[^.;,\n]*\b(?:required|mandatory)\b"
    preferred = bool(
        re.search(
            r"preferred|ideally|nice.to.have|souhait|appréci|un plus|wünschenswert|idealerweise",
            re.sub(negation, "", text, flags=re.IGNORECASE),
            re.IGNORECASE,
        )
    )
    required = bool(
        re.search(
            r"required|must|mandatory|minimum|obligatoire|exig|courant|fluent|erforderlich",
            re.sub(negation, "", text, flags=re.IGNORECASE),
            re.IGNORECASE,
        )
    )
    negated = bool(re.search(negation, text, re.IGNORECASE))
    modality = (
        "mixed"
        if negated and required
        else "optional"
        if negated
        else "mixed"
        if preferred and required
        else "preferred"
        if preferred or kind == "preferred"
        else "required"
        if required or kind == "requirements"
        else "unknown"
    )
    categories = {
        "education": r"degree|bachelor|master|graduat|student|enroll|diplôm|étudian|formation|studium|eingeschrieben",
        "documents": r"convention|agreement|transcript|cover letter|lettre de motivation",
        "work_authorization": r"visa|sponsor|authoriz|autorisa|right to work|droit de travailler",
        "language": r"english|french|german|anglais|français|allemand|language|langue|deutsch",
        "availability": r"availab|disponib|start|début|month|mois|week|semaine|hours|heures",
    }
    category = next(
        (
            key
            for key, pattern in categories.items()
            if re.search(pattern, text, re.IGNORECASE)
        ),
        "skill",
    )
    return {
        "text": text,
        "category": category,
        "modality": modality,
        "alternative": bool(re.search(r"\bor\b|\bou\b|\boder\b", text, re.IGNORECASE)),
        "block_id": block_id,
    }


def build_content(description, revisions=()):
    blocks = blocks_from(description)
    expected = fingerprint(blocks)
    revision_id = None
    selected_payload = {}
    for revision in revisions:
        candidate = payload_blocks(revision.payload)
        if candidate and expected and fingerprint(candidate) == expected:
            blocks, revision_id, selected_payload = (
                candidate,
                revision.pk,
                revision.payload,
            )
            break
    sections, requirements = [], []
    current = None
    for index, block in enumerate(blocks):
        block["id"] = f"b{index}"
        if block["kind"] == "heading":
            current = {
                "kind": section_kind(block["text"]),
                "original_heading": block["text"],
                "block_ids": [],
            }
            sections.append(current)
        else:
            if current is None or block.get("section_kind"):
                current = {
                    "kind": block.get("section_kind", "about_role"),
                    "original_heading": None,
                    "block_ids": [],
                }
                sections.append(current)
            current["block_ids"].append(block["id"])
            for text in block_texts(block):
                if current["kind"] in {
                    "requirements",
                    "preferred",
                    "conditions",
                } or re.search(
                    r"must|required|obligatoire|convention de stage|visa sponsorship",
                    text,
                    re.IGNORECASE,
                ):
                    requirements.append(requirement(text, current["kind"], block["id"]))
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "description": description,
                "blocks": blocks,
                "sections": sections,
                "requirements": requirements,
                "revision": revision_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "input_hash": input_hash,
        "source_revision_id": revision_id,
        "blocks": blocks,
        "sections": sections,
        "requirements": requirements,
    }, selected_payload
