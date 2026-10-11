from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("jobboard", "0009_catalogue")]
    operations = [
        migrations.RenameField(
            model_name="candidateprofile", old_name="location", new_name="location_text"
        ),
    ]
