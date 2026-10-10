"""Validate PDFs and keep durable pending/deleting rows around storage operations."""

import hashlib
import logging
import math
from io import BytesIO
from pathlib import PurePath
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from pypdf import PdfReader, filters
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NullObject,
    NumberObject,
)

from jobboard.api.core import APIError, lock_user
from jobboard.integrations.storage import (
    delete_object,
    read_object,
    storage_bucket,
    write_object,
)
from jobboard.models import Document
from jobboard.services.profiles import bump, locked_profile

# A CV never needs enormous decoded object streams. pypdf enforces these
# limits before allocating decoder output, including compressed object tables.
filters.ZLIB_MAX_OUTPUT_LENGTH = 16 * 1024 * 1024
filters.LZW_MAX_OUTPUT_LENGTH = 16 * 1024 * 1024
filters.MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH = 16 * 1024 * 1024
filters.MAX_DECLARED_STREAM_LENGTH = 16 * 1024 * 1024


def _passive_open_destination(value, reader):
    """Accept only a local page/zoom destination, never an action dictionary."""
    if not isinstance(value, ArrayObject) or len(value) < 2:
        return False
    page, mode, *coordinates = value
    arity = {
        "/Fit": 0,
        "/FitB": 0,
        "/FitH": 1,
        "/FitV": 1,
        "/FitBH": 1,
        "/FitBV": 1,
        "/XYZ": 3,
        "/FitR": 4,
    }
    if (
        not isinstance(mode, str)
        or mode not in arity
        or len(coordinates) != arity[mode]
    ):
        return False
    if not isinstance(page, IndirectObject) or not any(
        page == candidate.indirect_reference for candidate in reader.pages
    ):
        return False
    return all(
        isinstance(coordinate, NullObject)
        or (
            isinstance(coordinate, (NumberObject, FloatObject))
            and math.isfinite(float(coordinate))
        )
        for coordinate in coordinates
    )


def validate_pdf(data):
    if not data.startswith(b"%PDF-"):
        raise APIError("invalid_pdf", "A valid PDF is required.")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
            raise ValueError("Encrypted or excessive PDF")
        seen = set()
        stack = [reader.trailer]
        count = 0
        while stack:
            item = stack.pop()
            if isinstance(item, IndirectObject):
                identity = (item.idnum, item.generation)
                if identity in seen:
                    continue
                seen.add(identity)
                item = item.get_object()
            count += 1
            if count > 100000:
                raise ValueError("Excessive PDF object graph")
            if isinstance(item, DictionaryObject):
                # LaTeX and other exporters use /OpenAction for passive page fitting.
                # Only permit that form on the catalog; continue traversing it below.
                if "/OpenAction" in item and (
                    item is not reader.root_object
                    or not _passive_open_destination(item["/OpenAction"], reader)
                ):
                    raise ValueError("Opening actions are not accepted")
                if any(
                    key in item
                    for key in (
                        "/JS",
                        "/JavaScript",
                        "/AA",
                        "/EmbeddedFiles",
                        "/EF",
                        "/XFA",
                        "/RichMedia",
                    )
                ):
                    raise ValueError("Active content is not accepted")
                if item.get("/S") in (
                    "/JavaScript",
                    "/Launch",
                    "/SubmitForm",
                    "/ImportData",
                    "/GoToR",
                    "/Rendition",
                ):
                    raise ValueError("Active actions are not accepted")
                stack.extend(item.values())
            elif isinstance(item, ArrayObject):
                stack.extend(item)
    except Exception as exc:
        raise APIError(
            "invalid_pdf",
            "PDF must be readable, unencrypted and contain no active content.",
        ) from exc


def upload_document(user, uploaded_file, kind):
    if kind not in ("resume", "cover_letter"):
        raise APIError("invalid_kind", "Document kind must be resume or cover_letter.")
    maximum = settings.MAX_DOCUMENT_BYTES
    if uploaded_file.size > maximum:
        raise APIError(
            "document_too_large", "PDF exceeds the upload limit.", status=413
        )
    data = uploaded_file.read(maximum + 1)
    if len(data) > maximum:
        raise APIError(
            "document_too_large", "PDF exceeds the upload limit.", status=413
        )
    validate_pdf(data)
    with transaction.atomic():
        lock_user(user)
        document = Document.objects.create(
            owner=user,
            kind=kind,
            origin="upload",
            bucket=storage_bucket(),
            object_key=f"{user.pk}/{uuid4().hex}.pdf",
            original_name=PurePath(uploaded_file.name.replace("\\", "/")).name[:255],
            mime_type="application/pdf",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            status="pending",
        )
    try:
        write_object(document.bucket, document.object_key, data)
        with transaction.atomic():
            lock_user(user)
            current = Document.objects.select_for_update().get(pk=document.pk)
            if current.status != "pending":
                raise APIError(
                    "document_unavailable", "Document is no longer pending.", status=409
                )
            current.status = "ready"
            current.save(update_fields=["status"])
            document = current
    except Exception as exc:
        # The write call has finished: release the upload barrier durably before
        # cleanup. This must also work after account deactivation; purge waits on
        # pending rows and may now recover this deleting row and its object key.
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            Document.objects.filter(pk=document.pk, status="pending").update(
                status="deleting"
            )
        document.status = "deleting"
        try:
            delete_document_blob(document)
        except Exception:
            logging.getLogger(__name__).exception("Pending document cleanup failed")
        if isinstance(exc, APIError):
            raise
        raise APIError(
            "storage_unavailable", "Private storage is unavailable.", status=503
        ) from exc
    return document


def read_document(document):
    if document.status != "ready":
        raise APIError("document_unavailable", "Document is not ready.", status=409)
    try:
        data = read_object(document.bucket, document.object_key)
    except Exception as exc:
        raise APIError(
            "storage_unavailable", "Private storage is unavailable.", status=503
        ) from exc
    if (
        len(data) != document.byte_size
        or hashlib.sha256(data).hexdigest() != document.sha256
    ):
        raise APIError(
            "document_integrity",
            "Stored document does not match its verified fingerprint.",
            status=409,
        )
    return data


def delete_document_blob(document):
    delete_object(document.bucket, document.object_key)


def delete_document(user, pk):
    with transaction.atomic():
        lock_user(user)
        document = (
            Document.objects.select_for_update().filter(owner=user, pk=pk).first()
        )
        if document is None:
            raise APIError("not_found", "Resource not found.", status=404)
        if document.status == "pending":
            raise APIError(
                "upload_in_progress", "This document is still uploading.", status=409
            )
        if (
            document.recruiterapplicant_set.exists()
            or document.current_for_profiles.exists()
            or document.revision_links.exists()
            or document.evidence_for_runs.exists()
            or document.variants.exists()
        ):
            raise APIError(
                "document_referenced",
                "This document is retained by a profile or historical dossier.",
                status=409,
            )
        document.status = "deleting"
        document.save(update_fields=["status"])
    try:
        delete_document_blob(document)
    except Exception as exc:
        raise APIError(
            "storage_unavailable",
            "Private storage is unavailable; deletion can be retried.",
            status=503,
        ) from exc
    with transaction.atomic():
        lock_user(user)
        Document.objects.filter(pk=pk, owner=user, status="deleting").delete()


def set_resume(user, pk):
    document = Document.objects.filter(
        pk=pk, owner=user, kind="resume", status="ready"
    ).first()
    if document is None:
        raise APIError("not_found", "Ready resume not found.", status=404)
    read_document(document)
    with transaction.atomic():
        profile = locked_profile(user)
        document = (
            Document.objects.select_for_update()
            .filter(pk=pk, owner=user, kind="resume", status="ready")
            .first()
        )
        if document is None:
            raise APIError("not_found", "Ready resume not found.", status=404)
        profile.current_resume = document
        profile.save(update_fields=["current_resume", "updated_at"])
        bump(profile)
        return profile
