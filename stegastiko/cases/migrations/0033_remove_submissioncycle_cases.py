"""Step 3/3: announcements no longer belong to division cases."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0032_submissioncycle_plots_data"),
    ]

    operations = [
        migrations.RemoveField(model_name="submissioncycle", name="cases"),
    ]
