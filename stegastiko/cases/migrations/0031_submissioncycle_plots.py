"""Step 1/3: announcements offer completed plots instead of covering cases."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0030_case_completion"),
        ("plots", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="submissioncycle",
            name="plots",
            field=models.ManyToManyField(
                blank=True,
                help_text="9.1 Διαθέσιμα οικόπεδα της Κοινότητας που προσφέρει η γνωστοποίηση",
                related_name="submission_cycles",
                to="plots.plot",
            ),
        ),
    ]
