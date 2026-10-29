import datetime
import django.db.models.deletion
from django.db import migrations, models


def assign_announcement(apps, schema_editor):
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for row in PlotApplication.objects.all():
        cycle = (
            SubmissionCycle.objects.filter(plots__community_id=row.community_id)
            .order_by("-published_at", "-announcement_date", "-pk")
            .first()
            or SubmissionCycle.objects.filter(communities=row.community_id)
            .order_by("-published_at", "-announcement_date", "-pk")
            .first()
        )
        if cycle is None:
            start = row.submitted_on or datetime.date(2026, 9, 1)
            cycle = SubmissionCycle.objects.create(
                announcement_date=start,
                submission_months=2,
                submission_end_date=start + datetime.timedelta(days=60),
            )
            cycle.communities.add(row.community_id)
        row.announcement_id = cycle.pk
        row.save(update_fields=["announcement"])


def restore_community(apps, schema_editor):
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    Community = apps.get_model("core", "Community")
    for row in PlotApplication.objects.select_related("announcement").all():
        cycle = row.announcement
        plot = cycle.plots.order_by("pk").first() if cycle else None
        if plot is not None:
            row.community_id = plot.community_id
        else:
            comm = cycle.communities.order_by("pk").first() if cycle else None
            if comm is not None:
                row.community_id = comm.pk
            else:
                first_comm = Community.objects.order_by("pk").first()
                if first_comm is not None:
                    row.community_id = first_comm.pk
        row.save(update_fields=["community"])


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0040_unique_fixed_publication_method"),
        ("allocation", "0010_beneficiary_lists"),
        ("plot_applications", "0021_objections_and_committee_rejection_stages"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="announcement",
            field=models.ForeignKey(
                help_text="Γνωστοποίηση υποβολής αιτήσεων (Ενότ. 4, 5)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="cases.submissioncycle",
            ),
        ),
        migrations.RunPython(assign_announcement, restore_community),
        migrations.RemoveField(
            model_name="plotapplication",
            name="community",
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="announcement",
            field=models.ForeignKey(
                help_text="Γνωστοποίηση υποβολής αιτήσεων (Ενότ. 4, 5)",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="cases.submissioncycle",
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="forfeited",
            field=models.BooleanField(
                default=False,
                help_text="Απόρριψη λόγω μη προσέλευσης / μη υπογραφής Συμφωνίας / μη πληρωμής (Ενότ. 8)",
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="forfeited_reason",
            field=models.TextField(
                blank=True,
                help_text="Αιτιολογία απόρριψης λόγω μη προσέλευσης / μη υπογραφής / μη πληρωμής (Ενότ. 8)",
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="forfeited_on",
            field=models.DateField(
                blank=True,
                help_text="Ημερομηνία απόρριψης λόγω μη προσέλευσης / μη υπογραφής / μη πληρωμής (Ενότ. 8)",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="application_stage",
            field=models.CharField(
                choices=[
                    ("collection", "Συλλογή πληροφοριών και πιστοποιητικών"),
                    ("examination", "Εξέταση επιλεξιμότητας"),
                    ("prioritization", "Επιλογή και προτεραιοποίηση"),
                    ("objections", "Προκαταρκτικός κατάλογος — Ενστάσεις"),
                    ("objections_committee", "Επιτροπή Εξέτασης Ενστάσεων"),
                    ("lottery", "Στάδιο κλήρωσης"),
                    ("agreement", "Υπογραφή συμφωνίας και πληρωμή"),
                    ("completed", "Ολοκλήρωση"),
                    ("rejected", "Απόρριψη από λειτουργό"),
                    ("committee_rejected", "Απόρριψη από Επιτροπή"),
                    ("forfeited", "Απόρριψη — μη προσέλευση/υπογραφή/πληρωμή"),
                ],
                default="collection",
                help_text="Στάδιο αίτησης",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="Objection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "submitted_on",
                    models.DateField(
                        help_text="Ημερομηνία υποβολής ένστασης (εντός 21 ημερών από τη λήψη της επιστολής, Ενότ. 7)"
                    ),
                ),
                (
                    "objection_type",
                    models.CharField(
                        choices=[
                            ("rejection", "Διαφωνία με την απόρριψη (Ενότ. 7(α))"),
                            ("rank", "Διαφωνία με τη σειρά κατάταξης (Ενότ. 7(β))"),
                        ],
                        help_text="Είδος ένστασης (Ενότ. 7)",
                        max_length=16,
                    ),
                ),
                ("grounds", models.TextField(help_text="Αιτιολόγηση ένστασης / Έκθεση Γεγονότων (Ενότ. 7)")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Εκκρεμεί εξέταση"),
                            ("upheld", "Ικανοποιήθηκε"),
                            ("dismissed", "Δεν ικανοποιήθηκε"),
                        ],
                        default="pending",
                        help_text="Απόφαση Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
                        max_length=16,
                    ),
                ),
                (
                    "decided_on",
                    models.DateField(
                        blank=True,
                        help_text="Ημερομηνία απόφασης Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
                        null=True,
                    ),
                ),
                (
                    "decision_notes",
                    models.TextField(
                        blank=True,
                        help_text="Σκεπτικό / απόφαση Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
                    ),
                ),
                (
                    "outcome_notified_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Ημερομηνία/ώρα αποστολής email απόφασης ένστασης (Ενότ. 7)",
                        null=True,
                    ),
                ),
                (
                    "application",
                    models.ForeignKey(
                        help_text="Αίτηση για την οποία υποβλήθηκε η ένσταση (Ενότ. 7)",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="objections",
                        to="plot_applications.plotapplication",
                    ),
                ),
                (
                    "preliminary_entry",
                    models.ForeignKey(
                        blank=True,
                        help_text="Εγγραφή στον Προκαταρκτικό Κατάλογο κατά την υποβολή της ένστασης (Ενότ. 6, 7)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="objections",
                        to="allocation.rankingentry",
                    ),
                ),
            ],
            options={
                "ordering": ("submitted_on", "id"),
            },
        ),
        migrations.CreateModel(
            name="PendingRequirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "description",
                    models.CharField(
                        help_text="Περιγραφή στοιχείου/πιστοποιητικού που πρέπει να προσκομισθεί",
                        max_length=500,
                    ),
                ),
                (
                    "is_fulfilled",
                    models.BooleanField(
                        default=False,
                        help_text="Έχει προσκομισθεί / ελεγχθεί",
                    ),
                ),
                (
                    "requested_on",
                    models.DateField(
                        auto_now_add=True,
                        help_text="Ημερομηνία που ζητήθηκε",
                    ),
                ),
                (
                    "fulfilled_on",
                    models.DateField(
                        blank=True,
                        help_text="Ημερομηνία προσκόμισης",
                        null=True,
                    ),
                ),
                (
                    "application",
                    models.ForeignKey(
                        help_text="Αίτηση από την οποία ζητούνται επιπλέον στοιχεία (Ενότ. 7)",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_requirements",
                        to="plot_applications.plotapplication",
                    ),
                ),
                (
                    "objection",
                    models.ForeignKey(
                        blank=True,
                        help_text="Σχετική ένσταση στο πλαίσιο της οποίας ζητούνται τα στοιχεία (Ενότ. 7)",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_requirements",
                        to="plot_applications.objection",
                    ),
                ),
            ],
            options={
                "ordering": ("is_fulfilled", "id"),
            },
        ),
    ]
