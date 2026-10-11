"""Data-migration tests for merging legacy Parcel (8.2) into ApprovedDesignPlot (7.3).

Covers cases 0024 (merge instead of duplicate), allocation 0002-0004 (FK repoint split in
schema/data/schema steps), cases 0026 (dedupe of rows created by the original 0024 and
final drop of Parcel/legacy_parcel_id) and the reverse path.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

CASES_0023 = ("cases", "0023_section_7_6_works_checks")
CASES_0025 = ("cases", "0025_remove_legacy_parcel")
CASES_0026 = ("cases", "0026_dedupe_approved_design_plots")
ALLOCATION_0001 = ("allocation", "0001_initial")
ALLOCATION_0004 = ("allocation", "0004_allocation_parcel_finalize")

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def _applied_state_apps(extra_nodes=()):
    """Historical apps for everything applied in the DB (plus ``extra_nodes``)."""
    loader = MigrationExecutor(connection).loader
    return loader.project_state([*loader.applied_migrations, *extra_nodes]).apps


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)
    return _applied_state_apps()


def _leaf_nodes():
    return MigrationExecutor(connection).loader.graph.leaf_nodes()


def _columns(table):
    with connection.cursor() as cursor:
        if table not in connection.introspection.table_names(cursor):
            return None
        return {c.name for c in connection.introspection.get_table_description(cursor, table)}


@pytest.fixture
def restore_latest_schema():
    yield
    _migrate(_leaf_nodes())


def _base_objects(apps):
    Community = apps.get_model("core", "Community")
    Case = apps.get_model("cases", "Case")
    Person = apps.get_model("applications", "Person")
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    Application = apps.get_model("applications", "Application")
    community = Community.objects.create(
        district="Λευκωσία",
        name="Κοινότητα Μετανάστευσης",
        contact_email="c@example.com",
        community_folder_code="MIG-1",
    )
    case = Case.objects.create(
        case_number="MIG/1",
        start_date=datetime.date(2026, 1, 1),
        contact_email="case@example.com",
        community=community,
    )
    person = Person.objects.create(
        identity_number="MIG-123",
        first_name="Α",
        last_name="Β",
        date_of_birth=datetime.date(1990, 1, 1),
        birth_place="Λευκωσία",
        birth_country="Κύπρος",
        parents_birth_place="Λευκωσία",
        parents_birth_country="Κύπρος",
    )
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=datetime.date(2026, 2, 1),
        submission_start_date=datetime.date(2026, 2, 1),
        submission_end_date=datetime.date(2026, 3, 1),
    )

    def make_application(folder):
        return Application.objects.create(
            folder_number=folder,
            submitted_on=datetime.date(2026, 2, 10),
            family_type="single",
            applicant_email="a@example.com",
            submission_cycle=cycle,
            person=person,
        )

    return case, person, make_application


def _audited_plot(apps, **kwargs):
    """A 7.3 row as created through the application (with its audit CREATE entry)."""
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    ActionHistory = apps.get_model("core", "ActionHistory")
    plot = ApprovedDesignPlot.objects.create(plot_type="division_plot", **kwargs)
    ActionHistory.objects.create(
        entity_type="ApprovedDesignPlot",
        entity_id=str(plot.pk),
        action="CREATE",
        case_id=plot.case_id,
    )
    return plot


def _seed_pre_merge(apps):
    """State at cases 0023: 7.3 rows, legacy Parcels (one overlapping) and allocations."""
    case, person, make_application = _base_objects(apps)
    Parcel = apps.get_model("cases", "Parcel")
    Field = apps.get_model("cases", "Field")
    Allocation = apps.get_model("allocation", "Allocation")
    field = Field.objects.create(case=case, code="F-1")
    plot_1 = _audited_plot(apps, case=case, design_number="1", sheet_plan="21/04", parcel_number="77")
    plot_2 = _audited_plot(apps, case=case, design_number="2")
    green = _audited_plot(apps, case=case, design_number="9")
    green.plot_type = "green_space"
    green.save()
    parcel_1 = Parcel.objects.create(
        case=case,
        design_lot_number="1",
        tkx_lot_number="301",
        final_area_sqm=Decimal("512.50"),
        valuation_amount=Decimal("70000"),
        disposal_price=Decimal("17500"),
        owner_person_id=person.pk,
        field=field,
        comments="από 8.2",
    )
    parcel_9 = Parcel.objects.create(
        case=case, design_lot_number="9", valuation_amount=Decimal("1000"), disposal_price=Decimal("250")
    )
    parcel_blank = Parcel.objects.create(case=case, design_lot_number="", kotsiani_number="K-5")
    Allocation.objects.create(application=make_application("A-1"), parcel=parcel_1)
    Allocation.objects.create(application=make_application("A-9"), parcel=parcel_9)
    return {
        "case": case,
        "person": person,
        "field": field,
        "plot_1": plot_1.pk,
        "plot_2": plot_2.pk,
        "green": green.pk,
        "parcels": (parcel_1.pk, parcel_9.pk, parcel_blank.pk),
    }


def test_forward_merges_parcels_into_existing_plots(restore_latest_schema):
    apps = _migrate([CASES_0023, ALLOCATION_0001])
    seed = _seed_pre_merge(apps)

    apps = _migrate(_leaf_nodes())
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Allocation = apps.get_model("allocation", "Allocation")

    division = ApprovedDesignPlot.objects.filter(case_id=seed["case"].pk, plot_type="division_plot")
    numbers = sorted(division.values_list("design_number", flat=True))
    assert numbers == ["", "1", "2", "9"]  # one row per lot - no duplicate for lot "1"

    merged = ApprovedDesignPlot.objects.get(pk=seed["plot_1"])
    assert merged.tkx_number == "301"
    assert merged.numbering_status == "tkx"
    assert merged.valuation_amount == Decimal("70000")
    assert merged.disposal_price == Decimal("17500")
    assert merged.final_area_sqm == Decimal("512.50")
    # cases 0027 turned owner_person_id into an ``owner`` FK with the same column value.
    assert getattr(merged, "owner_id", getattr(merged, "owner_person_id", None)) == seed["person"].pk
    assert merged.field_id == seed["field"].pk
    assert merged.comments == "από 8.2"
    assert merged.sheet_plan == "21/04"  # parcel empty -> 7.3 value kept
    assert merged.parcel_number == "77"

    # Lot "9" only matches a green space, so a new division plot is created for it.
    created_9 = division.get(design_number="9")
    assert created_9.pk != seed["green"]
    assert created_9.valuation_amount == Decimal("1000")
    assert division.get(design_number="").kotsiani_number == "K-5"

    assert sorted(Allocation.objects.values_list("parcel_id", flat=True)) == sorted(
        [merged.pk, created_9.pk]
    )
    with pytest.raises(LookupError):
        apps.get_model("cases", "Parcel")
    assert _columns("cases_parcel") is None
    assert "legacy_parcel_id" not in _columns("cases_approveddesignplot")
    assert "approved_design_plot_id" not in _columns("allocation_allocation")


def test_reverse_restores_parcels_and_keeps_existing_plots(restore_latest_schema):
    apps = _migrate([CASES_0023, ALLOCATION_0001])
    seed = _seed_pre_merge(apps)
    _migrate(_leaf_nodes())

    apps = _migrate([CASES_0023, ALLOCATION_0001])
    Parcel = apps.get_model("cases", "Parcel")
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Allocation = apps.get_model("allocation", "Allocation")

    parcels = {p.design_lot_number: p for p in Parcel.objects.all()}
    assert sorted(parcels) == ["", "1", "9"]
    assert parcels["1"].tkx_lot_number == "301"
    assert parcels["1"].valuation_amount == Decimal("70000")
    assert parcels["1"].owner_person_id == seed["person"].pk
    assert parcels["9"].valuation_amount == Decimal("1000")
    assert parcels[""].kotsiani_number == "K-5"
    allocated = sorted(
        Parcel.objects.get(pk=pk).design_lot_number
        for pk in Allocation.objects.values_list("parcel_id", flat=True)
    )
    assert allocated == ["1", "9"]

    # Pre-existing 7.3 rows survive; rows created by 0024 are gone again.
    assert sorted(ApprovedDesignPlot.objects.values_list("pk", flat=True)) == sorted(
        [seed["plot_1"], seed["plot_2"], seed["green"]]
    )

    # Re-applying merges again instead of duplicating.
    apps = _migrate(_leaf_nodes())
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    numbers = list(
        ApprovedDesignPlot.objects.filter(plot_type="division_plot").values_list(
            "design_number", flat=True
        )
    )
    assert sorted(numbers) == ["", "1", "2", "9"]


def _seed_duplicates(apps, with_legacy):
    case, _person, make_application = _base_objects(apps)
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Allocation = apps.get_model("allocation", "Allocation")
    Attachment = apps.get_model("core", "Attachment")
    ContentType = apps.get_model("contenttypes", "ContentType")
    original = _audited_plot(apps, case=case, design_number="5", sheet_plan="X/1")
    copy_kwargs = {"legacy_parcel_id": 4242} if with_legacy else {}
    copy = ApprovedDesignPlot.objects.create(  # inserted by the buggy 0024: no audit entry
        case=case,
        plot_type="division_plot",
        design_number="5",
        tkx_number="77",
        numbering_status="tkx",
        valuation_amount=Decimal("1000"),
        disposal_price=Decimal("250"),
        **copy_kwargs,
    )
    # Two user-entered rows with the same number are not migration duplicates.
    user_a = _audited_plot(apps, case=case, design_number="6")
    user_b = _audited_plot(apps, case=case, design_number="6")
    allocation = Allocation.objects.create(application=make_application("D-1"), parcel=copy)
    plot_ct, _ = ContentType.objects.get_or_create(app_label="cases", model="approveddesignplot")
    attachment = Attachment.objects.create(
        content_type=plot_ct,
        object_id=copy.pk,
        filename="a.pdf",
        content_type_name="application/pdf",
        size_bytes=1,
        data=b"x",
    )
    return original.pk, copy.pk, (user_a.pk, user_b.pk), allocation.pk, attachment.pk


def _assert_deduped(apps, original_id, copy_id, user_ids, allocation_id, attachment_id):
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Allocation = apps.get_model("allocation", "Allocation")
    Attachment = apps.get_model("core", "Attachment")
    assert not ApprovedDesignPlot.objects.filter(pk=copy_id).exists()
    kept = ApprovedDesignPlot.objects.get(pk=original_id)
    assert kept.valuation_amount == Decimal("1000")
    assert kept.disposal_price == Decimal("250.00")
    assert kept.tkx_number == "77"
    assert kept.numbering_status == "tkx"
    assert kept.sheet_plan == "X/1"
    assert Allocation.objects.get(pk=allocation_id).parcel_id == original_id
    assert Attachment.objects.get(pk=attachment_id).object_id == original_id
    assert ApprovedDesignPlot.objects.filter(pk__in=user_ids).count() == 2


def test_dedupe_after_old_0025_dropped_legacy_column(restore_latest_schema):
    """User DB scenario: the old 0024/0025 already ran, legacy_parcel_id and Parcel are gone."""
    _migrate([CASES_0025, ALLOCATION_0004])
    state_0025 = _applied_state_apps()
    with connection.schema_editor() as editor:
        plot_model = state_0025.get_model("cases", "ApprovedDesignPlot")
        editor.remove_field(plot_model, plot_model._meta.get_field("legacy_parcel_id"))
        editor.delete_model(state_0025.get_model("cases", "Parcel"))

    # Rows are created with the post-0026 state, which matches this schema.
    final_apps = _applied_state_apps([CASES_0026])
    ids = _seed_duplicates(final_apps, with_legacy=False)

    apps = _migrate([CASES_0026])
    _assert_deduped(apps, *ids)
    assert _columns("cases_parcel") is None


def test_dedupe_with_legacy_column_present(restore_latest_schema):
    apps = _migrate([CASES_0025, ALLOCATION_0004])
    ids = _seed_duplicates(apps, with_legacy=True)

    apps = _migrate([CASES_0026])
    _assert_deduped(apps, *ids)
    assert "legacy_parcel_id" not in _columns("cases_approveddesignplot")
