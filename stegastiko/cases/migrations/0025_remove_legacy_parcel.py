from django.db import migrations, models


class Migration(migrations.Migration):
    # Only help-text updates now. Dropping Parcel and ApprovedDesignPlot.legacy_parcel_id moved
    # to 0026: they must run after allocation 0003/0004 (which still read legacy_parcel_id and
    # reference Parcel), and this migration cannot gain a dependency on those because databases
    # that already applied it would then fail with InconsistentMigrationHistory. 0026 skips the
    # drops on databases where an earlier version of this migration already performed them.
    dependencies = [
        ("cases", "0024_merge_parcel_into_approved_design_plot"),
        ("allocation", "0002_allocation_approved_design_plot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="case",
            name="dls_application_date",
            field=models.DateField(
                blank=True,
                help_text="8.1 Ημερομηνία υποβολής αίτησης στο ΤΚΧ",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="case",
            name="dls_file_number",
            field=models.CharField(
                blank=True, help_text="8.1 Αριθμός φακέλου ΤΚΧ", max_length=64
            ),
        ),
        migrations.AlterField(
            model_name="case",
            name="dls_response_date",
            field=models.DateField(
                blank=True,
                help_text="8.1 Ημερομηνία απάντησης / ολοκλήρωσης ΤΚΧ",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="case",
            name="dls_comments",
            field=models.TextField(blank=True, help_text="8.1 Σχόλια"),
        ),
        migrations.AlterField(
            model_name="field",
            name="code",
            field=models.CharField(help_text="8.2 Κωδικός χωραφιού", max_length=64),
        ),
        migrations.AlterField(
            model_name="field",
            name="description",
            field=models.CharField(
                blank=True, help_text="8.2 Περιγραφή χωραφιού", max_length=255
            ),
        ),
        migrations.AlterField(
            model_name="valuationreferral",
            name="letter_date",
            field=models.DateField(
                blank=True,
                help_text="8.2 Ημερομηνία επιστολής / αίτησης προς ΤΚΧ",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="valuationreferral",
            name="reference_number",
            field=models.CharField(
                blank=True, help_text="8.2 Αριθμός φακέλου / αναφοράς", max_length=128
            ),
        ),
        migrations.AlterField(
            model_name="valuationreferral",
            name="response_date",
            field=models.DateField(
                blank=True, help_text="8.2 Ημερομηνία απάντησης ΤΚΧ", null=True
            ),
        ),
        migrations.AlterField(
            model_name="valuationreferral",
            name="comments",
            field=models.TextField(blank=True, help_text="8.2 Σχόλια"),
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="tkx_number",
            field=models.CharField(blank=True, help_text="8.1 Αρίθμηση ΤΚΧ", max_length=64),
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="title_deed_number",
            field=models.CharField(
                blank=True, help_text="8.2 Αριθμός τίτλου ιδιοκτησίας", max_length=64
            ),
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="parcel_number",
            field=models.CharField(
                blank=True, help_text="8.2 Αριθμός τεμαχίου", max_length=64
            ),
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="sheet_plan",
            field=models.CharField(blank=True, help_text="8.2 Φύλλο/Σχέδιο", max_length=64),
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="final_area_sqm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="8.2 Τελικό εμβαδόν (τ.μ.)",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="numbering_status",
            field=models.CharField(
                choices=[
                    ("design", "Αρίθμηση σχεδιασμού"),
                    ("tkx", "Αρίθμηση ΤΚΧ"),
                    ("title_deed", "Αρίθμηση βάσει τίτλου ιδιοκτησίας"),
                ],
                default="design",
                help_text="8.1 / 8.2 Κατάσταση αρίθμησης",
                max_length=16,
            ),
        ),
    ]
