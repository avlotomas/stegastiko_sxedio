import django.core.validators
from django.db import migrations, models
from django.db.models import F


def restore_start_date(apps, schema_editor):
    """Reverse only: the submission period used to start the day the announcement was issued."""
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    SubmissionCycle.objects.update(submission_start_date=F("announcement_date"))


def months_from_dates(apps, schema_editor):
    """Existing announcements keep their last day; the months are what that day implies."""
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for cycle in SubmissionCycle.objects.all():
        start, end = cycle.announcement_date, cycle.submission_end_date
        months = (end.year - start.year) * 12 + end.month - start.month + (1 if end.day > start.day else 0)
        cycle.submission_months = min(max(months, 1), 12)
        cycle.save(update_fields=["submission_months"])


class Migration(migrations.Migration):
    """Γνωστοποίηση = πεδία του Πρότυπου 1: ημερομηνία, μήνες, λήξη (η έναρξη είναι η ημερομηνία γνωστοποίησης)."""

    dependencies = [
        ("cases", "0038_remove_submissioncycle_community"),
    ]

    operations = [
        migrations.AlterField(
            model_name="submissioncycle",
            name="submission_start_date",
            field=models.DateField(null=True),
        ),
        migrations.RunPython(migrations.RunPython.noop, restore_start_date),
        migrations.RemoveField(model_name="submissioncycle", name="submission_start_date"),
        migrations.RemoveField(model_name="submissioncycle", name="announcement_text"),
        migrations.AddField(
            model_name="submissioncycle",
            name="submission_months",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="9.1 Προθεσμία υποβολής αιτήσεων σε μήνες από την ημερομηνία γνωστοποίησης· η τελευταία ημέρα υποβολής υπολογίζεται αυτόματα",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(12),
                ],
            ),
        ),
        migrations.RunPython(months_from_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="submissioncycle",
            name="submission_end_date",
            field=models.DateField(
                editable=False,
                help_text="9.1 Τελευταία ημέρα υποβολής αιτήσεων (υπολογίζεται από την ημερομηνία γνωστοποίησης και τους μήνες)",
            ),
        ),
    ]
