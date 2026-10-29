from django.db import migrations, models


def keep_single_community_plots(apps, schema_editor):
    """Ensure every existing announcement offers plots of at most one community."""
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for cycle in SubmissionCycle.objects.all():
        plots = list(cycle.plots.order_by("pk").all())
        if not plots:
            continue
        first_community_id = plots[0].community_id
        extra = [p.pk for p in plots if p.community_id != first_community_id]
        if extra:
            cycle.plots.remove(*extra)


def restore_communities_from_plots(apps, schema_editor):
    """Reverse: populate communities M2M from the offered plots' communities (or default community)."""
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    Community = apps.get_model("core", "Community")
    default_comm = Community.objects.order_by("pk").first()
    for cycle in SubmissionCycle.objects.all():
        community_ids = list(cycle.plots.values_list("community_id", flat=True).distinct())
        if not community_ids and default_comm is not None:
            community_ids = [default_comm.pk]
        if community_ids:
            cycle.communities.set(community_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0040_unique_fixed_publication_method"),
        ("plot_applications", "0022_announcement_objections_pending_requirements"),
    ]

    operations = [
        migrations.RunPython(keep_single_community_plots, restore_communities_from_plots),
        migrations.RemoveField(
            model_name="submissioncycle",
            name="communities",
        ),
        migrations.AlterField(
            model_name="submissioncycle",
            name="plots",
            field=models.ManyToManyField(
                blank=True,
                help_text="9.1 Διαθέσιμα οικόπεδα μίας Κοινότητας που προσφέρει η γνωστοποίηση",
                related_name="submission_cycles",
                to="plots.plot",
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="stage",
            field=models.CharField(
                choices=[
                    ("submission", "1. Υποβολή αιτήσεων"),
                    ("applications_committee", "2. Επιτροπή Εξέτασης Αιτήσεων"),
                    ("objections_committee", "3. Επιτροπή Εξέτασης Ενστάσεων"),
                    ("lottery", "4. Στάδιο κλήρωσης"),
                    ("agreements", "5. Υπογραφή συμφωνίας και πληρωμή"),
                    ("closed", "Ολοκλήρωση γνωστοποίησης"),
                ],
                default="submission",
                help_text="Στάδιο διαδικασίας γνωστοποίησης (1–5)",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="applications_committee_date",
            field=models.DateField(
                blank=True,
                help_text="Ημερομηνία συνεδρίας Επιτροπής Εξέτασης Αιτήσεων (Ενότ. 6)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="objections_committee_date",
            field=models.DateField(
                blank=True,
                help_text="Ημερομηνία συνεδρίας Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="agreement_location",
            field=models.CharField(
                blank=True,
                help_text="Τόπος προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 9, 12, 15)",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="agreement_appointment_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Προεπιλεγμένη ημερομηνία/ώρα προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 9, 12, 15)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="agreement_deadline",
            field=models.DateField(
                blank=True,
                help_text="Προεπιλεγμένη προθεσμία προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 8, 9)",
                null=True,
            ),
        ),
    ]
