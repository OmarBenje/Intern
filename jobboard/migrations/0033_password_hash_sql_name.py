"""Expose an explicit SQL password-hash name without changing Django authentication."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("jobboard", "0032_recruiter_company_memberships"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [
        migrations.RunSQL(
            "ALTER TABLE auth_user ADD COLUMN mot_de_passe_hash text "
            "GENERATED ALWAYS AS (password) STORED",
            "ALTER TABLE auth_user DROP COLUMN mot_de_passe_hash",
        ),
    ]
