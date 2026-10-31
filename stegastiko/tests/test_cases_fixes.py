"""Regression tests for correctness fixes in the Κ.Σ./Δ.Δ. case app (cases/*)."""

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from applications.models import Person
from cases import services
from cases.models import (
    ApprovedDesignPlot,
    Case,
    CommunicationStatus,
    CompletenessCheck,
    InfrastructureCheck,
    MinistryDecisionRound,
    SubmissionCycle,
    SubmissionCyclePublication,
    YesNo,
)
from core.models import Communication, Community, Role
from core.services import (
    begin_settings_memo,
    end_settings_memo,
    get_setting,
    set_setting,
)
from tests.fixtures.cycles import make_cycle
from tests.fixtures.plot_applications import make_plot_application

JSON = {"HTTP_ACCEPT": "application/json"}
STAFF_ROLE = "Προϊστάμενος ελέγχου"
NEW_DELETE_GRANTS = ("case_section_6:delete", "case_section_7:delete")


@pytest.fixture
def community(db):
    return Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )


def _grant(role_name, *grants):
    role = Role.objects.get(name=role_name)
    role.grants = sorted({*role.grants, *grants})
    role.save()
    return role


@pytest.fixture
def staff_client(client, make_user):
    # The seeded staff role keeps «Διαγραφή» on 6 / 7 / 8 (added to the catalog with this fix).
    _grant(STAFF_ROLE, *NEW_DELETE_GRANTS)
    client.force_login(make_user("officer", STAFF_ROLE))
    return client


@pytest.fixture
def smtp_configured(db):
    set_setting("smtpHost", "smtp.example.org")
    set_setting("smtpFromEmail", "stegastiko@example.org")


def _role_client(client, make_user, username, grants):
    role = Role.objects.create(name=f"role-{username}", grants=sorted(grants))
    user = make_user(username)
    role.members.add(user)
    client.force_login(user)
    return client


def _make_case(community, number="CASE-ABG-01", **extra):
    return Case.objects.create(
        community=community,
        case_number=number,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
        **extra,
    )


def _make_person(identity="ID-1"):
    return Person.objects.create(
        identity_number=identity,
        first_name="Α",
        last_name="Β",
        date_of_birth=date(1990, 1, 1),
        birth_place="Λευκωσία",
        birth_country="Κύπρος",
        parents_birth_place="Λευκωσία",
        parents_birth_country="Κύπρος",
    )


def _allocate(plot, community):
    """Allocate the completed plot produced by a 7.3 row (created as completion would)."""
    from allocation.models import Allocation
    from plots.models import Plot

    completed = Plot(community=community, source_case=plot.case, source_design_plot=plot)
    completed.copy_from(plot)
    completed.save()

    application = make_plot_application(community, _make_person())
    return Allocation.objects.create(application=application, parcel=completed)


# --- 1. Case number: max sequence + retry, never a server error -----------------------------


def _create_payload(community):
    return {
        "community": community.pk,
        "submitted_at": "2026-01-15",
        "contact_email": community.contact_email,
    }


@pytest.mark.django_db
def test_case_number_is_not_reused_after_a_deletion(community, staff_client):
    for _ in range(3):
        assert staff_client.post(reverse("cases:create"), _create_payload(community)).status_code == 302
    numbers = sorted(Case.objects.values_list("case_number", flat=True))
    assert numbers == ["CASE.001.1", "CASE.001.2", "CASE.001.3"]
    Case.objects.get(case_number=numbers[0]).delete()

    response = staff_client.post(reverse("cases:create"), _create_payload(community))
    assert response.status_code == 302
    assert Case.objects.order_by("-id").first().case_number == "CASE.001.4"


@pytest.mark.django_db
def test_case_number_is_prefix_folder_code_and_sequence_per_community(community):
    other = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ", name="ΔΕΖ", contact_email="dez@example.org", community_folder_code="002"
    )
    set_setting("caseNumberPrefix", "17")
    first = services.create_case(Case(community=community, contact_email="a@example.org"))
    other_first = services.create_case(Case(community=other, contact_email="b@example.org"))
    second = services.create_case(Case(community=community, contact_email="a@example.org"))
    assert first.case_number == "17.001.1"
    assert other_first.case_number == "17.002.1"
    assert second.case_number == "17.001.2"

    # A later prefix change keeps counting the community's cases.
    set_setting("caseNumberPrefix", "18")
    third = services.create_case(Case(community=community, contact_email="a@example.org"))
    assert third.case_number == "18.001.3"


@pytest.mark.django_db
def test_case_create_retries_when_a_concurrent_create_took_the_number(community, monkeypatch):
    real = services.generate_case_number
    year = date.today().year
    _make_case(community, number="CASE.001.7")
    calls = []

    def racing(community, start_date=None):
        calls.append(1)
        # First attempt returns the number a concurrent request has just saved.
        return "CASE.001.7" if len(calls) == 1 else real(community, start_date)

    monkeypatch.setattr(services, "generate_case_number", racing)
    case = services.create_case(
        Case(community=community, contact_email="x@example.org", start_date=date(year, 2, 1))
    )
    assert len(calls) == 2
    assert case.case_number == "CASE.001.8"


@pytest.mark.django_db
def test_case_create_shows_a_form_error_instead_of_500_when_numbers_keep_colliding(
    community, staff_client, monkeypatch
):
    def always_taken(case):
        raise IntegrityError("UNIQUE constraint failed: cases_case.case_number")

    monkeypatch.setattr(Case, "save", lambda self, *a, **k: always_taken(self))
    response = staff_client.post(reverse("cases:create"), _create_payload(community))
    assert response.status_code == 200
    assert "ταυτόχρονης καταχώρισης" in response.content.decode()


# --- 2. Announcement details (Στάδιο 1) stay editable after publishing -------------------------


def _cycle(community, published=False):
    return make_cycle(
        community,
        announcement_date=date(2027, 6, 1),
        published_at="2027-06-01T10:00:00Z" if published else None,
    )


def _announcement_post(months="1"):
    return {"cycle-announcement_date": "2027-06-01", "cycle-submission_months": months}


PUBLICATION = {"published_on": "2027-06-02"}


@pytest.mark.django_db
def test_announcement_detail_post_saves_a_draft(community, staff_client):
    cycle = _cycle(community)
    url = reverse("announcements:detail", args=[cycle.pk])
    response = staff_client.post(url, _announcement_post("3"))
    assert response.status_code == 302
    cycle.refresh_from_db()
    assert cycle.submission_months == 3 and cycle.submission_end_date == date(2027, 9, 1)


@pytest.mark.django_db
def test_publication_table_always_lists_the_four_methods_with_a_date_input(community, staff_client):
    cycle = _cycle(community)
    detail = staff_client.get(reverse("announcements:detail", args=[cycle.pk])).content.decode()
    assert "data-publication-table" in detail
    for method in SubmissionCyclePublication.FIXED_METHODS:
        assert SubmissionCyclePublication.PublicationMethod(method).label in detail
        assert reverse("announcements:publication_date", args=[cycle.pk, method.value]) in detail
    assert detail.count("data-publication-date=") == 4


def _set_date(client, cycle, method, value):
    url = reverse("announcements:publication_date", args=[cycle.pk, method])
    return client.post(url, {"published_on": value}, **JSON)


@pytest.mark.django_db
def test_fixed_method_date_is_set_inline_once_and_is_optional(community, staff_client):
    cycle = _cycle(community)
    response = _set_date(staff_client, cycle, "district_office", "2027-06-02")
    assert response.status_code == 200 and response.json()["ok"]
    assert "data-publication-table" in response.json()["grid_html"]
    row = cycle.publications.get()
    assert (row.method, row.notes, row.published_on) == ("district_office", "", date(2027, 6, 2))

    # Changing the date updates the same row; an empty date removes it (the method is optional).
    assert _set_date(staff_client, cycle, "district_office", "2027-06-05").json()["ok"]
    row.refresh_from_db()
    assert row.published_on == date(2027, 6, 5) and cycle.publications.count() == 1
    assert _set_date(staff_client, cycle, "district_office", "").json()["ok"]
    assert cycle.publications.count() == 0
    assert _set_date(staff_client, cycle, "district_office", "").json()["ok"]  # nothing to remove

    assert _set_date(staff_client, cycle, "community", "31/02/2027").status_code == 400
    assert _set_date(staff_client, cycle, "other", "2027-06-02").status_code == 404
    assert cycle.publications.count() == 0


@pytest.mark.django_db
def test_fixed_method_dates_stay_editable_once_published(community, staff_client):
    cycle = _cycle(community, published=True)
    response = _set_date(staff_client, cycle, "community", "2027-06-02")
    assert response.status_code == 200 and response.json()["ok"]
    assert cycle.publications.count() == 1


@pytest.mark.django_db
def test_fixed_methods_are_not_edited_in_the_modal(community, staff_client):
    cycle = _cycle(community)
    row = cycle.publications.create(method="community", published_on=date(2027, 6, 2))
    edit_url = reverse("announcements:publication_edit", args=[cycle.pk, row.pk])
    assert staff_client.get(edit_url, **JSON).status_code == 404
    delete_url = reverse("announcements:publication_delete", args=[cycle.pk, row.pk])
    assert staff_client.post(delete_url, **JSON).status_code == 404
    assert cycle.publications.count() == 1


@pytest.mark.django_db
def test_other_can_be_recorded_many_times_with_date_and_comment(community, staff_client):
    cycle = _cycle(community)
    create_url = reverse("announcements:publication_create", args=[cycle.pk])
    assert staff_client.post(create_url, PUBLICATION, **JSON).status_code == 400  # the comment is needed
    for day, comment in (("2027-06-02", "Εφημερίδα"), ("2027-06-03", "Ραδιόφωνο")):
        response = staff_client.post(create_url, {"published_on": day, "notes": comment}, **JSON)
        assert response.status_code == 200 and response.json()["ok"]
    first, second = cycle.publications.all()
    assert (first.method, first.notes) == ("other", "Εφημερίδα")

    edit_url = reverse("announcements:publication_edit", args=[cycle.pk, first.pk])
    assert staff_client.post(edit_url, {"published_on": "2027-06-04", "notes": "Τύπος"}, **JSON).json()["ok"]
    delete_url = reverse("announcements:publication_delete", args=[cycle.pk, second.pk])
    assert staff_client.post(delete_url, **JSON).json()["ok"]
    assert list(cycle.publications.values_list("notes", flat=True)) == ["Τύπος"]


@pytest.mark.django_db
def test_the_database_keeps_each_fixed_method_once(community):
    cycle = _cycle(community)
    cycle.publications.create(method="community", published_on=date(2027, 6, 2))
    with pytest.raises(IntegrityError), transaction.atomic():
        cycle.publications.create(method="community", published_on=date(2027, 6, 3))
    cycle.publications.create(method="other", published_on=date(2027, 6, 3), notes="α")
    cycle.publications.create(method="other", published_on=date(2027, 6, 4), notes="β")


@pytest.mark.django_db
def test_announcement_publications_stay_editable_once_published(community, staff_client):
    cycle = _cycle(community, published=True)
    create_url = reverse("announcements:publication_create", args=[cycle.pk])
    detail = staff_client.get(
        reverse("announcements:detail", args=[cycle.pk]), {"stage": "details"}
    ).content.decode()
    assert create_url in detail
    response = staff_client.post(create_url, {**PUBLICATION, "notes": "Εφημερίδα"}, **JSON)
    assert response.status_code == 200 and response.json()["ok"]
    assert cycle.publications.count() == 1


@pytest.mark.django_db
def test_announcement_detail_post_saves_a_published_announcement(community, staff_client):
    cycle = _cycle(community, published=True)
    url = reverse("announcements:detail", args=[cycle.pk])
    response = staff_client.post(url, _announcement_post("5"))
    assert response.status_code == 302 and response["Location"].endswith("?stage=details")
    cycle.refresh_from_db()
    assert cycle.submission_months == 5 and cycle.submission_end_date == date(2027, 11, 1)
    assert cycle.is_published


@pytest.mark.django_db
def test_announcement_details_tab_of_published_announcement_is_editable(community, staff_client):
    cycle = _cycle(community, published=True)
    html = staff_client.get(
        reverse("announcements:detail", args=[cycle.pk]), {"stage": "details"}
    ).content.decode()
    assert "data-published-editable-notice" in html
    assert "data-save-announcement-details" in html
    assert "μόνο για ανάγνωση" not in html


# --- 4. Deficiency email: record first, mark sent / failed, refuse double submits -------------------


def _make_check(case):
    return CompletenessCheck.objects.create(
        case=case, check_date=date(2026, 1, 20), result=YesNo.NO, deficiencies="Λείπει κατάλογος."
    )


@pytest.mark.django_db
def test_deficiency_email_is_recorded_before_it_is_sent(community, smtp_configured, monkeypatch):
    check = _make_check(_make_case(community))
    seen = []

    def fake_send(recipient, subject, body):
        seen.append(list(Communication.objects.values_list("status", flat=True)))

    monkeypatch.setattr(services, "send_email", fake_send)
    communication = services.send_deficiency_email(check, "Θέμα", "Κείμενο")
    assert seen == [[CommunicationStatus.SENDING]]
    communication.refresh_from_db()
    assert communication.status == CommunicationStatus.SENT
    assert communication.sent_at is not None


@pytest.mark.django_db
def test_failed_deficiency_email_is_marked_failed_and_keeps_check_deletable(
    community, smtp_configured, monkeypatch, staff_client
):
    from django.core.exceptions import ValidationError

    case = _make_case(community)
    check = _make_check(case)

    def broken_send(recipient, subject, body):
        raise ValidationError("Αποτυχία αποστολής email: down")

    monkeypatch.setattr(services, "send_email", broken_send)
    url = reverse("cases:deficiency_email_send", args=[case.pk, check.pk])
    response = staff_client.post(url, {"subject": "Θέμα", "body": "Κείμενο"}, **JSON)
    assert response.status_code == 400
    assert "down" in response.json()["errors"][0]
    assert list(check.communications.values_list("status", flat=True)) == [
        CommunicationStatus.FAILED
    ]
    assert check.can_delete
    assert check.sent_emails_count == 0
    # A failed attempt does not count as a duplicate: retrying is allowed.
    monkeypatch.setattr(services, "send_email", lambda *args: None)
    assert staff_client.post(url, {"subject": "Θέμα", "body": "Κείμενο"}, **JSON).status_code == 200
    assert not CompletenessCheck.objects.get(pk=check.pk).can_delete


@pytest.mark.django_db
def test_double_submitted_deficiency_email_is_sent_once(community, smtp_configured, staff_client):
    case = _make_case(community)
    check = _make_check(case)
    url = reverse("cases:deficiency_email_send", args=[case.pk, check.pk])
    payload = {"subject": "Θέμα", "body": "Κείμενο"}
    assert staff_client.post(url, payload, **JSON).status_code == 200
    second = staff_client.post(url, payload, **JSON)
    assert second.status_code == 400
    assert "έχει ήδη σταλεί" in second.json()["errors"][0]
    assert len(mail.outbox) == 1
    assert check.communications.count() == 1


@pytest.mark.django_db
def test_deficiency_email_without_smtp_records_nothing(community, staff_client):
    case = _make_case(community)
    check = _make_check(case)
    url = reverse("cases:deficiency_email_send", args=[case.pk, check.pk])
    response = staff_client.post(url, {"subject": "Θέμα", "body": "Κ"}, **JSON)
    assert response.status_code == 400
    assert not Communication.objects.exists()


# --- 5. Completeness check numbering survives a concurrent insert -------------------------------------


@pytest.mark.django_db
def test_completeness_sequence_retries_on_conflict(community, monkeypatch):
    case = _make_case(community)
    _make_check(case)  # sequence 1
    real = CompletenessCheck._next_sequence
    attempts = []

    def stale(self):
        attempts.append(1)
        # A concurrent save already took number 1 when this one read the max.
        return 1 if len(attempts) == 1 else real(self)

    monkeypatch.setattr(CompletenessCheck, "_next_sequence", stale)
    check = _make_check(case)
    assert len(attempts) == 2
    assert check.sequence == 2


# --- 6. Bulk plot numbering continues after existing rows --------------------------------------------


def _bulk(client, case, **values):
    data = {"plot_type": "division_plot", "plot_type_other": "", "count": "3", "numbering_mode": "serial"}
    data.update(values)
    return client.post(
        reverse("cases:approved_design_plot_bulk_create", args=[case.pk]), data, **JSON
    )


@pytest.mark.django_db
def test_bulk_serial_numbering_starts_after_existing_numbers(community, staff_client):
    case = _make_case(community)
    assert _bulk(staff_client, case).status_code == 200
    assert _bulk(staff_client, case, count="2").status_code == 200
    # Another type numbers independently.
    assert _bulk(staff_client, case, plot_type="green_space", count="1").status_code == 200
    numbers = list(
        case.approved_design_plots.filter(plot_type="division_plot")
        .order_by("id")
        .values_list("design_number", flat=True)
    )
    assert numbers == ["1", "2", "3", "4", "5"]
    assert case.approved_design_plots.get(plot_type="green_space").design_number == "1"


@pytest.mark.django_db
def test_bulk_manual_numbering_rejects_numbers_already_in_the_case(community, staff_client):
    case = _make_case(community)
    ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot", design_number="7")
    response = staff_client.post(
        reverse("cases:approved_design_plot_bulk_create", args=[case.pk]),
        {
            "plot_type": "division_plot",
            "count": "2",
            "numbering_mode": "manual",
            "manual_numbers": ["6", "7"],
        },
        **JSON,
    )
    assert response.status_code == 400
    assert "υπάρχει ήδη" in response.json()["html"]
    assert case.approved_design_plots.count() == 1


@pytest.mark.django_db
def test_approved_design_plots_workspace_is_available_from_every_case_section(
    community, staff_client
):
    case = _make_case(community)
    plot = ApprovedDesignPlot.objects.create(
        case=case,
        plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT,
        design_number="3",
        valuation_amount=Decimal("80000"),
    )

    for section in ("1", "4", "7"):
        html = staff_client.get(
            reverse("cases:section_edit", args=[case.pk, section])
        ).content.decode()
        assert 'class="approved-design-plots-fab"' in html
        assert 'id="approved-design-plots-workspace"' in html
        assert reverse("cases:approved_design_plot_grid", args=[case.pk]) in html

    grid = staff_client.get(
        reverse("cases:approved_design_plot_grid", args=[case.pk]), **JSON
    ).json()["grid_html"]
    assert "Μαζική προσθήκη" in grid
    assert f"approved-design-plot-row-{plot.pk}" in grid
    assert "Αξία τελευταίας γενικής εκτίμησης (€)" in grid
    assert "Τιμή διάθεσης (€)" in grid


@pytest.mark.django_db
def test_approved_design_plot_inline_save_updates_value_and_calculated_price(
    community, staff_client
):
    case = _make_case(community)
    plot = ApprovedDesignPlot.objects.create(
        case=case,
        plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT,
        design_number="3",
    )
    prefix = f"plot-{plot.pk}"
    response = staff_client.post(
        reverse("cases:approved_design_plot_inline_edit", args=[case.pk, plot.pk]),
        {
            f"{prefix}-plot_type": ApprovedDesignPlot.PlotType.DIVISION_PLOT,
            f"{prefix}-plot_type_other": "",
            f"{prefix}-design_number": "4",
            f"{prefix}-tkx_number": "204",
            f"{prefix}-title_deed_number": "T-4",
            f"{prefix}-parcel_number": "44",
            f"{prefix}-sheet_plan": "21/04",
            f"{prefix}-final_area_sqm": "610.50",
            f"{prefix}-numbering_status": ApprovedDesignPlot.NumberingStatus.TKX,
            f"{prefix}-valuation_amount": "80000",
        },
        **JSON,
    )

    assert response.status_code == 200
    plot.refresh_from_db()
    assert plot.design_number == "4"
    assert plot.tkx_number == "204"
    assert plot.valuation_amount == Decimal("80000")
    assert plot.disposal_price == Decimal("20000.00")
    assert "20000" in response.json()["grid_html"]

    def post(valuation, price):
        values = {
            f"{prefix}-plot_type": ApprovedDesignPlot.PlotType.DIVISION_PLOT,
            f"{prefix}-design_number": "4",
            f"{prefix}-numbering_status": ApprovedDesignPlot.NumberingStatus.DESIGN,
            f"{prefix}-valuation_amount": valuation,
            f"{prefix}-disposal_price": price,
        }
        url = reverse("cases:approved_design_plot_inline_edit", args=[case.pk, plot.pk])
        assert staff_client.post(url, values, **JSON).status_code == 200
        plot.refresh_from_db()

    # The price is editable: a typed price is kept, also when the value changes later.
    post("80000", "18500")
    assert plot.disposal_price == Decimal("18500")
    post("90000", "18500")
    assert plot.disposal_price == Decimal("18500")
    # Cleared, it is calculated again from the value.
    post("90000", "")
    assert plot.disposal_price == Decimal("22500.00")
    # Left as it was, it follows the value.
    post("100000", "22500.00")
    assert plot.disposal_price == Decimal("25000.00")


@pytest.mark.django_db
def test_approved_design_plot_links_optional_source_land_plots(community, staff_client):
    case = _make_case(community)
    first = case.land_plots.create(parcel_number="101", sheet_plan="30/12")
    second = case.land_plots.create(parcel_number="102")
    other_case = _make_case(community, number="CASE-ABG-02")
    foreign = other_case.land_plots.create(parcel_number="999")

    # New row from the dialog: two parcels of the case.
    create_url = reverse("cases:approved_design_plot_create", args=[case.pk])
    form_html = staff_client.get(create_url, **JSON).json()["html"]
    assert "Τεμάχια προέλευσης" in form_html
    assert "101 (Φ/Σχ 30/12)" in form_html
    assert "999" not in form_html
    response = staff_client.post(
        create_url,
        {
            "plot_type": "division_plot",
            "plot_type_other": "",
            "design_number": "1",
            "source_land_plots": [first.pk, second.pk],
        },
        **JSON,
    )
    assert response.status_code == 200
    plot = case.approved_design_plots.get()
    assert set(plot.source_land_plots.all()) == {first, second}
    assert "101 (Φ/Σχ 30/12), 102" in response.json()["grid_html"]

    # A parcel of another case is not a valid choice.
    response = staff_client.post(
        create_url,
        {
            "plot_type": "division_plot",
            "plot_type_other": "",
            "design_number": "2",
            "source_land_plots": [foreign.pk],
        },
        **JSON,
    )
    assert response.status_code == 400

    # The inline row save can clear the links: they are optional.
    prefix = f"plot-{plot.pk}"
    response = staff_client.post(
        reverse("cases:approved_design_plot_inline_edit", args=[case.pk, plot.pk]),
        {
            f"{prefix}-plot_type": "division_plot",
            f"{prefix}-plot_type_other": "",
            f"{prefix}-design_number": "1",
            f"{prefix}-numbering_status": ApprovedDesignPlot.NumberingStatus.DESIGN,
            f"{prefix}-source_land_plots": [second.pk],
        },
        **JSON,
    )
    assert response.status_code == 200
    assert list(plot.source_land_plots.all()) == [second]


@pytest.mark.django_db
def test_land_plot_linked_to_design_plot_cannot_be_deleted(community, staff_client):
    case = _make_case(community)
    linked = case.land_plots.create(parcel_number="101")
    free = case.land_plots.create(parcel_number="102")
    plot = ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot", design_number="5")
    plot.source_land_plots.add(linked)

    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "3"])).content.decode()
    assert reverse("cases:land_plot_delete", args=[case.pk, linked.pk]) not in html
    assert reverse("cases:land_plot_delete", args=[case.pk, free.pk]) in html

    refused = staff_client.post(
        reverse("cases:land_plot_delete", args=[case.pk, linked.pk]),
        {"confirm_evaluation": "1"},
        **JSON,
    )
    assert refused.status_code == 409
    assert "τεμάχιο 101 δεν διαγράφεται" in refused.json()["message"]
    assert case.land_plots.filter(pk=linked.pk).exists()

    # Once the plot no longer names it, the parcel can go.
    plot.source_land_plots.clear()
    deleted = staff_client.post(
        reverse("cases:land_plot_delete", args=[case.pk, linked.pk]), **JSON
    )
    assert deleted.json()["ok"] is True


# --- 7. An allocated plot keeps its type -------------------------------------------------------------


@pytest.mark.django_db
def test_allocated_plot_type_cannot_change(community, staff_client):
    case = _make_case(community)
    plot = ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot", design_number="1")
    _allocate(plot, community)
    url = reverse("cases:approved_design_plot_edit", args=[case.pk, plot.pk])
    response = staff_client.post(
        url, {"plot_type": "green_space", "plot_type_other": "", "design_number": "1"}, **JSON
    )
    assert response.status_code == 400
    assert "έχει ήδη καταχωριστεί στα Οικόπεδα" in response.json()["html"]
    plot.refresh_from_db()
    assert plot.plot_type == "division_plot"
    # The number can still be corrected.
    response = staff_client.post(
        url, {"plot_type": "division_plot", "plot_type_other": "", "design_number": "1Α"}, **JSON
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_allocated_plot_cannot_be_deleted(community, staff_client):
    case = _make_case(community)
    plot = ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot", design_number="1")
    _allocate(plot, community)
    response = staff_client.post(
        reverse("cases:approved_design_plot_delete", args=[case.pk, plot.pk]), **JSON
    )
    assert response.status_code == 409
    assert ApprovedDesignPlot.objects.filter(pk=plot.pk).exists()


# --- 8. Delete views need «Διαγραφή» of the section that owns the row ------------------------------------


EDIT_ONLY = {
    "cases:view",
    "case_section_6:view",
    "case_section_6:edit",
    "case_section_7:view",
    "case_section_7:edit",
}


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["ministry", "plot", "infrastructure", "consultation"])
def test_delete_views_require_delete_access(community, client, make_user, kind):
    from cases.models import Consultation

    case = _make_case(community)
    if kind == "ministry":
        row = MinistryDecisionRound.objects.create(case=case)
        url = reverse("cases:ministry_decision_round_delete", args=[case.pk, row.pk])
    elif kind == "plot":
        row = ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot")
        url = reverse("cases:approved_design_plot_delete", args=[case.pk, row.pk])
    elif kind == "infrastructure":
        row = InfrastructureCheck.objects.create(case=case, check_date=date(2027, 1, 1))
        url = reverse("cases:infrastructure_check_delete", args=[case.pk, row.pk])
    else:
        row = Consultation.objects.create(
            case=case, stage=Consultation.Stage.DIVISION, department="tkx"
        )
        url = reverse("cases:division_consultation_delete", args=[case.pk, row.pk])

    editor = _role_client(client, make_user, "editor", EDIT_ONLY)
    assert editor.post(url, **JSON).status_code == 403
    assert type(row).objects.filter(pk=row.pk).exists()

    section = {"ministry": "6", "plot": "7", "infrastructure": "7", "consultation": "7"}[kind]
    deleter = _role_client(
        client, make_user, "deleter", EDIT_ONLY | {f"case_section_{section}:delete"}
    )
    response = deleter.post(url, **JSON)
    assert response.status_code == 200, response.content
    assert response.json()["ok"] is True
    assert not type(row).objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_division_plots_are_deleted_with_section_7_access(community, client, make_user):
    case = _make_case(community)
    plot = ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot")
    url = reverse("cases:approved_design_plot_delete", args=[case.pk, plot.pk])
    viewer = _role_client(
        client, make_user, "viewer7", {"cases:view", "case_section_7:view", "case_section_7:edit"}
    )
    assert viewer.post(url, **JSON).status_code == 403
    deleter = _role_client(
        client,
        make_user,
        "deleter7",
        {"cases:view", "case_section_7:view", "case_section_7:edit", "case_section_7:delete"},
    )
    response = deleter.post(url, **JSON)
    assert response.status_code == 200
    assert response.json()["reload"] is False
    assert not ApprovedDesignPlot.objects.filter(pk=plot.pk).exists()


@pytest.mark.django_db
def test_delete_views_reject_get_and_other_cases(community, staff_client):
    case = _make_case(community)
    other = _make_case(community, number="CASE-ABG-02")
    row = MinistryDecisionRound.objects.create(case=other)
    url = reverse("cases:ministry_decision_round_delete", args=[case.pk, row.pk])
    assert staff_client.get(url, **JSON).status_code == 404
    assert staff_client.post(url).status_code == 404  # not a JSON request
    assert staff_client.post(url, **JSON).status_code == 404  # row of another case
    assert MinistryDecisionRound.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_ministry_round_delete_removes_its_files(community, staff_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.models import ActionHistory, Attachment

    case = _make_case(community)
    response = staff_client.post(
        reverse("cases:ministry_decision_round_create", args=[case.pk]),
        {
            "letter_sent_date": "2027-01-01",
            "recommendation": "positive",
            "ministry_decision": "",
            "comments": "",
            "new_recommendation_files": SimpleUploadedFile("rec.pdf", b"%PDF"),
        },
        **JSON,
    )
    assert response.status_code == 200
    row = MinistryDecisionRound.objects.get()
    assert row.attachments.count() == 1
    response = staff_client.post(
        reverse("cases:ministry_decision_round_delete", args=[case.pk, row.pk]), **JSON
    )
    assert response.status_code == 200
    assert not Attachment.objects.exists()
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="DELETE", section_ref="6.7"
    ).exists()


# --- 9. Performance: bounded queries -----------------------------------------------------------------


def _list_queries(client, community, extra_cases, prefix):
    for index in range(extra_cases):
        case = _make_case(community, number=f"CASE-{prefix}-{index:02d}")
        _make_check(case)
        MinistryDecisionRound.objects.create(case=case, ministry_decision="approved")
        ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot")
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("cases:list"))
    assert response.status_code == 200
    return len(queries)


@pytest.mark.django_db
def test_case_list_query_count_does_not_grow_with_rows(community, staff_client):
    few = _list_queries(staff_client, community, 2, "A")
    many = _list_queries(staff_client, community, 10, "B")
    assert few == many
    assert many <= 15


@pytest.mark.django_db
def test_case_list_shows_annotated_row_data(community, staff_client):
    case = _make_case(community)
    _make_check(case)
    MinistryDecisionRound.objects.create(
        case=case, ministry_decision="other", ministry_decision_other="Επανεξέταση"
    )
    ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot")
    ApprovedDesignPlot.objects.create(case=case, plot_type="green_space")
    html = staff_client.get(reverse("cases:list")).content.decode()
    assert "Άλλο: Επανεξέταση" in html
    assert 'badge--fail">ΟΧΙ<' in html
    assert "<td>2</td>" in html  # two approved design plots

    annotated = Case.objects.with_list_data().get(pk=case.pk)
    plain = Case.objects.get(pk=case.pk)
    for name in ("completeness_result", "completeness_result_display", "latest_ministry_decision_display"):
        assert getattr(annotated, name) == getattr(plain, name)
    assert annotated.land_plots_count == 0 and annotated.approved_design_plots_count == 2


@pytest.mark.django_db
def test_case_list_is_paginated_and_keeps_filters(community, staff_client):
    from cases.views.folder import CASE_LIST_PAGE_SIZE

    for index in range(CASE_LIST_PAGE_SIZE + 3):
        _make_case(community, number=f"CASE-P-{index:03d}")
    html = staff_client.get(reverse("cases:list"), {"community_id": community.pk}).content.decode()
    assert html.count('class="btn btn-ghost btn-sm">Άνοιγμα</a>') == CASE_LIST_PAGE_SIZE
    assert f"community_id={community.pk}&amp;page=2" in html
    page_2 = staff_client.get(reverse("cases:list"), {"community_id": community.pk, "page": 2})
    assert page_2.content.decode().count('class="btn btn-ghost btn-sm">Άνοιγμα</a>') == 3


@pytest.mark.django_db
def test_plot_owner_is_a_foreign_key_loaded_without_a_query_per_plot(community, staff_client):
    case = _make_case(community)
    for index in range(5):
        ApprovedDesignPlot.objects.create(
            case=case, plot_type="division_plot", owner=_make_person(f"ID-{index}")
        )
    plot = ApprovedDesignPlot.objects.select_related("owner").first()
    with CaptureQueriesContext(connection) as queries:
        assert plot.owner.identity_number == "ID-0"
    assert len(queries) == 0

    def detail_queries():
        with CaptureQueriesContext(connection) as captured:
            assert staff_client.get(reverse("cases:detail", args=[case.pk])).status_code == 200
        return len(captured)

    detail_queries()  # Warm template/configuration caches before comparing query counts.
    before = detail_queries()
    ApprovedDesignPlot.objects.create(case=case, plot_type="division_plot", owner=_make_person("ID-9"))
    assert detail_queries() == before

    # Deleting the person leaves the plot without owner (SET_NULL).
    plot.owner.delete()
    plot.refresh_from_db()
    assert plot.owner is None


@pytest.mark.django_db
def test_settings_are_read_once_per_request(community, staff_client):
    case = _make_case(community)
    with CaptureQueriesContext(connection) as queries:
        staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"]))
    setting_reads = [q for q in queries if "core_systemsetting" in q["sql"]]
    # One bulk load for get_setting (+ the menu label lookup of core.menu_labels).
    assert len(setting_reads) <= 2


@pytest.mark.django_db
def test_settings_memo_sees_changes_made_during_the_request(db):
    begin_settings_memo()
    try:
        assert get_setting("caseNumberPrefix", "CASE") == "CASE"
        with CaptureQueriesContext(connection) as queries:
            get_setting("caseNumberPrefix", "CASE")
        assert len(queries) == 0
        set_setting("caseNumberPrefix", "ΥΠ")
        assert get_setting("caseNumberPrefix", "CASE") == "ΥΠ"
    finally:
        end_settings_memo()
    # Outside a request every lookup reads the database.
    with CaptureQueriesContext(connection) as queries:
        assert get_setting("caseNumberPrefix", "CASE") == "ΥΠ"
    assert len(queries) == 1


@pytest.mark.django_db
def test_section_labels_change_between_requests(community, staff_client):
    from cases.section_labels import save_case_section_label

    case = _make_case(community)
    staff_client.get(reverse("cases:detail", args=[case.pk]))
    save_case_section_label("3", "Τεμάχια από ρυθμίσεις")
    html = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Τεμάχια από ρυθμίσεις" in html


# --- 10/11. Refactor guards ---------------------------------------------------------------------


def test_views_stay_importable_from_cases_views():
    from cases import urls, views

    for pattern in urls.urlpatterns:
        assert getattr(views, pattern.callback.__name__) is pattern.callback


@pytest.mark.django_db
def test_section_7_comments_field_is_removed(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert 'name="section7_comments"' not in html
    assert 'name="section8_comments"' not in html
    assert "Σχόλια / Παρατηρήσεις Ενότητας 7" not in html


def test_consultation_help_texts_refer_to_7_4():
    from cases.models import Consultation

    for field in Consultation._meta.fields:
        assert "8.4" not in (field.help_text or "")


# --- Migration 0027 keeps stored owners and section 7 comments ------------------------------------


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_migration_0027_preserves_owner_and_comments():
    from django.db.migrations.executor import MigrationExecutor

    before = [("cases", "0026_dedupe_approved_design_plots")]
    after = [("cases", "0027_owner_fk_section7_comments")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
        loader = MigrationExecutor(connection).loader
        apps = loader.project_state(list(loader.applied_migrations)).apps
        Community = apps.get_model("core", "Community")
        CaseModel = apps.get_model("cases", "Case")
        Plot = apps.get_model("cases", "ApprovedDesignPlot")
        PersonModel = apps.get_model("applications", "Person")
        community = Community.objects.create(
            district="Λ", name="Μ", contact_email="m@example.org", community_folder_code="M-1"
        )
        case = CaseModel.objects.create(
            community=community,
            case_number="MIG-0027",
            start_date=date(2026, 1, 1),
            contact_email="m@example.org",
            section8_comments="Σχόλια 7",
        )
        person = PersonModel.objects.create(
            identity_number="MIG-P",
            first_name="Α",
            last_name="Β",
            date_of_birth=date(1990, 1, 1),
            birth_place="Λ",
            birth_country="Κ",
            parents_birth_place="Λ",
            parents_birth_country="Κ",
        )
        owned = Plot.objects.create(case=case, plot_type="division_plot", owner_person_id=person.pk)
        dangling = Plot.objects.create(case=case, plot_type="division_plot", owner_person_id=999999)

        MigrationExecutor(connection).migrate(after)
        loader = MigrationExecutor(connection).loader
        apps = loader.project_state(list(loader.applied_migrations)).apps
        Plot = apps.get_model("cases", "ApprovedDesignPlot")
        assert Plot.objects.get(pk=owned.pk).owner_id == person.pk
        assert Plot.objects.get(pk=dangling.pk).owner_id is None
        assert apps.get_model("cases", "Case").objects.get(pk=case.pk).section7_comments == "Σχόλια 7"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db
def test_announcement_stages_have_wizard_prev_next_navigation(community, staff_client):
    cycle = _cycle(community, published=True)
    url = reverse("announcements:detail", args=[cycle.pk])
    details = staff_client.get(url, {"stage": "details"}).content.decode()
    assert "data-stage-prev" not in details
    assert 'data-stage-next="submission"' in details
    assert 'form="announcement-details-form"' in details
    submission = staff_client.get(url, {"stage": "submission"}).content.decode()
    assert 'data-stage-prev="details"' in submission
    assert "data-stage-next-disabled" in submission
    assert "data-save-announcement-details" not in submission
