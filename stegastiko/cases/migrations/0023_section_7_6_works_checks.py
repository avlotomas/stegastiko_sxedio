from django.db import migrations, models

# 7.6 checks keep one «Σχόλια» field; the old per-work comments are appended to it.
ITEM_COMMENT_FIELDS = (
    ("curbs_comments", "Ρείθρα"),
    ("pavements_comments", "Κράσπεδα"),
    ("asphalt_comments", "Οδόστρωμα με ασφαλτικό σκυρόδεμα"),
    ("pavement_fill_comments", "Επιχωμάτωση πεζοδρομίων"),
    ("water_comments", "Υδατοπρομήθεια"),
    ("telecom_comments", "Τηλεπικοινωνίες"),
    ("electricity_comments", "Παροχή ηλεκτρικού ρεύματος"),
    ("street_light_comments", "Οδικός φωτισμός"),
)


def _append(existing, lines):
    return "\n".join(part for part in [existing.strip(), *lines] if part)


def merge_old_7_6_values(apps, schema_editor):
    InfrastructureCheck = apps.get_model("cases", "InfrastructureCheck")
    Case = apps.get_model("cases", "Case")

    for check in InfrastructureCheck.objects.all():
        lines = [
            f"{label}: {getattr(check, name).strip()}"
            for name, label in ITEM_COMMENT_FIELDS
            if getattr(check, name).strip()
        ]
        if lines:
            check.comments = _append(check.comments, lines)
            check.save(update_fields=["comments"])

    # The former flat 7.6 fields have no dated check to land on, so they stay readable in the
    # Section 7 comments instead of being turned into a check with invented ΝΑΙ / ΟΧΙ values.
    for case in Case.objects.all():
        lines = []
        if case.works_progress_stage.strip():
            lines.append(f"Τρέχον στάδιο / γενική πορεία εργασιών: {case.works_progress_stage.strip()}")
        if case.works_progress_updated_on:
            lines.append(
                f"Ημερομηνία ενημέρωσης πορείας: {case.works_progress_updated_on:%d/%m/%Y}"
            )
        if case.works_progress_comments.strip():
            lines.append(f"Σχόλια γενικής πορείας: {case.works_progress_comments.strip()}")
        if lines:
            case.section8_comments = _append(case.section8_comments, lines)
            case.save(update_fields=["section8_comments"])


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0022_alter_case_section8_comments_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="infrastructurecheck",
            name="stage",
            field=models.CharField(blank=True, help_text="7.6 Στάδιο", max_length=255),
        ),
        migrations.RunPython(merge_old_7_6_values, migrations.RunPython.noop),
        migrations.RemoveField(model_name="case", name="works_progress_comments"),
        migrations.RemoveField(model_name="case", name="works_progress_stage"),
        migrations.RemoveField(model_name="case", name="works_progress_updated_on"),
        migrations.RemoveField(model_name="infrastructurecheck", name="asphalt_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="curbs_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="electricity_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="pavement_fill_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="pavements_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="street_light_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="telecom_comments"),
        migrations.RemoveField(model_name="infrastructurecheck", name="water_comments"),
        migrations.AlterField(
            model_name="case",
            name="section8_comments",
            field=models.TextField(blank=True, help_text="7 Σχόλια / Παρατηρήσεις Ενότητας 7"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="asphalt_ready",
            field=models.BooleanField(
                default=False, help_text="7.6 Οδόστρωμα με ασφαλτικό σκυρόδεμα"
            ),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="check_date",
            field=models.DateField(help_text="7.6 Ημερομηνία ελέγχου"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="comments",
            field=models.TextField(blank=True, help_text="7.6 Σχόλια"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="curbs_ready",
            field=models.BooleanField(default=False, help_text="7.6 Ρείθρα"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="electricity_ready",
            field=models.BooleanField(default=False, help_text="7.6 Παροχή ηλεκτρικού ρεύματος"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="is_ready_for_submission_cycle",
            field=models.BooleanField(
                default=False,
                help_text="7.6 Συνολικό ΝΑΙ/ΟΧΙ ετοιμότητας για άνοιγμα κύκλου υποβολής (αυτόματο)",
            ),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="pavement_fill_ready",
            field=models.BooleanField(default=False, help_text="7.6 Επιχωμάτωση πεζοδρομίων"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="pavements_ready",
            field=models.BooleanField(default=False, help_text="7.6 Κράσπεδα"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="street_light_ready",
            field=models.BooleanField(default=False, help_text="7.6 Οδικός φωτισμός"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="telecom_ready",
            field=models.BooleanField(default=False, help_text="7.6 Τηλεπικοινωνίες"),
        ),
        migrations.AlterField(
            model_name="infrastructurecheck",
            name="water_ready",
            field=models.BooleanField(default=False, help_text="7.6 Υδατοπρομήθεια"),
        ),
    ]
