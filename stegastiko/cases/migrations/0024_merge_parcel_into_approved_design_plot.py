from django.db import migrations, models
import django.db.models.deletion


DIVISION_PLOT = "division_plot"

# 8.2 fields carried by the legacy Parcel, as (ApprovedDesignPlot field, Parcel field).
PARCEL_FIELD_MAP = (
    ("tkx_number", "tkx_lot_number"),
    ("sheet_plan", "sheet_plan"),
    ("final_area_sqm", "final_area_sqm"),
    ("field_id", "field_id"),
    ("valuation_referral_id", "valuation_referral_id"),
    ("owner_person_id", "owner_person_id"),
    ("lot_number_in_field", "lot_number_in_field"),
    ("kotsiani_number", "kotsiani_number"),
    ("has_separate_title", "has_separate_title"),
    ("valuation_amount", "valuation_amount"),
    ("disposal_price", "disposal_price"),
    ("comments", "comments"),
)


def _is_empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _numbering_status(current, tkx_number):
    # Never downgrade a title-deed numbering; promote "design" to "tkx" once a ΤΚΧ number exists.
    if current == "title_deed":
        return current
    return "tkx" if tkx_number else (current or "design")


def copy_parcels(apps, schema_editor):
    """Merge every legacy 8.2 Parcel into the 7.3 division-plot row of the same lot.

    A Parcel matches the oldest not-yet-merged ApprovedDesignPlot of the same case with
    plot_type=division_plot and design_number == Parcel.design_lot_number. Parcel values win
    for the 8.2 fields; 7.3 values are kept where the parcel is empty. Only parcels without a
    matching 7.3 row get a new ApprovedDesignPlot. Either way legacy_parcel_id records the
    link, which allocation 0003 uses to repoint Allocation.parcel.
    """
    Parcel = apps.get_model("cases", "Parcel")
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    for parcel in Parcel.objects.order_by("id").iterator():
        design_number = (parcel.design_lot_number or "").strip()
        plot = None
        if design_number:
            plot = (
                ApprovedDesignPlot.objects.filter(
                    case_id=parcel.case_id,
                    plot_type=DIVISION_PLOT,
                    design_number=design_number,
                    legacy_parcel_id__isnull=True,
                )
                .order_by("id")
                .first()
            )
        if plot is None:
            plot = ApprovedDesignPlot(
                case_id=parcel.case_id,
                plot_type=DIVISION_PLOT,
                design_number=parcel.design_lot_number,
                numbering_status="design",
                created_at=parcel.created_at,
            )
        for plot_field, parcel_field in PARCEL_FIELD_MAP:
            value = getattr(parcel, parcel_field)
            if not _is_empty(value):
                setattr(plot, plot_field, value)
        plot.legacy_parcel_id = parcel.pk
        plot.numbering_status = _numbering_status(plot.numbering_status, plot.tkx_number)
        plot.save()


def _migration_created_plot_ids(apps, plot_ids):
    """Plots without an audit CREATE entry were inserted by this migration, not by a user.

    Historical models bypass core.audit's post_save handler, so rows created by copy_parcels
    (or restored by cases 0026's reverse) never get an ActionHistory CREATE record.
    """
    ActionHistory = apps.get_model("core", "ActionHistory")
    audited = set(
        ActionHistory.objects.filter(
            entity_type="ApprovedDesignPlot",
            action="CREATE",
            entity_id__in=[str(pk) for pk in plot_ids],
        ).values_list("entity_id", flat=True)
    )
    return {pk for pk in plot_ids if str(pk) not in audited}


def restore_parcels(apps, schema_editor):
    """Reverse of copy_parcels.

    Every plot carrying a legacy_parcel_id is written back to the Parcel with that id (created
    if missing), so 8.2 edits made after the merge survive. When reversing from beyond cases
    0026, the 0026 reverse has already recreated the Parcels and set legacy_parcel_id.
    Plots this migration created are then deleted; plots that already existed as 7.3 rows are
    kept (their 8.2 columns disappear with the RemoveField reversals that follow).

    Limitation: for merged rows, 7.3 values that copy_parcels overwrote with parcel data
    (tkx_number, sheet_plan, final_area_sqm, numbering_status) are not restored to their
    pre-merge values - they stay as merged.
    """
    Parcel = apps.get_model("cases", "Parcel")
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    plots = list(ApprovedDesignPlot.objects.exclude(legacy_parcel_id=None).order_by("id"))
    for plot in plots:
        values = {
            parcel_field: getattr(plot, plot_field) for plot_field, parcel_field in PARCEL_FIELD_MAP
        }
        for parcel_field in ("tkx_lot_number", "sheet_plan", "lot_number_in_field",
                             "kotsiani_number", "has_separate_title", "comments"):
            values[parcel_field] = values[parcel_field] or ""
        values.update(case_id=plot.case_id, design_lot_number=plot.design_number or "")
        parcel = Parcel.objects.filter(pk=plot.legacy_parcel_id).first()
        if parcel is None:
            Parcel.objects.create(pk=plot.legacy_parcel_id, created_at=plot.created_at, **values)
        else:
            for name, value in values.items():
                setattr(parcel, name, value)
            parcel.save()
    created_ids = _migration_created_plot_ids(apps, [plot.pk for plot in plots])
    ApprovedDesignPlot.objects.filter(pk__in=created_ids).delete()


class Migration(migrations.Migration):
    # Non-atomic so that, on PostgreSQL, the RunPython (atomic on its own) commits before the
    # reverse RemoveField operations ALTER cases_approveddesignplot; otherwise the reverse
    # fails with "cannot ALTER TABLE ... because it has pending trigger events".
    atomic = False

    dependencies = [
        ("cases", "0023_section_7_6_works_checks"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="approveddesignplot",
            name="comments",
            field=models.TextField(blank=True, help_text="8.2 Σχόλια οικοπέδου"),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="disposal_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                editable=False,
                help_text="8.2 Τιμή διάθεσης (αυτόματα 25% της αξίας)",
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="field",
            field=models.ForeignKey(
                blank=True,
                help_text="8.2 Χωράφι προέλευσης (προαιρετικό)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_design_plots",
                to="cases.field",
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="has_separate_title",
            field=models.CharField(
                blank=True,
                choices=[("yes", "ΝΑΙ"), ("no", "ΟΧΙ")],
                help_text="8.2 Υπάρχει ξεχωριστός Τίτλος Ιδιοκτησίας;",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="kotsiani_number",
            field=models.CharField(
                blank=True, help_text="8.2 Αριθμός κοτσιάνι (προαιρετικός)", max_length=64
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="legacy_parcel_id",
            field=models.BigIntegerField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="lot_number_in_field",
            field=models.CharField(
                blank=True,
                help_text="8.2 Νούμερο εντός χωραφιού (προαιρετικό)",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="owner_person_id",
            field=models.IntegerField(
                blank=True, help_text="8.2 Ιδιοκτήτης οικοπέδου", null=True
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="valuation_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="8.2 Αξία για υπολογισμό",
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="approveddesignplot",
            name="valuation_referral",
            field=models.ForeignKey(
                blank=True,
                help_text="8.2 Παραπομπή προς Διευθυντή ΤΚΧ που καθόρισε την αξία",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_design_plots",
                to="cases.valuationreferral",
            ),
        ),
        migrations.RunPython(copy_parcels, restore_parcels, atomic=True),
    ]
