from django.db import migrations, models


def populate_stage_and_allocation(apps, schema_editor):
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    Allocation = apps.get_model("allocation", "Allocation")
    active_allocated_app_ids = set(
        Allocation.objects.filter(status="active", application_id__isnull=False).values_list(
            "application_id", flat=True
        )
    )
    for app in PlotApplication.objects.all().iterator():
        is_complete = (
            app.completeness_result == "complete" and app.documents_completeness == "complete"
        )
        if not is_complete:
            stage = "collection"
            plot_status = "pending"
        elif app.eligibility_result == "pending":
            stage = "examination"
            plot_status = "pending"
        elif app.eligibility_result == "fail":
            stage = "completed"
            plot_status = "not_allocated"
        elif app.pk in active_allocated_app_ids:
            stage = "completed"
            plot_status = "allocated"
        else:
            stage = "prioritization"
            plot_status = "pending"
        PlotApplication.objects.filter(pk=app.pk).update(
            application_stage=stage,
            plot_allocation_status=plot_status,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("allocation", "0009_application_to_plot_application"),
        ("plot_applications", "0015_plotapplication_resides_in_controlled_areas"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="application_stage",
            field=models.CharField(
                choices=[
                    ("collection", "Συλλογή πληροφοριών και πιστοποιητικών"),
                    ("examination", "Εξέταση επιλεξιμότητας"),
                    ("prioritization", "Επιλογή και προτεραιοποίηση"),
                    ("completed", "Ολοκλήρωση"),
                ],
                default="collection",
                help_text="Στάδιο εξέτασης της αίτησης (συλλογή πληροφοριών και πιστοποιητικών, εξέταση επιλεξιμότητας, επιλογή και προτεραιοποίηση, ολοκλήρωση)",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="plot_allocation_status",
            field=models.CharField(
                choices=[
                    ("pending", "Εκκρεμεί"),
                    ("allocated", "Πήρε οικόπεδο"),
                    ("not_allocated", "Δεν πήρε οικόπεδο"),
                ],
                default="pending",
                help_text="Κατάσταση παραχώρησης οικοπέδου (Εκκρεμεί, Πήρε οικόπεδο, Δεν πήρε οικόπεδο — Ενότ. 8, 9)",
                max_length=16,
            ),
        ),
        migrations.RunPython(populate_stage_and_allocation, migrations.RunPython.noop),
    ]
