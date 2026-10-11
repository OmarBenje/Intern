"""Enforce ownership and matching destinations, including writes bypassing the ORM.

Django's ordinary ForeignKey checks only one ID. These additional composite keys
check the owner/application/source together. They are immediate by default, but
can be deferred explicitly inside controlled data-maintenance transactions.
"""

from django.db import migrations

KEYS = [
    (
        "offersource",
        "source_import_board_fk",
        ("last_seen_run_id", "board_id"),
        "importrun",
        ("id", "board_id"),
    ),
    (
        "compensationband",
        "salary_source_offer_fk",
        ("source_id", "offer_id"),
        "offersource",
        ("id", "offer_id"),
    ),
    (
        "document",
        "document_parent_owner_fk",
        ("derived_from_id", "owner_id"),
        "document",
        ("id", "owner_id"),
    ),
    (
        "candidateprofile",
        "profile_resume_owner_kind_fk",
        ("current_resume_id", "user_id", "current_resume_kind"),
        "document",
        ("id", "owner_id", "kind"),
    ),
    (
        "application",
        "application_source_offer_fk",
        ("source_id", "offer_id"),
        "offersource",
        ("id", "offer_id"),
    ),
    (
        "applicationrevision",
        "revision_application_owner_fk",
        ("application_id", "user_id"),
        "application",
        ("id", "user_id"),
    ),
    (
        "revisiondocument",
        "revision_document_owner_fk",
        ("revision_id", "user_id"),
        "applicationrevision",
        ("id", "user_id"),
    ),
    (
        "revisiondocument",
        "revision_document_kind_fk",
        ("document_id", "user_id", "purpose"),
        "document",
        ("id", "owner_id", "kind"),
    ),
    (
        "submissionauthorization",
        "authorization_revision_owner_fk",
        ("revision_id", "application_id", "user_id"),
        "applicationrevision",
        ("id", "application_id", "user_id"),
    ),
    (
        "agentrun",
        "run_revision_owner_fk",
        ("revision_id", "application_id", "user_id"),
        "applicationrevision",
        ("id", "application_id", "user_id"),
    ),
    (
        "agentrun",
        "run_authorization_owner_fk",
        ("authorization_id", "revision_id", "application_id", "user_id"),
        "submissionauthorization",
        ("id", "revision_id", "application_id", "user_id"),
    ),
    (
        "agentrun",
        "run_evidence_owner_fk",
        ("evidence_document_id", "user_id"),
        "document",
        ("id", "owner_id"),
    ),
    (
        "applicationevent",
        "event_run_application_fk",
        ("run_id", "application_id"),
        "agentrun",
        ("id", "application_id"),
    ),
]


class Migration(migrations.Migration):
    dependencies = [("jobboard", "0013_finalize_catalogue_preferences")]
    operations = [
        migrations.RunSQL(
            sql=f'ALTER TABLE "jobboard_{table}" ADD CONSTRAINT "{name}" '
            f'FOREIGN KEY ({", ".join(columns)}) REFERENCES "jobboard_{target}" '
            f"({', '.join(target_columns)}) ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE",
            reverse_sql=f'ALTER TABLE "jobboard_{table}" DROP CONSTRAINT "{name}"',
        )
        for table, name, columns, target, target_columns in KEYS
    ]
