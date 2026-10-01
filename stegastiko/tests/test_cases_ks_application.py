"""Tests for the Κ.Σ./Δ.Δ. application (Αίτηση Α, Ενότητες 1–9).

Scenario ids refer to Μέρος Β §Β.7 of the requirements.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from cases.models import (
    Case,
    CompletenessCheck,
    Field,
    InfrastructureCheck,
    Parcel,
    SubmissionCycle,
    ValuationReferral,
    YesNo,
)
from cases.services import (
    announcement_readiness,
    build_announcement_text,
    create_deficiency_email,
    publish_announcement,
    section8_completion,
)
from cases.views import section_screens_for
from core.models import ActionHistory, Community


@pytest.fixture
def community(db):
    return Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )


@pytest.fixture
def staff_client(db, client):
    user = get_user_model().objects.create_user(username="officer", password="secret")
    client.force_login(user)
    return client


def _make_case(community, case_type=Case.CaseType.NEW_DIVISION, number="CASE-ABG-01"):
    return Case.objects.create(
        community=community,
        case_number=number,
        case_type=case_type,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )


def _ready_parcel(case, **overrides):
    values = {
        "design_lot_number": "1",
        "tkx_lot_number": "301",
        "final_area_sqm": Decimal("600"),
        "has_separate_title": YesNo.YES,
        "valuation_amount": Decimal("70000"),
    }
    values.update(overrides)
    return Parcel.objects.create(case=case, **values)


def _make_case_ready_for_announcement(community, number="CASE-ABG-01"):
    case = _make_case(community, number=number)
    InfrastructureCheck.objects.create(
        case=case,
        check_date=date(2027, 5, 15),
        curbs_ready=True,
        pavements_ready=True,
        asphalt_ready=True,
    )
    case.dls_response_date = date(2027, 6, 1)
    case.save()
    _ready_parcel(case)
    return case


# --- Scenario 1: two parallel cases of different type in the same community ---


@pytest.mark.django_db
def test_same_community_holds_both_case_types(community):
    new_division = _make_case(community, number="CASE-ABG-02")
    unallocated = _make_case(
        community, case_type=Case.CaseType.UNALLOCATED_PLOTS, number="CASE-ABG-01"
    )
    assert new_division.is_new_division
    assert not unallocated.is_new_division
    assert community.cases.count() == 2


@pytest.mark.django_db
def test_unallocated_case_skips_sections_2_to_8_7(community):
    """§Α.3.3 An unallocated-plots case has no Αίτηση Α, so it goes straight to 8.8."""
    unallocated = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    assert unallocated.applicable_sections == ("1", "8-plots", "9")
    for skipped in ("2", "3", "4", "5", "6", "7", "8"):
        assert skipped not in unallocated.applicable_sections


@pytest.mark.django_db
def test_unallocated_case_blocks_section_screen(community, staff_client):
    unallocated = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    blocked = staff_client.get(
        reverse("cases:section_edit", args=[unallocated.pk, "3"])
    )
    assert blocked.status_code == 404
    allowed = staff_client.get(
        reverse("cases:section_edit", args=[unallocated.pk, "8-plots"])
    )
    assert allowed.status_code == 200


# --- Scenario 6: Ενότητα 2 keeps every dated completeness check ---


@pytest.mark.django_db
def test_completeness_checks_are_sequential_and_latest_wins(community):
    case = _make_case(community)
    assert case.completeness_result == ""

    first = CompletenessCheck.objects.create(
        case=case,
        check_date=date(2026, 1, 20),
        result=YesNo.NO,
        deficiencies="Λείπει ο κατάλογος ενδιαφερόμενων οικογενειών.",
    )
    second = CompletenessCheck.objects.create(
        case=case, check_date=date(2026, 2, 15), result=YesNo.YES
    )

    assert first.sequence == 1
    assert second.sequence == 2
    # Both checks stay visible, and the current state comes from the last one.
    assert case.completeness_checks.count() == 2
    assert case.latest_completeness_check == second
    assert case.completeness_result == YesNo.YES


@pytest.mark.django_db
def test_deficiency_email_built_from_the_failing_check(community):
    case = _make_case(community)
    failing = CompletenessCheck.objects.create(
        case=case,
        check_date=date(2026, 1, 20),
        result=YesNo.NO,
        deficiencies="Λείπει ο κατάλογος ενδιαφερόμενων οικογενειών.",
    )
    communication = create_deficiency_email(failing)
    assert communication.recipient == community.contact_email
    assert "Λείπει ο κατάλογος" in communication.body
    assert "1ος έλεγχος" in communication.subject


@pytest.mark.django_db
def test_deficiency_email_rejected_for_passing_or_empty_check(community):
    case = _make_case(community)
    passing = CompletenessCheck.objects.create(
        case=case, check_date=date(2026, 2, 15), result=YesNo.YES
    )
    with pytest.raises(ValidationError):
        create_deficiency_email(passing)

    empty = CompletenessCheck.objects.create(
        case=case, check_date=date(2026, 3, 1), result=YesNo.NO
    )
    with pytest.raises(ValidationError):
        create_deficiency_email(empty)


# --- Scenario 12: a plot without a separate title is valued through a ΤΚΧ referral ---


@pytest.mark.django_db
def test_disposal_price_is_a_quarter_of_the_value(community):
    case = _make_case(community)
    parcel = _ready_parcel(case, valuation_amount=Decimal("80000"))
    assert parcel.disposal_price == Decimal("20000.00")
    assert parcel.is_valued


@pytest.mark.django_db
def test_plot_without_title_takes_its_value_from_the_referral(community):
    case = _make_case(community)
    referral = ValuationReferral.objects.create(
        case=case,
        letter_date=date(2027, 2, 2),
        reference_number="ΤΚΧ-77",
        response_date=date(2027, 3, 20),
    )
    parcel = _ready_parcel(
        case,
        has_separate_title=YesNo.NO,
        valuation_amount=Decimal("60000"),
        valuation_referral=referral,
    )
    assert parcel.valuation_referral == referral
    assert parcel.disposal_price == Decimal("15000.00")


@pytest.mark.django_db
def test_section8_completion_requires_value_and_price_on_every_plot(community):
    case = _make_case(community)
    case.dls_response_date = date(2027, 6, 1)
    case.save()
    _ready_parcel(case)
    unvalued = Parcel.objects.create(case=case, design_lot_number="2")

    completion = section8_completion(case)
    assert completion["parcels_count"] == 2
    assert not completion["all_valued"]
    assert not completion["is_complete"]

    unvalued.valuation_amount = Decimal("70000")
    unvalued.final_area_sqm = Decimal("610")
    unvalued.save()

    completion = section8_completion(case)
    assert completion["all_valued"] and completion["all_priced"]
    assert completion["is_complete"]


# --- Scenario 11: the 9.4 readiness check gates the announcement ---


@pytest.mark.django_db
def test_announcement_blocked_without_infrastructure_check(community):
    case = _make_case(community)
    case.dls_response_date = date(2027, 6, 1)
    case.save()
    _ready_parcel(case)

    readiness = announcement_readiness(case)
    assert not readiness["can_start"]

    InfrastructureCheck.objects.create(
        case=case,
        check_date=date(2027, 3, 10),
        curbs_ready=True,
        pavements_ready=True,
        asphalt_ready=False,
    )
    assert not announcement_readiness(case)["can_start"]

    InfrastructureCheck.objects.create(
        case=case,
        check_date=date(2027, 5, 15),
        curbs_ready=True,
        pavements_ready=True,
        asphalt_ready=True,
    )
    assert announcement_readiness(case)["can_start"]


@pytest.mark.django_db
def test_announcement_blocked_without_values(community):
    case = _make_case(community)
    InfrastructureCheck.objects.create(
        case=case,
        check_date=date(2027, 5, 15),
        curbs_ready=True,
        pavements_ready=True,
        asphalt_ready=True,
    )
    case.dls_response_date = date(2027, 6, 1)
    case.save()
    Parcel.objects.create(case=case, design_lot_number="1", final_area_sqm=Decimal("600"))

    assert not announcement_readiness(case)["can_start"]


@pytest.mark.django_db
def test_publish_is_refused_while_a_linked_case_is_not_ready(community):
    ready = _make_case_ready_for_announcement(community, number="CASE-ABG-02")
    not_ready = _make_case(community, number="CASE-ABG-03")

    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )
    cycle.cases.add(ready, not_ready)
    cycle.announcement_text = build_announcement_text(cycle)
    cycle.save()

    with pytest.raises(ValidationError):
        publish_announcement(cycle)

    cycle.cases.remove(not_ready)
    publish_announcement(cycle)
    cycle.refresh_from_db()
    assert cycle.is_published


# --- Scenario 2: one announcement mixing an old and a new split ---


@pytest.mark.django_db
def test_one_announcement_covers_old_and_new_split(community):
    new_division = _make_case_ready_for_announcement(community, number="CASE-ABG-02")
    field = Field.objects.create(case=new_division, code="FLD-ABG-02")
    _ready_parcel(new_division, design_lot_number="2", field=field)

    unallocated = _make_case(
        community, case_type=Case.CaseType.UNALLOCATED_PLOTS, number="CASE-ABG-01"
    )
    _ready_parcel(unallocated, design_lot_number="U-1", valuation_amount=Decimal("80000"))

    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )
    cycle.cases.add(new_division, unallocated)

    # 9.1 available plots are counted across both cases of the community.
    assert cycle.available_plots_count == 3
    assert "Αριθμός διαθέσιμων οικοπέδων: 3" in build_announcement_text(cycle)
    # Both cases reach the announcement from their own folder.
    assert new_division.submission_cycles.count() == 1
    assert unallocated.submission_cycles.count() == 1


@pytest.mark.django_db
def test_available_plots_exclude_unvalued_parcels(community):
    case = _make_case_ready_for_announcement(community)
    Parcel.objects.create(case=case, design_lot_number="pending")
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )
    cycle.cases.add(case)
    assert case.parcels.count() == 2
    assert cycle.available_plots_count == 1


# --- §Β.1.3 history covers the many-to-many announcement link ---


@pytest.mark.django_db
def test_linking_a_case_to_an_announcement_is_audited(community):
    case = _make_case(community)
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )
    cycle.cases.add(case)
    assert ActionHistory.objects.filter(
        entity_type="SubmissionCycle", field_name="cases", new_value=str(case.pk)
    ).exists()

    cycle.cases.remove(case)
    assert ActionHistory.objects.filter(
        entity_type="SubmissionCycle", field_name="cases", old_value=str(case.pk)
    ).exists()


@pytest.mark.django_db
def test_completeness_check_changes_reach_the_case_history(community):
    case = _make_case(community)
    check = CompletenessCheck.objects.create(
        case=case, check_date=date(2026, 1, 20), result=YesNo.NO, deficiencies="Ελλείψεις"
    )
    check.result = YesNo.YES
    check.save()

    from cases.services import case_history

    entries = case_history(case)
    assert entries.filter(entity_type="CompletenessCheck", action="CREATE").exists()
    assert entries.filter(
        entity_type="CompletenessCheck", action="UPDATE", field_name="result"
    ).exists()


# --- Scenario 17: navigation reaches both lists and every case action ---


@pytest.mark.django_db
def test_home_and_nav_expose_both_application_kinds(staff_client):
    response = staff_client.get(reverse("home"))
    assert response.status_code == 200
    body = response.content.decode()
    assert reverse("cases:list") in body
    assert reverse("applications:list") in body


@pytest.mark.django_db
def test_case_screens_render(community, staff_client):
    case = _make_case_ready_for_announcement(community)
    CompletenessCheck.objects.create(
        case=case, check_date=date(2026, 2, 15), result=YesNo.YES
    )

    detail = staff_client.get(reverse("cases:detail", args=[case.pk]))
    assert detail.status_code == 200
    assert case.case_number.encode() in detail.content
    detail_html = detail.content.decode()
    assert "1.2 Μεγάλες εκτάσεις τουρκοκυπριακών περιουσιών" in detail_html
    assert "Ενότητα 7 — Σύσταση προς τον Υπουργό" in detail_html

    assert staff_client.get(reverse("cases:list")).status_code == 200
    assert staff_client.get(reverse("cases:create")).status_code == 200
    assert staff_client.get(reverse("cases:history", args=[case.pk])).status_code == 200
    assert (
        staff_client.get(reverse("cases:announcement_create", args=[case.pk])).status_code == 200
    )
    for section in section_screens_for(case):
        response = staff_client.get(reverse("cases:section_edit", args=[case.pk, section]))
        assert response.status_code == 200, f"Ενότητα {section} δεν ανοίγει"

    # Ενότητα 9 lives on the announcement screens, not the generic section screen.
    assert "9" in case.applicable_sections
    assert "9" not in section_screens_for(case)


@pytest.mark.django_db
def test_section_1_splits_readonly_11_and_editable_12(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "1"])).content.decode()
    assert "1.1 Βασικά στοιχεία" in html
    assert "1.2 Χαρακτηριστικά Κοινότητας για σκοπούς προτεραιότητας" in html
    assert "1.1 Τύπος διαδικασίας" in html
    assert "Μεγάλες εκτάσεις τουρκοκυπριακών περιουσιών" in html
    assert "1.2 Μεγάλες εκτάσεις" not in html
    assert case.case_number in html


@pytest.mark.django_db
def test_section_1_unallocated_hides_12_and_submission_date(community, staff_client):
    case = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "1"])).content.decode()
    assert "1.1 Βασικά στοιχεία" in html
    assert "1.2 Χαρακτηριστικά Κοινότητας" not in html
    assert 'name="submitted_at"' not in html


@pytest.mark.django_db
def test_section_edit_shows_persistent_case_actions_sidebar(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "4"])).content.decode()
    assert "case-actions-nav" in html
    assert reverse("cases:section_edit", args=[case.pk, "1"]) in html
    assert reverse("cases:section_edit", args=[case.pk, "8-plots"]) in html
    assert reverse("cases:announcement_create", args=[case.pk]) in html
    assert 'class="case-actions-nav__link is-active"' in html
    assert reverse("cases:section_edit", args=[case.pk, "4"]) in html


@pytest.mark.django_db
def test_case_screens_require_login(community, client):
    case = _make_case(community)
    for url in (
        reverse("cases:list"),
        reverse("cases:detail", args=[case.pk]),
        reverse("cases:section_edit", args=[case.pk, "1"]),
    ):
        assert client.get(url).status_code == 302


# --- Regression: native date inputs must round-trip stored dates ---


@pytest.mark.django_db
def test_date_fields_render_in_iso_so_they_are_not_silently_cleared(community, staff_client):
    """`<input type="date">` only accepts ISO, so a d/m/Y value renders empty and is lost."""
    case = _make_case(community)
    case.submitted_at = date(2026, 1, 10)
    case.save()

    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "1"])).content.decode()
    assert 'value="2026-01-10"' in html
    assert 'value="10/01/2026"' not in html


@pytest.mark.django_db
def test_saving_a_section_keeps_existing_dates(community, staff_client):
    case = _make_case(community)
    case.submitted_at = date(2026, 1, 10)
    case.save()

    url = reverse("cases:section_edit", args=[case.pk, "1"])
    html = staff_client.get(url).content.decode()
    # Post the value exactly as the browser would send it back.
    assert 'name="submitted_at"' in html
    response = staff_client.post(
        url,
        {
            "submitted_at": "2026-01-10",
            "contact_email": case.contact_email,
            "priority_other": "",
            "priority_documentation": "",
            "comments": "",
        },
    )
    assert response.status_code == 302
    case.refresh_from_db()
    assert case.submitted_at == date(2026, 1, 10)


@pytest.mark.django_db
def test_case_forms_use_greek_labels_with_section_numbers(community, staff_client):
    """Ελληνικό UI: labels must not fall back to humanised English field names."""
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "8"])).content.decode()
    assert "8.1 Ημερομηνία ανάθεσης μελέτης" in html
    assert "Survey assignment date" not in html
    assert "Works progress stage" not in html


@pytest.mark.django_db
def test_publication_rows_use_greek_labels(community, staff_client):
    """9.2 The publication formset is a separate model and needs labels too."""
    case = _make_case_ready_for_announcement(community)
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )
    cycle.cases.add(case)
    html = staff_client.get(
        reverse("cases:announcement_detail", args=[case.pk, cycle.pk])
    ).content.decode()
    assert "9.2 Τρόπος δημοσίευσης" in html
    assert "9.2 Ημερομηνία δημοσίευσης" in html
    assert ">Method:</label>" not in html
    assert ">Published on:</label>" not in html


@pytest.mark.django_db
def test_no_form_label_falls_back_to_english(community, staff_client):
    """Sweep every section screen for a label that is not Greek."""
    import re

    case = _make_case_ready_for_announcement(community)
    allowed_latin = ("Email", "DEMO", case.case_number)
    for section in section_screens_for(case):
        html = staff_client.get(
            reverse("cases:section_edit", args=[case.pk, section])
        ).content.decode()
        labels = re.findall(r"<label[^>]*>(.*?)</label>", html, re.S)
        for raw in labels:
            label = re.sub(r"<[^>]+>", "", raw).strip()
            if not label or not re.search(r"[A-Za-z]", label):
                continue
            assert any(token in label for token in allowed_latin), (
                f"Ενότητα {section}: μη ελληνική ετικέτα {label!r}"
            )


@pytest.mark.django_db
def test_announcement_case_choices_are_not_styled_as_text_inputs(community, staff_client):
    case = _make_case_ready_for_announcement(community)
    html = staff_client.get(
        reverse("cases:announcement_create", args=[case.pk])
    ).content.decode()
    assert 'class="checkbox-list"' in html
    assert 'type="checkbox" name="cases"' in html
    assert 'name="cases" class="input"' not in html


@pytest.mark.django_db
def test_evaluation_rows_identify_their_parcel(community, staff_client):
    case = _make_case(community)
    case.land_plots.create(parcel_number="123", sheet_plan="30/12", area_sqm=Decimal("4500"))
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "4"])).content.decode()
    assert "Τεμάχιο 123" in html


@pytest.mark.django_db
def test_technical_evaluation_action_saves_per_plot(community, staff_client):
    """The 4.1 action records morphology and suitability against each land plot."""
    case = _make_case(community)
    plot = case.land_plots.create(parcel_number="123", area_sqm=Decimal("4500"))

    url = reverse("cases:section_edit", args=[case.pk, "4"])
    response = staff_client.post(
        url,
        {
            "access_technical_evaluation": "Πρόσβαση σε εγγεγραμμένο δημόσιο δρόμο.",
            "section4_comments": "",
            "plot_evaluations-TOTAL_FORMS": "1",
            "plot_evaluations-INITIAL_FORMS": "1",
            "plot_evaluations-MIN_NUM_FORMS": "0",
            "plot_evaluations-MAX_NUM_FORMS": "1000",
            "plot_evaluations-0-id": str(plot.pk),
            "plot_evaluations-0-case": str(case.pk),
            "plot_evaluations-0-morphology": "flat",
            "plot_evaluations-0-morphology_comments": "Επίπεδο",
            "plot_evaluations-0-usable_area_sqm": "4000",
            "plot_evaluations-0-estimated_plots_count": "5",
            "plot_evaluations-0-technical_suitability": "suitable",
            "utility_services-TOTAL_FORMS": "0",
            "utility_services-INITIAL_FORMS": "0",
            "utility_services-MIN_NUM_FORMS": "0",
            "utility_services-MAX_NUM_FORMS": "1000",
        },
    )
    assert response.status_code == 302

    plot.refresh_from_db()
    case.refresh_from_db()
    assert plot.morphology == "flat"
    assert plot.estimated_plots_count == 5
    assert plot.technical_suitability == "suitable"
    assert case.access_technical_evaluation.startswith("Πρόσβαση")
