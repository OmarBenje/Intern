from django.db import models


class ContractType(models.TextChoices):
    INTERNSHIP = "internship", "Internship"
    APPRENTICESHIP = "apprenticeship", "Apprenticeship"
    EMPLOYMENT = "employment", "Employment"
    CONTRACTOR = "contractor", "Contractor"
    TEMPORARY = "temporary", "Temporary"
    UNKNOWN = "unknown", "Unknown"


class WorkMode(models.TextChoices):
    REMOTE = "remote", "Remote"
    HYBRID = "hybrid", "Hybrid"
    ONSITE = "onsite", "On-site"
    UNKNOWN = "unknown", "Unknown"


class OfferStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    EXPIRED = "expired", "Expired"
    HIDDEN = "hidden", "Hidden"


class SalaryPeriod(models.TextChoices):
    HOUR = "hour", "Hour"
    DAY = "day", "Day"
    WEEK = "week", "Week"
    MONTH = "month", "Month"
    YEAR = "year", "Year"


class ApplicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    SCREENING = "screening", "Screening"
    INTERVIEW = "interview", "Interview"
    OFFER_RECEIVED = "offer_received", "Offer received"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


class DocumentKind(models.TextChoices):
    RESUME = "resume", "Resume"
    COVER_LETTER = "cover_letter", "Cover letter"
    EVIDENCE = "evidence", "Evidence"


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    NEEDS_INPUT = "needs_input", "Needs input"
    UNCERTAIN = "uncertain", "Uncertain"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


ACTIVE_RUN_STATUSES = ("queued", "running", "needs_input", "uncertain")
