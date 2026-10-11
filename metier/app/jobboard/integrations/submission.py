"""Explicit submission capability. Public job access never grants submission access."""

import base64
import hashlib
import json
import re
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.utils import timezone

from jobboard.api.core import APIError


@dataclass(frozen=True)
class SubmissionResult:
    status: str  # succeeded, failed, uncertain
    receipt: str | None = None
    error_code: str | None = None


def fingerprint(form):
    content = {
        k: v for k, v in form.items() if k not in {"fetched_at", "form_fingerprint"}
    }
    return hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def basic_form():
    fields = [
        {"key": key, "label": label, "type": kind, "required": required, "options": []}
        for key, label, kind, required in [
            ("first_name", "First name", "text", True),
            ("last_name", "Last name", "text", True),
            ("email", "Email", "text", True),
        ]
    ]
    form = {
        "fields": fields,
        "notices": [],
        "supported": False,
        "fetched_at": timezone.now().isoformat(),
    }
    form["form_fingerprint"] = fingerprint(form)
    return form


class GreenhouseAdapter:
    version = "greenhouse-partner-v1"

    def __init__(self, source):
        self.source = source
        board = source.board
        if (
            board.provider != "greenhouse"
            or board.instance != "global"
            or not isinstance(board.board_key, str)
            or not isinstance(source.external_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,240}", board.board_key)
            or not re.fullmatch(r"[0-9]{1,30}", source.external_id)
        ):
            raise APIError("unsupported_source", "Unsupported Greenhouse source.", 409)
        self.url = f"https://boards-api.greenhouse.io/v1/boards/{board.board_key}/jobs/{source.external_id}"
        self.key = settings.GREENHOUSE_API_KEYS.get(board.board_key)

    def ensure_enabled(self):
        if (
            self.source.board.provider != "greenhouse"
            or not self.source.board.enabled
            or self.source.board.submission_mode != "partner_api"
            or not isinstance(self.key, str)
            or not self.key.strip()
        ):
            raise APIError(
                "submission_unavailable",
                "An authorized partner connector must be configured.",
                409,
            )

    def fetch_form(self):
        try:
            with httpx.Client(
                timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "GET", self.url, params={"questions": "true"}
                ) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            raise ValueError("oversized")
                        chunks.append(chunk)
                    data = json.loads(b"".join(chunks))
            if (
                not isinstance(data, dict)
                or type(data.get("id")) is not int
                or str(data["id"]) != self.source.external_id
                or not isinstance(data.get("questions"), list)
                or len(data["questions"]) > 200
            ):
                raise ValueError("invalid_form")
            form = basic_form()
            form["supported"] = True
            mapped = {
                "input_text": "text",
                "textarea": "text",
                "multi_value_single_select": "select",
                "multi_value_multi_select": "multi_select",
                "input_file": "file",
            }
            by_key = {f["key"]: f for f in form["fields"]}
            seen = set()
            for question in data["questions"]:
                if (
                    not isinstance(question, dict)
                    or type(question.get("required")) is not bool
                    or not isinstance(question.get("label"), str)
                    or not 1 <= len(question["label"]) <= 500
                ):
                    raise ValueError("invalid_question")
                fields = question.get("fields")
                if not isinstance(fields, list) or not 1 <= len(fields) <= 10:
                    raise ValueError("invalid_fields")
                normalized = []
                for field in fields:
                    if not isinstance(field, dict):
                        raise ValueError("invalid_field")
                    key, source_kind = field.get("name"), field.get("type")
                    if (
                        not isinstance(key, str)
                        or not re.fullmatch(r"[A-Za-z0-9_]{1,120}", key)
                        or key in seen
                        or not isinstance(source_kind, str)
                    ):
                        raise ValueError("invalid_key")
                    seen.add(key)
                    kind = mapped.get(source_kind)
                    if (
                        key in {"first_name", "last_name", "email", "phone"}
                        and kind != "text"
                    ):
                        raise ValueError("invalid_identity_type")
                    if key in {"resume", "cover_letter"} and kind != "file":
                        raise ValueError("invalid_document_type")
                    options = field.get("values", [])
                    if not isinstance(options, list) or len(options) > 1000:
                        raise ValueError("invalid_options")
                    option_values, clean_options = set(), []
                    for option in options:
                        if (
                            not isinstance(option, dict)
                            or type(option.get("value")) not in (str, int)
                            or not isinstance(option.get("label"), str)
                        ):
                            raise ValueError("invalid_option")
                        value, label = option["value"], option["label"]
                        if (
                            len(str(value)) > 300
                            or len(label) > 500
                            or (type(value), value) in option_values
                        ):
                            raise ValueError("invalid_option")
                        option_values.add((type(value), value))
                        clean_options.append({"value": value, "label": label})
                    if kind in {"select", "multi_select"} and not clean_options:
                        raise ValueError("empty_options")
                    if kind not in {"select", "multi_select"} and clean_options:
                        raise ValueError("unexpected_options")
                    if kind is None or (
                        kind == "file" and key not in {"resume", "cover_letter"}
                    ):
                        form["supported"] = False
                    normalized.append(
                        {
                            "key": key,
                            "label": question["label"],
                            "type": kind,
                            "required": question["required"],
                            "options": clean_options,
                        }
                    )
                # Only the documented resume/cover-letter file + plaintext alternative
                # can be collapsed. Other grouped questions remain unsupported.
                if len(normalized) > 1:
                    files = [
                        f
                        for f in normalized
                        if f["type"] == "file"
                        and f["key"] in {"resume", "cover_letter"}
                    ]
                    if (
                        len(files) != 1
                        or len(normalized) != 2
                        or not any(
                            f["key"] == files[0]["key"] + "_text"
                            and f["type"] == "text"
                            for f in normalized
                        )
                    ):
                        form["supported"] = False
                        continue
                    normalized = files
                for field in normalized:
                    if field["type"] is None:
                        continue
                    # Transport fields (URLs/base64/consent/tracking) must never become
                    # arbitrary text answers forwarded directly to the partner API.
                    if field["key"] not in {
                        "first_name",
                        "last_name",
                        "email",
                        "phone",
                        "resume",
                        "cover_letter",
                    } and not re.fullmatch(r"question_[0-9]+", field["key"]):
                        form["supported"] = False
                    by_key[field["key"]] = field
            for key in ("first_name", "last_name", "email"):
                by_key[key]["required"] = True
            if len(by_key) > 200:
                raise ValueError("too_many_fields")
            form["fields"] = list(by_key.values())
            # Explicitly fail closed for forms needing additional location/compliance protocols.
            for section in (
                "location_questions",
                "compliance",
                "data_compliance",
                "demographic_questions",
            ):
                if data.get(section):
                    form["notices"].append({"kind": section, "content": data[section]})
                    form["supported"] = False
            if data.get("ai_disclaimer"):
                form["notices"].append(
                    {"kind": "ai_disclaimer", "content": data["ai_disclaimer"]}
                )
            form["form_fingerprint"] = fingerprint(form)
            return form
        except (httpx.HTTPError, ValueError, KeyError, TypeError, RecursionError):
            raise APIError(
                "form_unavailable",
                "The current application form could not be verified.",
                503,
            ) from None

    def submit(self, revision, documents):
        self.ensure_enabled()
        payload = {
            answer["field_key"]: answer["value"]
            for answer in revision.answers
            if answer["value"] is not None
        }
        file_fields = {
            field["key"]
            for field in revision.form_snapshot["fields"]
            if field["type"] == "file"
        }
        if set(documents) - file_fields:
            raise APIError(
                "unexpected_documents",
                "This form does not request these documents.",
                409,
            )
        for purpose, (document, data) in documents.items():
            payload[purpose + "_content"] = base64.b64encode(data).decode("ascii")
            payload[purpose + "_content_filename"] = (
                document.original_name or purpose + ".pdf"
            )
        try:
            # No automatic retries: the remote API has no guaranteed idempotency contract.
            with httpx.Client(
                timeout=30, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "POST", self.url, auth=(self.key, ""), json=payload
                ) as response:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 1024 * 1024:
                            return SubmissionResult(
                                "uncertain", error_code="response_too_large"
                            )
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    if response.status_code in (200, 201):
                        # Preserve a digest of the actual HTTP acknowledgement, never fabricate a candidate ID.
                        receipt = f"greenhouse:http-{response.status_code}:sha256:{hashlib.sha256(raw).hexdigest()}"
                        return SubmissionResult("succeeded", receipt=receipt)
                    if response.status_code in (400, 401, 403, 404, 413, 422, 429):
                        return SubmissionResult(
                            "failed", error_code=f"provider_http_{response.status_code}"
                        )
                    return SubmissionResult(
                        "uncertain", error_code="provider_response_uncertain"
                    )
        except httpx.HTTPError:
            return SubmissionResult(
                "uncertain", error_code="provider_transport_uncertain"
            )


def get_adapter(source):
    if source.board.provider != "greenhouse":
        raise APIError(
            "submission_unavailable",
            "No submission connector is configured for this source.",
            409,
        )
    return GreenhouseAdapter(source)


def fetch_form(source):
    if source.board.provider == "greenhouse":
        return get_adapter(source).fetch_form()
    return basic_form()
