"""Clean up after the original 0024 and finish removing the legacy Parcel model.

1. ``dedupe_division_plots`` - the first version of 0024 created a *new* ApprovedDesignPlot
   for every Parcel, even when the case already had a 7.3 division-plot row with the same
   design number. Each such duplicate pair is merged into the original 7.3 row and the copy is
   deleted (allocations, attachments and communications are repointed first).

   How a pair is recognised:
   * the *copy* is a row with no ActionHistory CREATE entry - migrations use historical
     models, which bypass core.audit, so rows inserted by 0024 never got one, while rows
     created through the application always do;
   * the *original* is an audited row of the same case, plot_type=division_plot and
     design_number;
   * while ``legacy_parcel_id`` still exists (databases that stopped between the old 0024 and
     this migration) it is required as well: copy has one, original does not.
   Copies are paired with originals in id order (same rule as the fixed 0024). On conflicting
   non-empty values the row updated more recently wins; empty values are filled from the
   other row. Groups with no audited original are left untouched.

2. ``Parcel`` and ``ApprovedDesignPlot.legacy_parcel_id`` are dropped here (moved from 0025,
   see the note there). Databases on which the earlier 0025 already dropped them only get the
   state change.

The migration is non-atomic (each RunPython is atomic on its own) so that on PostgreSQL the
data changes are committed before the ALTER/DROP statements - mixing them in one transaction
fails with "cannot ALTER TABLE ... because it has pending trigger events".

Reverse: the dedupe is not undone (noop) - the merged row is a superset of both rows and the
original pairing cannot be reconstructed. The Parcel table and legacy_parcel_id column are
recreated and one Parcel is restored for every division plot that holds 8.2 data, has
allocations or was created by 0024, so allocation 0003 and cases 0024 can be reversed.
Limitation: restored Parcels get new primary keys (the original ids were lost when the
column was dropped).
"""

from decimal import Decimal

from django.db import migrations
from django.utils import timezone

DIVISION_PLOT = "division_plot"
PLOT_TABLE = "cases_approveddesignplot"
PARCEL_TABLE = "cases_parcel"
LEGACY_COLUMN = "legacy_parcel_id"

# Value columns merged from the duplicate into the kept row.
MERGE_FIELDS = (
    "plot_type_other",
    "tkx_number",
    "title_deed_number",
    "parcel_number",
    "sheet_plan",
    "final_area_sqm",
    "owner_person_id",
    "lot_number_in_field",
    "kotsiani_number",
    "has_separate_title",
    "valuation_amount",
    "comments",
    "field_id",
    "valuation_referral_id",
)
# Columns added by 0024 for 8.2 - a plot with any of them set carried legacy Parcel data.
PARCEL_ONLY_FIELDS = (
    "owner_person_id",
    "lot_number_in_field",
    "kotsiani_number",
    "has_separate_title",
    "valuation_amount",
    "comments",
    "field_id",
    "valuation_referral_id",
)
NUMBERING_RANK = {"design": 0, "tkx": 1, "title_deed": 2}


def _table_exists(schema_editor, table):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return table in connection.introspection.table_names(cursor)


def _column_exists(schema_editor, table, column):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if table not in connection.introspection.table_names(cursor):
            return False
        description = connection.introspection.get_table_description(cursor, table)
    return any(col.name == column for col in description)


def _is_empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _audited_plot_ids(apps):
    ActionHistory = apps.get_model("core", "ActionHistory")
    return {
        int(entity_id)
        for entity_id in ActionHistory.objects.filter(
            entity_type="ApprovedDesignPlot", action="CREATE"
        ).values_list("entity_id", flat=True)
        if entity_id.isdigit()
    }


def _merged_values(keeper, extra):
    newer, older = (keeper, extra)
    if (extra["updated_at"] or extra["created_at"]) > (keeper["updated_at"] or keeper["created_at"]):
        newer, older = extra, keeper
    values = {}
    for name in MERGE_FIELDS:
        value = newer[name]
        values[name] = older[name] if _is_empty(value) else value
    valuation = values["valuation_amount"]
    values["disposal_price"] = (
        None if valuation is None else (valuation * Decimal("0.25")).quantize(Decimal("0.01"))
    )
    status = max(
        (keeper["numbering_status"] or "design", extra["numbering_status"] or "design"),
        key=lambda s: NUMBERING_RANK.get(s, 0),
    )
    if status == "design" and values["tkx_number"]:
        status = "tkx"
    values["numbering_status"] = status
    values["updated_at"] = timezone.now()
    return values


def dedupe_division_plots(apps, schema_editor):
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Allocation = apps.get_model("allocation", "Allocation")
    Attachment = apps.get_model("core", "Attachment")
    Communication = apps.get_model("core", "Communication")
    ContentType = apps.get_model("contenttypes", "ContentType")

    has_legacy = _column_exists(schema_editor, PLOT_TABLE, LEGACY_COLUMN)
    columns = ["id", "case_id", "design_number", "numbering_status", "created_at", "updated_at"]
    columns += list(MERGE_FIELDS)
    if has_legacy:
        columns.append("legacy_parcel_id")

    groups = {}
    rows = (
        ApprovedDesignPlot.objects.filter(plot_type=DIVISION_PLOT)
        .exclude(design_number="")
        .order_by("id")
        .values(*columns)
    )
    for row in rows:
        key = (row["case_id"], row["design_number"].strip())
        if key[1]:
            groups.setdefault(key, []).append(row)

    audited = _audited_plot_ids(apps)
    plot_ct = ContentType.objects.filter(app_label="cases", model="approveddesignplot").first()
    alias = schema_editor.connection.alias
    merged = 0
    for (case_id, design_number), group in sorted(groups.items(), key=lambda item: item[1][0]["id"]):
        if len(group) < 2:
            continue
        copies = [
            r for r in group
            if r["id"] not in audited and (not has_legacy or r["legacy_parcel_id"] is not None)
        ]
        originals = [
            r for r in group
            if r["id"] in audited and (not has_legacy or r["legacy_parcel_id"] is None)
        ]
        for keeper, extra in zip(originals, copies):
            values = _merged_values(keeper, extra)
            Allocation.objects.filter(parcel_id=extra["id"]).update(parcel_id=keeper["id"])
            if plot_ct is not None:
                for model in (Attachment, Communication):
                    model.objects.filter(content_type=plot_ct, object_id=extra["id"]).update(
                        object_id=keeper["id"]
                    )
            ApprovedDesignPlot.objects.filter(pk=extra["id"])._raw_delete(alias)
            if has_legacy:
                values["legacy_parcel_id"] = extra["legacy_parcel_id"]
            ApprovedDesignPlot.objects.filter(pk=keeper["id"]).update(**values)
            merged += 1
            print(
                f"\n  cases 0026: merged duplicate division plot {extra['id']} into "
                f"{keeper['id']} (case {case_id}, design number {design_number!r})",
                end="",
            )
    if merged:
        print(f"\n  cases 0026: {merged} duplicate division plot(s) merged", end="")


def restore_parcels(apps, schema_editor):
    """Reverse helper: recreate Parcels from division plots (see module docstring)."""
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Parcel = apps.get_model("cases", "Parcel")
    Allocation = apps.get_model("allocation", "Allocation")
    audited = _audited_plot_ids(apps)
    allocated = set(Allocation.objects.values_list("parcel_id", flat=True))
    plots = ApprovedDesignPlot.objects.filter(
        plot_type=DIVISION_PLOT, legacy_parcel_id__isnull=True
    ).order_by("id")
    for plot in plots:
        has_parcel_data = any(not _is_empty(getattr(plot, name)) for name in PARCEL_ONLY_FIELDS)
        if not (has_parcel_data or plot.pk in allocated or plot.pk not in audited):
            continue
        parcel = Parcel.objects.create(
            case_id=plot.case_id,
            design_lot_number=plot.design_number or "",
            tkx_lot_number=plot.tkx_number or "",
            sheet_plan=plot.sheet_plan or "",
            final_area_sqm=plot.final_area_sqm,
            field_id=plot.field_id,
            valuation_referral_id=plot.valuation_referral_id,
            owner_person_id=plot.owner_person_id,
            lot_number_in_field=plot.lot_number_in_field or "",
            kotsiani_number=plot.kotsiani_number or "",
            has_separate_title=plot.has_separate_title or "",
            valuation_amount=plot.valuation_amount,
            disposal_price=plot.disposal_price,
            comments=plot.comments or "",
            created_at=plot.created_at,
        )
        ApprovedDesignPlot.objects.filter(pk=plot.pk).update(legacy_parcel_id=parcel.pk)


class _OnlyIfPresent(migrations.SeparateDatabaseAndState):
    """Always applies the state change; runs the DB drop only if the table/column still exists.

    Reversal always recreates the table/column: both migration histories end without them.
    """

    def __init__(self, operation, table, column=None):
        super().__init__(database_operations=[operation], state_operations=[operation])
        self.table = table
        self.column = column

    def deconstruct(self):
        return (
            "SeparateDatabaseAndState",
            [],
            {
                "database_operations": self.database_operations,
                "state_operations": self.state_operations,
            },
        )

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self.column is None:
            present = _table_exists(schema_editor, self.table)
        else:
            present = _column_exists(schema_editor, self.table, self.column)
        if present:
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("cases", "0025_remove_legacy_parcel"),
        ("allocation", "0004_allocation_parcel_finalize"),
        ("core", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(dedupe_division_plots, migrations.RunPython.noop, atomic=True),
        migrations.RunPython(migrations.RunPython.noop, restore_parcels, atomic=True),
        _OnlyIfPresent(migrations.DeleteModel(name="Parcel"), PARCEL_TABLE),
        _OnlyIfPresent(
            migrations.RemoveField(model_name="approveddesignplot", name="legacy_parcel_id"),
            PLOT_TABLE,
            LEGACY_COLUMN,
        ),
    ]
