from django.db import migrations, models


def populate_auto_result_and_reopen_non_beneficiaries(apps, schema_editor):
    """The software result is the stored result (no overrides existed yet).

    Complete applications judged «ΜΗ ΔΙΚΑΙΟΥΧΟΣ» now remain open in stage 3 (they appear in the
    prioritization list with their reason) unless they already belong to a finalized ranking list.
    """
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    RankingEntry = apps.get_model("allocation", "RankingEntry")
    Allocation = apps.get_model("allocation", "Allocation")
    closed_ids = set(
        RankingEntry.objects.filter(
            models.Q(ranking_list__finalized_at__isnull=False) | models.Q(ranking_list__list_type="final")
        ).values_list("application_id", flat=True)
    ) | set(
        Allocation.objects.filter(status="active", application_id__isnull=False).values_list(
            "application_id", flat=True
        )
    )
    for app in PlotApplication.objects.all().iterator():
        values = {"eligibility_auto_result": app.eligibility_result}
        if (
            app.application_stage == "completed"
            and app.eligibility_result == "fail"
            and app.pk not in closed_ids
        ):
            values.update(application_stage="prioritization", plot_allocation_status="pending")
        PlotApplication.objects.filter(pk=app.pk).update(**values)


class Migration(migrations.Migration):

    dependencies = [
        ("allocation", "0009_application_to_plot_application"),
        ("plot_applications", "0016_plotapplication_stage_and_plot_allocation_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="eligibility_auto_result",
            field=models.CharField(
                choices=[
                    ("pass", "Κατ' αρχήν πληροί"),
                    ("fail", "Δεν πληροί"),
                    ("pending", "Εκκρεμεί έλεγχος"),
                ],
                default="pending",
                help_text="Αποτέλεσμα του αυτόματου ελέγχου επιλεξιμότητας από το λογισμικό, πριν από τυχόν χειροκίνητη αλλαγή (Ενότ. 10, 20)",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="eligibility_override",
            field=models.CharField(
                blank=True,
                choices=[("pass", "ΔΙΚΑΙΟΥΧΟΣ"), ("fail", "ΜΗ ΔΙΚΑΙΟΥΧΟΣ")],
                help_text="Χειροκίνητη αλλαγή του αποτελέσματος του λογισμικού κατά πόσο ο αιτητής είναι δικαιούχος (Ενότ. 6)",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="eligibility_override_reason",
            field=models.TextField(
                blank=True,
                help_text="Αιτιολογία της χειροκίνητης αλλαγής του αποτελέσματος επιλεξιμότητας (Ενότ. 6)",
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="priority_rank",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Θέση στον κατάλογο προτεραιοποίησης της Κοινότητας μετά από χειροκίνητη αλλαγή σειράς (Ενότ. 6, 11)",
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_auto_result_and_reopen_non_beneficiaries, migrations.RunPython.noop
        ),
    ]
