"""Check the destination and CV owner even when writes bypass the API."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("jobboard", "0033_password_hash_sql_name")]
    operations = [
        migrations.AddField(
            model_name="recruiterapplicant",
            name="candidate",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="recruiterapplicant",
            name="offer",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="jobboard.offer",
            ),
        ),
        migrations.AddField(
            model_name="recruiterapplicant",
            name="resume_kind",
            field=models.CharField(default="resume", editable=False, max_length=16),
        ),
        migrations.RunSQL(
            "UPDATE jobboard_recruiterapplicant ra "
            "SET candidate_id = a.user_id, offer_id = a.offer_id "
            "FROM jobboard_application a WHERE a.id = ra.application_id",
            migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="recruiterapplicant",
            name="candidate",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AlterField(
            model_name="recruiterapplicant",
            name="offer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="jobboard.offer"
            ),
        ),
        migrations.AddConstraint(
            model_name="application",
            constraint=models.UniqueConstraint(
                fields=("id", "user", "offer"), name="application_owner_offer_identity"
            ),
        ),
        migrations.AddConstraint(
            model_name="recruiterjob",
            constraint=models.UniqueConstraint(
                fields=("id", "offer"), name="recruiter_job_offer_identity"
            ),
        ),
        migrations.AddConstraint(
            model_name="recruiterapplicant",
            constraint=models.CheckConstraint(
                condition=models.Q(resume_kind="resume"),
                name="recruiter_resume_kind_valid",
            ),
        ),
    ] + [
        migrations.RunSQL(
            f"ALTER TABLE jobboard_recruiterapplicant ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({columns}) REFERENCES {target} ({target_columns}) "
            "DEFERRABLE INITIALLY IMMEDIATE",
            f"ALTER TABLE jobboard_recruiterapplicant DROP CONSTRAINT {name}",
        )
        for name, columns, target, target_columns in [
            (
                "recruiter_application_owner_offer_fk",
                "application_id, candidate_id, offer_id",
                "jobboard_application",
                "id, user_id, offer_id",
            ),
            (
                "recruiter_application_job_offer_fk",
                "job_id, offer_id",
                "jobboard_recruiterjob",
                "id, offer_id",
            ),
            (
                "recruiter_application_resume_owner_fk",
                "resume_id, candidate_id, resume_kind",
                "jobboard_document",
                "id, owner_id, kind",
            ),
        ]
    ]
