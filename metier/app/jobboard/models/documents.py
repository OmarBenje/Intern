from django.conf import settings
from django.db import models
from django.db.models import F, Q

from .choices import DocumentKind
from .constraints import allowed


class Document(models.Model):
    Kind = DocumentKind
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documents"
    )
    kind = models.CharField(max_length=16, choices=DocumentKind)
    origin = models.CharField(
        max_length=12,
        choices=[(v, v.title()) for v in ("upload", "generated", "capture")],
    )
    bucket = models.CharField(max_length=100)
    object_key = models.TextField()
    original_name = models.CharField(max_length=255, null=True, blank=True)
    mime_type = models.CharField(max_length=160)
    byte_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[
            (v, v.title()) for v in ("pending", "ready", "quarantined", "deleting")
        ],
    )
    derived_from = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="variants"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bucket", "object_key"], name="document_object_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "owner"], name="document_owner_identity"
            ),
            models.UniqueConstraint(
                fields=["id", "owner", "kind"], name="document_kind_identity"
            ),
            allowed("kind", DocumentKind.values, "document_kind_valid"),
            allowed(
                "origin", ("upload", "generated", "capture"), "document_origin_valid"
            ),
            allowed(
                "status",
                ("pending", "ready", "quarantined", "deleting"),
                "document_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(byte_size__gt=0), name="document_size_positive"
            ),
            models.CheckConstraint(
                condition=Q(sha256__regex=r"^[0-9a-f]{64}$"), name="document_hash_valid"
            ),
            models.CheckConstraint(
                condition=Q(derived_from__isnull=True) | ~Q(derived_from=F("id")),
                name="document_not_own_parent",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="document_owner_idx")
        ]

    def __str__(self):
        return self.original_name or f"{self.kind} #{self.pk}"
