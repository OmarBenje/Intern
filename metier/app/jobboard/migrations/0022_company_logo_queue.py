# ruff: noqa: RUF012
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("jobboard", "0021_coverage_discovery")]

    operations = [
        migrations.AddField(
            model_name="company",
            name="logo_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="company",
            name="logo_next_attempt_at",
            field=models.DateTimeField(
                default=django.utils.timezone.now, null=True, blank=True, db_index=True
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="logo_last_error",
            field=models.CharField(max_length=240, blank=True, default=""),
        ),
    ]
