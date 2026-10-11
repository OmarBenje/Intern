# ruff: noqa: RUF012 - Django declarative model and migration attributes
"""A shared, versioned vocabulary for job functions (independent of industry)."""

from django.db import models


class JobDomain(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "slug"]

    def __str__(self):
        return self.name


class JobSubdomain(models.Model):
    domain = models.ForeignKey(
        JobDomain, on_delete=models.PROTECT, related_name="subdomains"
    )
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    aliases = models.JSONField(default=list)
    generalist = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["domain__position", "position", "slug"]

    def __str__(self):
        return f"{self.domain.name} → {self.name}"
