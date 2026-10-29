import django.db.models.deletion
from django.db import migrations, models


def dedupe_ranking_lists_per_cycle(apps, schema_editor):
    RankingList = apps.get_model("allocation", "RankingList")
    seen = set()
    for rlist in RankingList.objects.order_by("-id"):
        key = (rlist.submission_cycle_id, rlist.list_type)
        if key in seen:
            rlist.delete()
        else:
            seen.add(key)


def restore_community_fks(apps, schema_editor):
    RankingList = apps.get_model("allocation", "RankingList")
    Lottery = apps.get_model("allocation", "Lottery")
    Community = apps.get_model("core", "Community")
    default_comm = Community.objects.order_by("pk").first()
    for rlist in RankingList.objects.select_related("submission_cycle").all():
        plot = rlist.submission_cycle.plots.order_by("pk").first()
        rlist.community_id = plot.community_id if plot else (default_comm.pk if default_comm else None)
        rlist.save(update_fields=["community"])
    for lottery in Lottery.objects.select_related("submission_cycle").all():
        plot = lottery.submission_cycle.plots.order_by("pk").first()
        lottery.community_id = plot.community_id if plot else (default_comm.pk if default_comm else None)
        lottery.save(update_fields=["community"])


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0010_beneficiary_lists"),
        ("cases", "0041_submissioncycle_workflow_and_plots_only"),
        ("plot_applications", "0022_announcement_objections_pending_requirements"),
    ]

    operations = [
        migrations.RunPython(dedupe_ranking_lists_per_cycle, restore_community_fks),
        migrations.AlterUniqueTogether(
            name="rankinglist",
            unique_together={("submission_cycle", "list_type")},
        ),
        migrations.RemoveField(
            model_name="rankinglist",
            name="community",
        ),
        migrations.AlterField(
            model_name="rankinglist",
            name="plots_count",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Διαθέσιμα οικόπεδα της γνωστοποίησης κατά την έκδοση του Τελικού Καταλόγου (Ενότ. 8)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="rankingentry",
            name="notified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Ημερομηνία/ώρα αποστολής επιστολής/email στον αιτητή (Ενότ. 6, 7)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="rankingentry",
            name="receipt_confirmed_on",
            field=models.DateField(
                blank=True,
                help_text="Ημερομηνία επιβεβαίωσης λήψης από τον αιτητή εντός 5 ημερών (Ενότ. 6)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="rankingentry",
            name="objection_deadline",
            field=models.DateField(
                blank=True,
                help_text="Προθεσμία υποβολής ένστασης του αιτητή (21 ημέρες από τη λήψη/αποστολή, Ενότ. 6, 7)",
                null=True,
            ),
        ),
        migrations.RemoveField(
            model_name="lottery",
            name="community",
        ),
        migrations.AlterField(
            model_name="lottery",
            name="lottery_type",
            field=models.CharField(
                choices=[
                    ("rank_tie", "Κλήρωση ισοψηφίας κατάταξης"),
                    ("parcel_allocation", "Κλήρωση κατανομής οικοπέδων"),
                ],
                default="parcel_allocation",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="lottery",
            name="lottery_date",
            field=models.DateTimeField(
                help_text="Ημερομηνία και ώρα διεξαγωγής κλήρωσης (Ενότ. 9)"
            ),
        ),
        migrations.AddField(
            model_name="lottery",
            name="completed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Ολοκλήρωση κλήρωσης οικοπέδων (Ενότ. 9)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="allocation",
            name="replaces",
            field=models.ForeignKey(
                blank=True,
                help_text="Προηγούμενη κατανομή που αντικαταστάθηκε από επιλαχόντα (Ενότ. 8)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="replacements",
                to="allocation.allocation",
            ),
        ),
        migrations.AddField(
            model_name="allocation",
            name="runner_up_justification",
            field=models.TextField(
                blank=True,
                help_text="Αιτιολογία επιλογής επιλαχόντα όταν δεν επιλέγεται ο αμέσως επόμενος κατά σειρά (Ενότ. 8)",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Τιμή διάθεσης οικοπέδου (25% Γενικής Εκτίμησης, Ενότ. 13, 15)",
                max_digits=14,
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("paid", "ΠΛΗΡΩΘΗΚΕ"),
                    ("pending", "ΕΚΚΡΕΜΕΙ"),
                    ("unpaid", "ΜΗ ΠΛΗΡΩΜΕΝΗ"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="agreement",
            name="appointment_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Ημερομηνία και ώρα προσέλευσης για υπογραφή και πληρωμή (Ενότ. 9, 12, 15)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="agreement",
            name="deadline",
            field=models.DateField(
                blank=True,
                help_text="Προθεσμία προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 8, 9)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="agreement",
            name="invited_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Ημερομηνία/ώρα αποστολής πρόσκλησης υπογραφής (Ενότ. 9)",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="agreement",
            name="status",
            field=models.CharField(
                choices=[
                    ("signed", "ΥΠΟΓΡΑΦΗΚΕ"),
                    ("not_signed", "ΔΕΝ ΥΠΟΓΡΑΦΗΚΕ"),
                    ("no_show", "ΜΗ ΠΡΟΣΕΛΕΥΣΗ"),
                ],
                default="not_signed",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="AgreementTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "name",
                    models.CharField(
                        help_text="Ονομασία προτύπου Συμφωνίας Παραχώρησης (Παράρτημα 4, Ενότ. 12)",
                        max_length=255,
                    ),
                ),
                (
                    "version",
                    models.CharField(
                        blank=True,
                        help_text="Έκδοση προτύπου",
                        max_length=64,
                    ),
                ),
                (
                    "template_file",
                    models.FileField(
                        help_text="Αρχείο Word (.docx) με πεδία {{placeholders}} (Παράρτημα 4)",
                        upload_to="agreement_templates/",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Ενεργό πρότυπο για παραγωγή Συμφωνιών",
                    ),
                ),
            ],
            options={
                "ordering": ("-is_active", "-id"),
            },
        ),
    ]
