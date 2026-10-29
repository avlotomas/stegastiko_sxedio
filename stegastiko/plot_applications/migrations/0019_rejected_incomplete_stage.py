from django.db import migrations, models


def move_rejected_to_application_stage(apps, schema_editor):
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    for app in PlotApplication.objects.filter(
        models.Q(incomplete_rejected=True) | models.Q(completeness_result="rejected")
    ).iterator():
        PlotApplication.objects.filter(pk=app.pk).update(
            incomplete_rejected=True,
            completeness_result="incomplete",
            documents_completeness="incomplete",
            application_stage="rejected",
            plot_allocation_status="not_allocated",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0018_incomplete_rejection"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plotapplication",
            name="application_stage",
            field=models.CharField(
                choices=[
                    ("collection", "Συλλογή πληροφοριών και πιστοποιητικών"),
                    ("examination", "Εξέταση επιλεξιμότητας"),
                    ("prioritization", "Επιλογή και προτεραιοποίηση"),
                    ("completed", "Ολοκλήρωση"),
                    ("rejected", "Απόρριψη"),
                ],
                default="collection",
                help_text="Στάδιο εξέτασης της αίτησης (συλλογή πληροφοριών και πιστοποιητικών, εξέταση επιλεξιμότητας, επιλογή και προτεραιοποίηση, ολοκλήρωση, απόρριψη)",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="completeness_result",
            field=models.CharField(
                choices=[("complete", "Πλήρης"), ("incomplete", "Ελλιπής")],
                default="incomplete",
                help_text="Κατάσταση πληρότητας της αίτησης (υποχρεωτικά πεδία, υπογραφές, δικαιολογητικά, Ενότ. 5, 20.2)",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="incomplete_rejected",
            field=models.BooleanField(
                default=False,
                help_text="Απόρριψη της αίτησης από τον λειτουργό (Ενότ. 5(β), 6, 20)",
            ),
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="incomplete_rejected_on",
            field=models.DateField(
                blank=True,
                help_text="Ημερομηνία απόρριψης της αίτησης",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="incomplete_rejection_reason",
            field=models.TextField(
                blank=True,
                help_text="Λόγος απόρριψης της αίτησης (Ενότ. 5(β), 6, 20)",
            ),
        ),
        migrations.RunPython(move_rejected_to_application_stage, migrations.RunPython.noop),
    ]
