from django.db import migrations, models


def set_unpublished_cycles_to_details(apps, schema_editor):
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    SubmissionCycle.objects.filter(
        published_at__isnull=True, stage="submission"
    ).update(stage="details")


def revert_details_cycles_to_submission(apps, schema_editor):
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    SubmissionCycle.objects.filter(stage="details").update(stage="submission")


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0042_submissioncycle_final_list_stage"),
    ]

    operations = [
        migrations.AddField(
            model_name="submissioncycle",
            name="submission_closed_early",
            field=models.BooleanField(
                default=False,
                help_text="Η περίοδος υποβολής αιτήσεων έκλεισε πριν από τη λήξη της προθεσμίας (Ενότ. 4, 5) κατόπιν αποδοχής προειδοποίησης",
            ),
        ),
        migrations.AlterField(
            model_name="submissioncycle",
            name="objections_closed_on",
            field=models.DateField(
                blank=True,
                help_text="Κλείσιμο περιόδου ενστάσεων (Ενότ. 7(α)): λήξη των 21 ημερών ή μετάβαση στο Στάδιο 5 με αποδοχή προειδοποίησης",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="submissioncycle",
            name="stage",
            field=models.CharField(
                choices=[
                    ("details", "1. Στοιχεία γνωστοποίησης"),
                    ("submission", "2. Υποβολή αιτήσεων"),
                    ("applications_committee", "3. Επιτροπή Εξέτασης Αιτήσεων"),
                    ("objections_committee", "4. Ενστάσεις"),
                    ("final_list", "5. Τελικός Κατάλογος Δικαιούχων"),
                    ("lottery", "6. Στάδιο κλήρωσης"),
                    ("agreements", "7. Υπογραφή συμφωνίας και πληρωμή"),
                    ("closed", "Ολοκλήρωση γνωστοποίησης"),
                ],
                default="details",
                help_text="Στάδιο διαδικασίας γνωστοποίησης (1–7)",
                max_length=32,
            ),
        ),
        migrations.RunPython(
            set_unpublished_cycles_to_details,
            revert_details_cycles_to_submission,
        ),
    ]
