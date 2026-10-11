# ruff: noqa: RUF012
from django.db import migrations, models
from django.utils import timezone


def reject_linkedin_favicon(apps, schema_editor):
    # This PNG was visually confirmed as LinkedIn's global favicon. Do not
    # invalidate other shared digests: subsidiaries may legitimately share logos.
    apps.get_model("jobboard", "Company").objects.using(
        schema_editor.connection.alias
    ).filter(
        logo_object_key__endswith="/037e67fd114b8f2a091d5973a2d89b5705614c3a1812192a51f9358fc73083aa.png"
    ).update(
        logo_object_key=None,
        logo_attempts=0,
        logo_next_attempt_at=timezone.now(),
        logo_last_error="platform_logo_rejected",
    )


class Migration(migrations.Migration):
    dependencies = [("jobboard", "0025_search_document")]

    operations = [
        migrations.AddField(
            model_name="company",
            name="logo_source_url",
            field=models.URLField(max_length=2048, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="company",
            name="logo_source_kind",
            field=models.CharField(max_length=32, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="company",
            name="logo_fetched_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.RunPython(reject_linkedin_favicon, migrations.RunPython.noop),
    ]
