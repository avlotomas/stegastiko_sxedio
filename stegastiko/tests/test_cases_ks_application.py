"""Tests for the Κ.Σ./Δ.Δ. application (Αίτηση Α, Ενότητες 1–9).

Scenario ids refer to Μέρος Β §Β.7 of the requirements.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from cases.models import (
    Case,
    CompletenessCheck,
    Consultation,
    Field,
    InfrastructureCheck,
    LandPlot,
    Parcel,
    SubmissionCycle,
    UtilityServiceType,
    ValuationReferral,
    YesNo,
)
from cases.services import (
    announcement_readiness,
    build_announcement_text,
    case_communications,
    deficiency_email_subject,
    publish_announcement,
    section8_completion,
    send_deficiency_email,
)
from cases.forms import CompletenessCheckForm
from cases.views import section_screens_for
from core.models import ActionHistory, Attachment, Community
from core.services import set_setting


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
def staff_client(client, make_user):
    client.force_login(make_user("officer", "Προϊστάμενος ελέγχου"))
    return client


@pytest.fixture
def smtp_configured(db):
    set_setting("smtpHost", "smtp.example.org")
    set_setting("smtpFromEmail", "stegastiko@example.org")


def _make_case(community, case_type=Case.CaseType.NEW_DIVISION, number="CASE-ABG-01"):
    return Case.objects.create(
        community=community,
        case_number=number,
        case_type=case_type,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )


def _make_check(case, **overrides):
    values = {
        "check_date": date(2026, 1, 20),
        "result": YesNo.NO,
        "deficiencies": "Λείπει ο κατάλογος ενδιαφερόμενων οικογενειών.",
    }
    values.update(overrides)
    return CompletenessCheck.objects.create(case=case, **values)


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


# --- Scenario 6: Ενότητα 2 — multiple checks, current result by latest check date ---


@pytest.mark.django_db
def test_latest_completeness_check_is_picked_by_date_then_sequence(community):
    case = _make_case(community)
    assert case.completeness_result == ""

    first = _make_check(case, check_date=date(2026, 1, 20), result=YesNo.NO)
    second = _make_check(case, check_date=date(2026, 2, 15), result=YesNo.YES, deficiencies="")
    third = _make_check(case, check_date=date(2026, 2, 15), result=YesNo.NO)

    assert case.completeness_checks.count() == 3
    assert case.latest_completeness_check == third
    assert third.sequence > second.sequence > first.sequence
    assert case.completeness_result == YesNo.NO

    third.result = YesNo.YES
    third.deficiencies = ""
    third.save()

    assert case.latest_completeness_check == third
    assert case.completeness_result == YesNo.YES


@pytest.mark.django_db
def test_deficiency_email_is_sent_to_the_11_address_and_recorded(community, smtp_configured):
    case = _make_case(community)
    check = _make_check(case)
    communication = send_deficiency_email(
        check, "Ελλείψεις", "Λείπει ο κατάλογος ενδιαφερόμενων οικογενειών."
    )

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [community.contact_email]
    assert sent.from_email == "stegastiko@example.org"
    assert sent.body.startswith("Λείπει ο κατάλογος")
    assert communication.status == "sent"
    assert communication.sent_at is not None
    assert communication.body.startswith("Λείπει ο κατάλογος")
    # 2.2 Sending and its date reach the case history.
    assert ActionHistory.objects.filter(
        entity_type="Communication", case_id=case.pk, section_ref="2.2", action="CREATE"
    ).exists()


@pytest.mark.django_db
def test_deficiency_email_needs_contact_email_text_and_smtp(community, smtp_configured):
    case = _make_case(community)
    check = _make_check(case)
    communication = send_deficiency_email(check, "Ελλείψεις", "   ")
    assert communication.status == "sent"

    case.contact_email = ""
    case.save()
    with pytest.raises(ValidationError):
        send_deficiency_email(check, "Ελλείψεις", "Λείπει ο κατάλογος.")

    case.contact_email = community.contact_email
    case.save()
    set_setting("smtpHost", "")
    with pytest.raises(ValidationError):
        send_deficiency_email(check, "Ελλείψεις", "Λείπει ο κατάλογος.")
    assert len(mail.outbox) == 1
    assert case_communications(case).count() == 1


@pytest.mark.django_db
def test_deficiency_email_subject_comes_from_settings(community):
    case = _make_case(community)
    assert case.case_number in deficiency_email_subject(case)

    set_setting("deficiencyEmailSubject", "Υπόθεση {case_number} — {community}")
    assert deficiency_email_subject(case) == f"Υπόθεση {case.case_number} — ΑΒΓ"


@pytest.mark.django_db
def test_result_yes_clears_the_deficiencies(community):
    form = CompletenessCheckForm(
        data={"check_date": "2026-02-15", "result": YesNo.YES, "deficiencies": "Παλιές ελλείψεις"}
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["deficiencies"] == ""

    form = CompletenessCheckForm(
        data={"check_date": "2026-02-15", "result": YesNo.NO, "deficiencies": ""}
    )
    assert not form.is_valid()
    assert "deficiencies" in form.errors


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
    assert "Μεγάλες εκτάσεις τουρκοκυπριακών περιουσιών" in detail_html
    assert "1.2 Μεγάλες εκτάσεις" not in detail_html
    assert "7. Σύσταση προς Υπουργό" in detail_html

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
def test_section_2_uses_21_22_23_structure(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "2"])).content.decode()
    assert "2.1 Έλεγχοι πληρότητας" in html
    assert "2.2 Ελλείψεις και επικοινωνία" in html
    assert "2.3 Σχόλια / Παρατηρήσεις" in html
    assert "data-completeness-check-grid" in html
    assert 'data-completeness-sort="date"' in html
    assert reverse("cases:completeness_check_create", args=[case.pk]) in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "2.1 Έλεγχοι πληρότητας" in detail
    assert "Πίνακας ελέγχων πληρότητας" in detail
    assert "2.3 Σχόλια / Παρατηρήσεις" in detail


@pytest.mark.django_db
def test_case_create_includes_section_11_and_12(community, staff_client):
    html = staff_client.get(reverse("cases:create")).content.decode()
    assert "1.1 Βασικά στοιχεία" in html
    assert "1.2 Χαρακτηριστικά Κοινότητας για σκοπούς προτεραιότητας" in html
    assert "Μεγάλες εκτάσεις τουρκοκυπριακών περιουσιών" in html
    assert 'id="priority-section"' in html


@pytest.mark.django_db
def test_case_create_requires_contact_email(community, staff_client):
    community_no_email = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΧΩΡΙΣ EMAIL",
        contact_email="",
        community_folder_code="002",
    )
    response = staff_client.post(
        reverse("cases:create"),
        {
            "community": community_no_email.pk,
            "case_type": Case.CaseType.NEW_DIVISION,
            "submitted_at": "2026-01-15",
            "contact_email": "",
        },
    )
    assert response.status_code == 200
    assert "Απαιτείται ηλεκτρονική διεύθυνση επικοινωνίας" in response.content.decode()


@pytest.mark.django_db
def test_case_create_persists_section_12_priority(community, staff_client):
    response = staff_client.post(
        reverse("cases:create"),
        {
            "community": community.pk,
            "case_type": Case.CaseType.NEW_DIVISION,
            "submitted_at": "2026-01-15",
            "contact_email": community.contact_email,
            "priority_turkish_cypriot_properties": "on",
            "priority_documentation": "Τεκμηρίωση δοκιμής",
        },
    )
    assert response.status_code == 302
    case = Case.objects.get(community=community)
    assert case.priority_turkish_cypriot_properties is True
    assert case.priority_documentation == "Τεκμηρίωση δοκιμής"


@pytest.mark.django_db
def test_section_1_splits_readonly_11_and_editable_12(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "1"])).content.decode()
    assert "1.1 Βασικά στοιχεία" in html
    assert "1.2 Χαρακτηριστικά Κοινότητας για σκοπούς προτεραιότητας" in html
    assert "Τύπος διαδικασίας" in html
    assert "1.1 Τύπος διαδικασίας" not in html
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


def _detail_main_html(staff_client, case):
    """Detail page content without the case actions sidebar."""
    html = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    main = html.split('<div class="case-work-layout__main">', 1)[1]
    return main.split('<aside class="case-work-layout__aside"', 1)[0]


@pytest.mark.django_db
def test_case_detail_is_read_only_with_actions_in_sidebar(
    community, staff_client, smtp_configured
):
    case = _make_case(community)
    check = _make_check(case, deficiencies="Ελλείψεις")
    send_deficiency_email(check, "Ελλείψεις", "Ελλείψεις")

    html = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "case-actions-nav" in html
    assert reverse("cases:section_edit", args=[case.pk, "1"]) in html

    main = _detail_main_html(staff_client, case)
    assert "<form" not in main
    assert "data-communication-view" in main
    assert reverse("cases:section_edit", args=[case.pk, "1"]) not in main


@pytest.mark.django_db
def test_case_detail_section_titles_come_from_settings(community, staff_client):
    from cases.section_labels import save_case_section_label

    case = _make_case(community)
    save_case_section_label("2", "Πληρότητα αίτησης από ρυθμίσεις")
    save_case_section_label("8-plots", "Οικόπεδα από ρυθμίσεις")

    main = _detail_main_html(staff_client, case)
    assert '<h2 class="card__title">1. Βασικά στοιχεία και προτεραιότητα</h2>' in main
    assert '<h2 class="card__title">2. Πληρότητα αίτησης από ρυθμίσεις</h2>' in main
    assert '<h2 class="card__title">8. Οικόπεδα από ρυθμίσεις</h2>' in main
    assert '<h2 class="card__title">9. Γνωστοποίηση έναρξης αιτήσεων</h2>' in main
    assert main.count('<h2 class="card__title">') == 10


@pytest.mark.django_db
def test_case_detail_unallocated_shows_only_applicable_sections(community, staff_client):
    case = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    main = _detail_main_html(staff_client, case)
    assert main.count('<h2 class="card__title">') == 3
    assert "2 Έλεγχος πληρότητας" not in main


@pytest.mark.django_db
def test_section_2_grid_rows_show_email_action_for_each_check(community, staff_client):
    case = _make_case(community)
    url = reverse("cases:section_edit", args=[case.pk, "2"])
    first = _make_check(case, result=YesNo.NO, deficiencies="Ελλείψεις")
    second = _make_check(case, result=YesNo.YES, deficiencies="")
    html = staff_client.get(url).content.decode()
    assert reverse("cases:deficiency_email_send", args=[case.pk, first.pk]) in html
    assert reverse("cases:deficiency_email_send", args=[case.pk, second.pk]) in html
    assert html.count("Αποστολή Email") == 2
    # A check without deficiencies can still open the email dialog and send.
    assert f'data-copy-text="{second.deficiencies}"' in html


@pytest.mark.django_db
def test_send_email_button_is_disabled_without_11_address(community, staff_client):
    case = _make_case(community)
    _make_check(case, result=YesNo.NO, deficiencies="Ελλείψεις")
    url = reverse("cases:section_edit", args=[case.pk, "2"])
    html = staff_client.get(url).content.decode()
    assert "data-dialog-open=\"deficiency-email-dialog\"" in html
    assert "Αποστολή Email" in html

    case.contact_email = ""
    case.save()
    html = staff_client.get(url).content.decode()
    assert "data-dialog-open=\"deficiency-email-dialog\"" in html
    assert "Αποστολή Email" in html
    assert "disabled" in html


@pytest.mark.django_db
def test_email_dialog_is_prefilled_and_outside_the_section_form(
    community, staff_client, smtp_configured
):
    case = _make_case(community)
    check = _make_check(case, deficiencies="Λείπει η αίτηση.")
    set_setting("deficiencyEmailSubject", "Ελλείψεις {case_number}")
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "2"])).content.decode()

    start = html.index('<dialog id="deficiency-email-dialog"')
    dialog = html[start : html.index("</dialog>", start)]
    assert community.contact_email in dialog
    assert f'value="Ελλείψεις {case.case_number}"' in dialog
    assert "data-email-check-label" in dialog
    assert reverse("cases:deficiency_email_send", args=[case.pk, check.pk]) in html
    # Forms cannot nest: the section form must close before the dialog opens.
    section_form = html.index('<form method="post" class="app-form" novalidate>')
    assert html.index("</form>", section_form) < html.index("<dialog")


@pytest.mark.django_db
def test_deficiency_email_send_endpoint(community, staff_client, smtp_configured):
    case = _make_case(community)
    check = _make_check(case)
    url = reverse("cases:deficiency_email_send", args=[case.pk, check.pk])
    payload = {"subject": "Ελλείψεις", "body": "Λείπει ο κατάλογος."}

    response = staff_client.post(url, payload, HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"]
    assert community.contact_email in data["message"]
    assert "Απεστάλη" in data["log_html"]
    assert len(mail.outbox) == 1

    response = staff_client.post(
        url, {"subject": "Ελλείψεις", "body": ""}, HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 200
    assert response.json()["ok"]
    assert len(mail.outbox) == 2

    # Without JavaScript the form posts normally and returns to section 2.
    response = staff_client.post(url, payload)
    assert response.status_code == 302
    assert response.url == reverse("cases:section_edit", args=[case.pk, "2"])
    assert case_communications(case).count() == 3
    assert check.communications.count() == 3


@pytest.mark.django_db
def test_completeness_check_delete_is_blocked_when_check_has_emails(
    community, staff_client, smtp_configured
):
    case = _make_case(community)
    check = _make_check(case)
    send_deficiency_email(check, "Θέμα", "Κείμενο")
    url = reverse("cases:completeness_check_delete", args=[case.pk, check.pk])
    response = staff_client.post(url, **JSON)
    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert "δεν διαγράφεται" in payload["message"]
    assert case.completeness_checks.filter(pk=check.pk).exists()
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "2"])).content.decode()
    assert "data-completeness-check-delete-blocked-reason" in html
    assert "title=\"Δεν μπορείτε να διαγράψετε αυτόν τον έλεγχο επειδή έχουν ήδη σταλεί email ελλείψεων.\"" in html


@pytest.mark.django_db
def test_completeness_check_modal_create_and_edit(community, staff_client):
    case = _make_case(community)
    create_url = reverse("cases:completeness_check_create", args=[case.pk])
    assert staff_client.get(create_url).status_code == 404
    payload = staff_client.get(create_url, **JSON).json()
    assert payload["ok"] is True
    assert "2.1 Νέος έλεγχος" in payload["html"]

    response = staff_client.post(
        create_url,
        {"check_date": "2026-01-20", "result": YesNo.NO, "deficiencies": "Ελλείψεις"},
        **JSON,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "data-completeness-check-grid" in data["grid_html"]
    check = case.completeness_checks.get()

    edit_url = reverse("cases:completeness_check_edit", args=[case.pk, check.pk])
    response = staff_client.post(
        edit_url,
        {"check_date": "2026-02-15", "result": YesNo.YES, "deficiencies": "θα καθαριστεί"},
        **JSON,
    )
    assert response.status_code == 200
    check.refresh_from_db()
    assert check.result == YesNo.YES
    assert check.deficiencies == ""


@pytest.mark.django_db
def test_section_2_save_updates_only_comments(community, staff_client):
    case = _make_case(community)
    check = _make_check(case)
    url = reverse("cases:section_edit", args=[case.pk, "2"])
    response = staff_client.post(url, {"section2_comments": "Νέα σχόλια 2.3"})
    assert response.status_code == 302
    case.refresh_from_db()
    check.refresh_from_db()
    assert case.section2_comments == "Νέα σχόλια 2.3"
    assert check.deficiencies.startswith("Λείπει")


@pytest.mark.django_db
def test_sent_email_grid_links_to_detail_endpoint(community, staff_client, smtp_configured):
    case = _make_case(community)
    check = _make_check(case)
    communication = send_deficiency_email(check, "Ελλείψεις", "Πλήρες κείμενο email.")
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "2"])).content.decode()
    detail_url = reverse("cases:communication_detail", args=[case.pk, communication.pk])
    assert detail_url in html
    assert "data-communication-view" in html
    assert "data-communication-detail-url" in html
    assert 'data-communication-sort="sent-at"' in html
    assert "communication-email-view-dialog" in html
    assert "Προβολή" in html


@pytest.mark.django_db
def test_communication_detail_returns_stored_email(community, staff_client, smtp_configured):
    case = _make_case(community)
    check = _make_check(case)
    communication = send_deficiency_email(
        check, "Θέμα δοκιμής", "Σώμα μηνύματος με\nδύο γραμμές."
    )
    url = reverse("cases:communication_detail", args=[case.pk, communication.pk])
    response = staff_client.get(url, HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"]
    assert data["recipient"] == community.contact_email
    assert data["subject"] == "Θέμα δοκιμής"
    assert "δύο γραμμές" in data["body"]
    assert data["status_display"] == "Απεστάλη"


@pytest.mark.django_db
def test_communication_detail_rejects_other_case(community, staff_client, smtp_configured):
    case_a = _make_case(community)
    case_b = _make_case(community, number="CASE-ABG-02")
    communication = send_deficiency_email(_make_check(case_a), "Θέμα", "Κείμενο")
    url = reverse("cases:communication_detail", args=[case_b.pk, communication.pk])
    assert staff_client.get(url, HTTP_ACCEPT="application/json").status_code == 404


@pytest.mark.django_db
def test_deficiency_email_send_rejected_for_unallocated_case(
    community, staff_client, smtp_configured
):
    case = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    fake_check = CompletenessCheck.objects.create(
        case=_make_case(community, number="CASE-ABG-02"),
        check_date=date(2026, 1, 20),
        result=YesNo.NO,
        deficiencies="Κείμενο",
    )
    url = reverse("cases:deficiency_email_send", args=[case.pk, fake_check.pk])
    response = staff_client.post(url, {"subject": "Θέμα", "body": "Κείμενο"})
    assert response.status_code == 404
    assert mail.outbox == []


@pytest.mark.django_db
def test_existing_announcements_open_from_section_9_screen(community, staff_client):
    case = _make_case_ready_for_announcement(community)
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )
    cycle.cases.add(case)
    html = staff_client.get(reverse("cases:announcement_create", args=[case.pk])).content.decode()
    assert reverse("cases:announcement_detail", args=[case.pk, cycle.pk]) in html


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
def test_case_forms_use_greek_labels_without_section_prefix_on_fields(community, staff_client):
    """Ελληνικό UI: labels must not fall back to humanised English field names."""
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "8"])).content.decode()
    assert "Ημερομηνία ανάθεσης μελέτης" in html
    assert "8.1 Ημερομηνία ανάθεσης μελέτης" not in html
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
    assert "Τρόπος δημοσίευσης" in html
    assert "Ημερομηνία δημοσίευσης" in html
    assert "9.2 Τρόπος δημοσίευσης" not in html
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


# --- Ενότητα 4: 4.1 grid ανά τεμάχιο της 3.1 (μόνο επεξεργασία σε modal), 4.2–4.5 ---


def _evaluation_values(**overrides):
    values = {
        "morphology": LandPlot.Morphology.FLAT,
        "morphology_other": "",
        "morphology_comments": "Ομαλό ανάγλυφο",
        "usable_area_sqm": "4000",
        "estimated_cost": "125000.50",
        "estimated_plots_count": "5",
        "technical_suitability": LandPlot.SuitabilityDecision.SUITABLE,
    }
    values.update(overrides)
    return values


def _section4_post(**overrides):
    data = {
        "access_technical_evaluation": "Πρόσβαση σε εγγεγραμμένο δημόσιο δρόμο.",
        "section4_comments": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_section_4_uses_41_to_45_structure(community, staff_client):
    case = _make_case(community)
    plot = case.land_plots.create(
        parcel_number="123", sheet_plan="30/12", area_sqm=Decimal("4500"), zone="Κα4"
    )
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "4"])).content.decode()
    headings = (
        "4.1 Τεχνική αξιολόγηση ανά τεμάχιο",
        "4.2 Υπηρεσίες κοινής ωφέλειας",
        "4.3 Πρόσβαση",
        "4.4 Επισυναπτόμενα αρχεία",
        "4.5 Σχόλια / Παρατηρήσεις Ενότητας 4",
        "4.6 Στοιχεία επίσκεψης μηχανικού",
    )
    positions = [html.index(heading) for heading in headings]
    assert positions == sorted(positions)
    # 4.1 is a grid over the 3.1 plots: edit only, no add / delete, no inline formset.
    assert "data-land-plot-grid" in html
    assert reverse("cases:land_plot_evaluation", args=[case.pk, plot.pk]) in html
    assert reverse("cases:land_plot_create", args=[case.pk]) not in html
    assert reverse("cases:land_plot_delete", args=[case.pk, plot.pk]) not in html
    assert "data-land-plot-delete" not in html
    assert "plot_evaluations-TOTAL_FORMS" not in html
    assert 'id="land-plot-dialog"' in html
    assert 'enctype="multipart/form-data"' in html
    assert "Κα4" in html
    assert "Αξιοποιήσιμο εμβαδόν γης (τ.μ.)" in html
    assert "Εκτιμώμενο κόστος" in html
    assert "Κατά προσέγγιση αξιοποιήσιμο" not in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    positions = [detail.index(heading) for heading in headings]
    assert positions == sorted(positions)


@pytest.mark.django_db
def test_section_4_rows_follow_the_section_3_plots(community, staff_client):
    case = _make_case(community)
    staff_client.post(
        reverse("cases:land_plot_create", args=[case.pk]), _plot_values(parcel_number="100"), **JSON
    )
    staff_client.post(
        reverse("cases:land_plot_create", args=[case.pk]), _plot_values(parcel_number="200"), **JSON
    )
    url = reverse("cases:section_edit", args=[case.pk, "4"])
    html = staff_client.get(url).content.decode()
    for plot in case.land_plots.all():
        assert reverse("cases:land_plot_evaluation", args=[case.pk, plot.pk]) in html

    removed = case.land_plots.get(parcel_number="200")
    staff_client.post(reverse("cases:land_plot_delete", args=[case.pk, removed.pk]), **JSON)
    html = staff_client.get(url).content.decode()
    assert reverse("cases:land_plot_evaluation", args=[case.pk, removed.pk]) not in html
    assert html.count("data-land-plot-open=") == 1


@pytest.mark.django_db
def test_plot_evaluation_modal_saves_41_only(community, staff_client):
    case = _make_case(community)
    plot = case.land_plots.create(parcel_number="123", area_sqm=Decimal("4500"), zone="Κα4")
    url = reverse("cases:land_plot_evaluation", args=[case.pk, plot.pk])
    assert staff_client.get(url).status_code == 404

    form = staff_client.get(url, **JSON).json()
    assert form["ok"] is True
    assert "4.1 Τεχνική αξιολόγηση τεμαχίου 123" in form["html"]
    assert "Στοιχεία τεμαχίου (από 3.1)" in form["html"]
    assert 'name="parcel_number"' not in form["html"]
    assert "4500" in form["html"]

    payload = staff_client.post(url, _evaluation_values(parcel_number="999"), **JSON).json()
    assert payload["ok"] is True
    assert "123" in payload["message"]
    assert "data-land-plot-grid" in payload["grid_html"]
    assert "Κατάλληλο" in payload["grid_html"]

    plot.refresh_from_db()
    assert plot.parcel_number == "123"
    assert plot.morphology == LandPlot.Morphology.FLAT
    assert plot.usable_area_sqm == Decimal("4000")
    assert plot.estimated_cost == Decimal("125000.50")
    assert plot.estimated_plots_count == 5
    assert plot.technical_suitability == LandPlot.SuitabilityDecision.SUITABLE
    assert case.land_plots.count() == 1
    assert ActionHistory.objects.filter(
        entity_type="LandPlot",
        action="UPDATE",
        case_id=case.pk,
        section_ref="4.1",
        field_name="technical_suitability",
    ).exists()


@pytest.mark.django_db
def test_plot_evaluation_other_morphology_is_described_in_the_same_cell(community, staff_client):
    case = _make_case(community)
    plot = case.land_plots.create(parcel_number="123")
    url = reverse("cases:land_plot_evaluation", args=[case.pk, plot.pk])

    missing = staff_client.post(
        url, _evaluation_values(morphology=LandPlot.Morphology.OTHER), **JSON
    )
    assert missing.status_code == 400
    assert "Συμπληρώστε την περιγραφή της άλλης τεχνικής ιδιαιτερότητας (4.1)." in missing.json()["html"]
    plot.refresh_from_db()
    assert plot.morphology == ""

    staff_client.post(
        url,
        _evaluation_values(morphology=LandPlot.Morphology.OTHER, morphology_other="Βραχώδες"),
        **JSON,
    )
    plot.refresh_from_db()
    assert plot.morphology_display == "Άλλη τεχνική ιδιαιτερότητα: Βραχώδες"
    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Άλλη τεχνική ιδιαιτερότητα: Βραχώδες" in detail

    staff_client.post(url, _evaluation_values(), **JSON)
    plot.refresh_from_db()
    assert plot.morphology_other == ""


@pytest.mark.django_db
def test_plot_evaluation_modal_is_scoped_to_its_case(community, staff_client):
    case = _make_case(community)
    other_case = _make_case(community, number="CASE-ABG-02")
    plot = other_case.land_plots.create(parcel_number="999")
    url = reverse("cases:land_plot_evaluation", args=[case.pk, plot.pk])
    assert staff_client.get(url, **JSON).status_code == 404
    assert staff_client.post(url, _evaluation_values(), **JSON).status_code == 404

    unallocated = _make_case(
        community, case_type=Case.CaseType.UNALLOCATED_PLOTS, number="CASE-ABG-03"
    )
    plot = unallocated.land_plots.create(parcel_number="1")
    url = reverse("cases:land_plot_evaluation", args=[unallocated.pk, plot.pk])
    assert staff_client.get(url, **JSON).status_code == 404


@pytest.mark.django_db
def test_section_4_blank_pdf_export(community, staff_client):
    case = _make_case(community)
    case.land_plots.create(
        parcel_number="123", sheet_plan="30/12", area_sqm=Decimal("4500"), zone="Κα4"
    )
    UtilityServiceType = __import__(
        "cases.models", fromlist=["UtilityServiceType"]
    ).UtilityServiceType
    UtilityServiceType.objects.get_or_create(name="ΑΗΚ", defaults={"display_order": 1})

    edit_html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "4"])).content.decode()
    assert reverse("cases:section_4_blank_pdf", args=[case.pk]) in edit_html
    assert "Εξαγωγή PDF φόρμας" in edit_html

    url = reverse("cases:section_4_blank_pdf", args=[case.pk])
    response = staff_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "technical_evaluation_" in response["Content-Disposition"]
    assert len(response.content) > 2000


@pytest.mark.django_db
def test_section_6_report_pdf_export(community, staff_client):
    from cases.section6_report_pdf import REPORT_TITLE, section6_report_context

    case = _make_case(community)
    case.priority_protection_zones = True
    case.state_land_remains_sufficient = YesNo.YES
    case.access_technical_evaluation = "Πρόσβαση από τον κύριο δρόμο."
    case.save()
    case.land_plots.create(
        parcel_number="123",
        area_sqm=Decimal("4500"),
        technical_suitability=LandPlot.SuitabilityDecision.SUITABLE,
        suitability_decision=LandPlot.SuitabilityDecision.CONDITIONAL,
        suitability_justification="Απαιτείται διαπλάτυνση δρόμου.",
    )
    case.consultations.create(
        stage=Consultation.Stage.SUITABILITY, department=Consultation.Department.TKX, topic="Αξία"
    )
    case.consultations.create(
        stage=Consultation.Stage.DIVISION, department=Consultation.Department.AHK, topic="Δίκτυο"
    )

    context = section6_report_context(case)
    assert context["report_title"] == REPORT_TITLE
    assert [c.topic for c in context["summary"]["consultations"]] == ["Αξία"]
    assert context["heading_66"].startswith("6.6 ")
    assert context["heading_62"] == "6.2 Τεχνική αξιολόγηση ανά τεμάχιο"
    assert context["heading_access"] == "Πρόσβαση"

    # Ενότητα 6 shows the 4.1-style grid read-only under heading 6.2.
    section6_html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "6"])).content.decode()
    assert "Εκτιμώμενος αριθμός οικοπέδων" in section6_html
    assert "data-land-plot-open" not in section6_html

    for url_name, section in (("cases:section_edit", "6"), ("cases:detail", None)):
        args = [case.pk, section] if section else [case.pk]
        html = staff_client.get(reverse(url_name, args=args)).content.decode()
        assert reverse("cases:section_6_report_pdf", args=[case.pk]) in html

    response = staff_client.get(reverse("cases:section_6_report_pdf", args=[case.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "pinakes_aksiologisis_" in response["Content-Disposition"]


@pytest.mark.django_db
def test_section_6_report_pdf_not_available_for_unallocated_plots(community, staff_client):
    case = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    response = staff_client.get(reverse("cases:section_6_report_pdf", args=[case.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_section_4_saves_43_44_45_with_case_files(community, staff_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    case = _make_case(community)
    url = reverse("cases:section_edit", args=[case.pk, "4"])
    data = _section4_post(
        section4_comments="Σχόλια 4.5",
        engineer_full_name="Μαρία Παπαδοπούλου",
        technical_visit_date="2026-03-15",
    )
    data["new_files"] = [
        SimpleUploadedFile("ekthesi.pdf", b"%PDF-1", content_type="application/pdf"),
        SimpleUploadedFile("photo.jpg", b"jpg", content_type="image/jpeg"),
    ]
    assert staff_client.post(url, data).status_code == 302

    case.refresh_from_db()
    assert case.access_technical_evaluation.startswith("Πρόσβαση")
    assert case.section4_comments == "Σχόλια 4.5"
    assert case.engineer_full_name == "Μαρία Παπαδοπούλου"
    assert str(case.technical_visit_date) == "2026-03-15"
    attachments = {a.filename: a for a in case.attachments.all()}
    assert set(attachments) == {"ekthesi.pdf", "photo.jpg"}
    assert all(a.section_ref == "4.4" for a in attachments.values())
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="CREATE", case_id=case.pk, section_ref="4.4"
    ).count() == 2

    download_url = reverse("cases:attachment_download", args=[case.pk, attachments["ekthesi.pdf"].pk])
    assert staff_client.get(download_url).content == b"%PDF-1"
    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert download_url in detail
    other_case = _make_case(community, number="CASE-ABG-02")
    assert staff_client.get(
        reverse("cases:attachment_download", args=[other_case.pk, attachments["ekthesi.pdf"].pk])
    ).status_code == 404

    data = _section4_post(remove_attachments=[str(attachments["photo.jpg"].pk)])
    staff_client.post(url, data)
    assert {a.filename for a in case.attachments.all()} == {"ekthesi.pdf"}
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="DELETE", case_id=case.pk, section_ref="4.4"
    ).exists()


@pytest.mark.django_db
def test_land_plot_delete_warns_when_technical_evaluation_exists(community, staff_client):
    case = _make_case(community)
    plot = case.land_plots.create(parcel_number="123")
    plain = case.land_plots.create(parcel_number="456")
    staff_client.post(
        reverse("cases:land_plot_evaluation", args=[case.pk, plot.pk]), _evaluation_values(), **JSON
    )
    plot.refresh_from_db()
    assert plot.has_technical_evaluation
    assert not plain.has_technical_evaluation

    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "3"])).content.decode()
    assert html.count("data-land-plot-warning=") == 1
    assert "υπάρχει τεχνική αξιολόγηση (Ενότητα 4.1) για το τεμάχιο 123" in html

    delete_url = reverse("cases:land_plot_delete", args=[case.pk, plot.pk])
    refused = staff_client.post(delete_url, **JSON)
    assert refused.status_code == 409
    payload = refused.json()
    assert payload["ok"] is False
    assert payload["requires_confirmation"] is True
    assert "τεχνική αξιολόγηση (Ενότητα 4.1)" in payload["message"]
    assert case.land_plots.filter(pk=plot.pk).exists()

    confirmed = staff_client.post(delete_url, {"confirm_evaluation": "1"}, **JSON).json()
    assert confirmed["ok"] is True
    assert not case.land_plots.filter(pk=plot.pk).exists()

    # Without a 4.1 evaluation there is nothing extra to confirm.
    plain_delete = reverse("cases:land_plot_delete", args=[case.pk, plain.pk])
    assert staff_client.post(plain_delete, **JSON).json()["ok"] is True


# --- Ενότητα 3: 3.1 πίνακας τεμαχίων (grid + modal), 3.2 έλεγχος κρατικής γης, 3.3 σχόλια ---

JSON = {"HTTP_ACCEPT": "application/json"}


def _plot_values(**overrides):
    values = {
        "parcel_number": "123",
        "sheet_plan": "30/12",
        "location": "Λιβάδι",
        "ownership_status": LandPlot.OwnershipStatus.STATE_LAND,
        "ownership_other": "",
        "area_sqm": "4500",
        "zone": "Κα4",
        "inside_development_zone": YesNo.YES,
        "access": LandPlot.Access.PUBLIC_ROAD,
        "access_other": "",
        "comments": "",
    }
    values.update(overrides)
    return values


def _section3_post(**overrides):
    data = {
        "state_land_remains_sufficient": YesNo.YES,
        "section3_comments": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_section_3_uses_31_32_33_structure(community, staff_client):
    case = _make_case(community)
    case.land_plots.create(parcel_number="123")
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "3"])).content.decode()
    positions = [
        html.index("3.1 Πίνακας τεμαχίων"),
        html.index("3.2 Έλεγχος επάρκειας κρατικής γης"),
        html.index("3.3 Σχόλια / Παρατηρήσεις Ενότητας 3"),
    ]
    assert positions == sorted(positions)
    assert "Μετά την προτεινόμενη αξιοποίηση θα παραμένουν στην Κοινότητα" in html
    # 3.1 is a grid with add / edit / delete actions and a modal; no inline plot formset.
    assert "data-land-plot-grid" in html
    assert reverse("cases:land_plot_create", args=[case.pk]) in html
    plot = case.land_plots.get()
    assert reverse("cases:land_plot_edit", args=[case.pk, plot.pk]) in html
    assert reverse("cases:land_plot_delete", args=[case.pk, plot.pk]) in html
    assert 'id="land-plot-dialog"' in html
    assert "land_plots-TOTAL_FORMS" not in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    for heading in (
        "3.1 Πίνακας τεμαχίων",
        "3.2 Έλεγχος επάρκειας κρατικής γης",
        "3.3 Σχόλια / Παρατηρήσεις Ενότητας 3",
        "Αρχεία τεμαχίου",
    ):
        assert heading in detail


@pytest.mark.django_db
def test_section_3_saves_32_33_without_touching_plots(community, staff_client):
    case = _make_case(community)
    case.land_plots.create(parcel_number="123")
    url = reverse("cases:section_edit", args=[case.pk, "3"])
    assert staff_client.post(url, _section3_post()).status_code == 302
    case.refresh_from_db()
    assert case.state_land_remains_sufficient == YesNo.YES
    assert case.land_plots.count() == 1


@pytest.mark.django_db
def test_land_plot_modal_adds_and_edits_a_plot(community, staff_client):
    case = _make_case(community)
    create_url = reverse("cases:land_plot_create", args=[case.pk])

    form = staff_client.get(create_url, **JSON).json()
    assert form["ok"] is True
    assert "3.1 Νέο τεμάχιο" in form["html"]
    assert 'enctype="multipart/form-data"' in form["html"]
    assert "multiple" in form["html"]

    response = staff_client.post(create_url, _plot_values(), **JSON)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "data-land-plot-grid" in payload["grid_html"]
    assert "Λιβάδι" in payload["grid_html"]
    plot = case.land_plots.get()
    assert plot.ownership_status == LandPlot.OwnershipStatus.STATE_LAND
    assert plot.access == LandPlot.Access.PUBLIC_ROAD
    assert plot.inside_development_zone == YesNo.YES
    assert ActionHistory.objects.filter(
        entity_type="LandPlot", action="CREATE", case_id=case.pk, section_ref="3.1"
    ).exists()

    edit_url = reverse("cases:land_plot_edit", args=[case.pk, plot.pk])
    form = staff_client.get(edit_url, **JSON).json()
    assert "3.1 Επεξεργασία τεμαχίου" in form["html"]
    assert 'value="Λιβάδι"' in form["html"]

    staff_client.post(edit_url, _plot_values(location="Αμπελάκια"), **JSON)
    plot.refresh_from_db()
    assert plot.location == "Αμπελάκια"
    assert case.land_plots.count() == 1


@pytest.mark.django_db
def test_land_plot_modal_is_scoped_to_its_case(community, staff_client):
    case = _make_case(community)
    other_case = _make_case(community, number="CASE-ABG-02")
    plot = other_case.land_plots.create(parcel_number="999")
    edit_url = reverse("cases:land_plot_edit", args=[case.pk, plot.pk])
    delete_url = reverse("cases:land_plot_delete", args=[case.pk, plot.pk])
    assert staff_client.get(edit_url, **JSON).status_code == 404
    assert staff_client.post(edit_url, _plot_values(), **JSON).status_code == 404
    assert staff_client.post(delete_url, **JSON).status_code == 404
    assert other_case.land_plots.filter(pk=plot.pk).exists()


@pytest.mark.django_db
def test_land_plot_other_is_described_in_the_same_cell(community, staff_client):
    case = _make_case(community)
    create_url = reverse("cases:land_plot_create", args=[case.pk])

    missing = staff_client.post(
        create_url,
        _plot_values(
            ownership_status=LandPlot.OwnershipStatus.OTHER, access=LandPlot.Access.OTHER
        ),
        **JSON,
    )
    assert missing.status_code == 400
    assert missing.json()["ok"] is False
    assert "Συμπληρώστε το είδος της άλλης ιδιοκτησίας (3.1)." in missing.json()["html"]
    assert "Συμπληρώστε τη διευκρίνιση της πρόσβασης (3.1)." in missing.json()["html"]
    assert not case.land_plots.exists()

    staff_client.post(
        create_url,
        _plot_values(
            ownership_status=LandPlot.OwnershipStatus.OTHER,
            ownership_other="Εκκλησιαστική",
            access=LandPlot.Access.OTHER,
            access_other="Αγροτικός δρόμος",
        ),
        **JSON,
    )
    plot = case.land_plots.get()
    assert plot.ownership_display == "Άλλη ιδιοκτησία: Εκκλησιαστική"
    assert plot.access_display == "Άλλο: Αγροτικός δρόμος"

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Άλλη ιδιοκτησία: Εκκλησιαστική" in detail
    assert "Άλλο: Αγροτικός δρόμος" in detail

    # Switching away from «Άλλο» drops the stale description.
    staff_client.post(
        reverse("cases:land_plot_edit", args=[case.pk, plot.pk]), _plot_values(), **JSON
    )
    plot.refresh_from_db()
    assert plot.ownership_other == ""
    assert plot.access_other == ""


@pytest.mark.django_db
def test_land_plot_files_belong_to_the_plot(community, staff_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    case = _make_case(community)
    plot = case.land_plots.create(parcel_number="123")
    edit_url = reverse("cases:land_plot_edit", args=[case.pk, plot.pk])
    data = _plot_values()
    data["new_files"] = [
        SimpleUploadedFile("sxedio.pdf", b"%PDF-1", content_type="application/pdf"),
        SimpleUploadedFile("photo.jpg", b"jpg", content_type="image/jpeg"),
        SimpleUploadedFile("topo.png", b"png", content_type="image/png"),
    ]
    payload = staff_client.post(edit_url, data, **JSON).json()
    assert payload["ok"] is True

    attachments = {a.filename: a for a in plot.attachments.all()}
    assert set(attachments) == {"sxedio.pdf", "photo.jpg", "topo.png"}
    assert attachments["sxedio.pdf"].section_ref == "3.1"
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="CREATE", case_id=case.pk, section_ref="3.1"
    ).count() == 3

    download_url = reverse(
        "cases:attachment_download", args=[case.pk, attachments["sxedio.pdf"].pk]
    )
    assert download_url in payload["grid_html"]
    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert download_url in detail
    response = staff_client.get(download_url)
    assert response.status_code == 200
    assert response.content == b"%PDF-1"
    assert "sxedio.pdf" in response["Content-Disposition"]

    other_case = _make_case(community, number="CASE-ABG-02")
    assert staff_client.get(
        reverse("cases:attachment_download", args=[other_case.pk, attachments["sxedio.pdf"].pk])
    ).status_code == 404

    data = _plot_values()
    data["remove_attachments"] = [str(attachments["photo.jpg"].pk)]
    staff_client.post(edit_url, data, **JSON)
    assert {a.filename for a in plot.attachments.all()} == {"sxedio.pdf", "topo.png"}
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="DELETE", case_id=case.pk
    ).exists()


@pytest.mark.django_db
def test_land_plot_delete_removes_plot_and_files(community, staff_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    case = _make_case(community)
    keep = case.land_plots.create(parcel_number="100")
    plot = case.land_plots.create(parcel_number="123")
    data = _plot_values()
    data["new_files"] = [SimpleUploadedFile("sxedio.pdf", b"%PDF-1")]
    staff_client.post(reverse("cases:land_plot_edit", args=[case.pk, plot.pk]), data, **JSON)

    delete_url = reverse("cases:land_plot_delete", args=[case.pk, plot.pk])
    assert staff_client.get(delete_url, **JSON).status_code == 404

    payload = staff_client.post(delete_url, **JSON).json()
    assert payload["ok"] is True
    assert "123" in payload["message"]
    assert list(case.land_plots.all()) == [keep]
    assert not Attachment.objects.filter(object_id=plot.pk, section_ref="3.1").exists()
    assert ActionHistory.objects.filter(
        entity_type="LandPlot", action="DELETE", case_id=case.pk, section_ref="3.1"
    ).exists()
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="DELETE", case_id=case.pk, section_ref="3.1"
    ).exists()


# --- 4.2 Υπηρεσίες κοινής ωφέλειας: grid με modal, τιμές από κατάλογο ---


def _service_type(name):
    return UtilityServiceType.objects.get(name=name)


def _service_values(service_type, **overrides):
    values = {"service_type": str(service_type.pk), "proximity": "50 μ.", "comments": ""}
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_utility_service_dropdown_is_seeded_in_order():
    assert list(UtilityServiceType.objects.values_list("name", flat=True)) == [
        "Τηλεπικοινωνίες",
        "ΑΗΚ",
        "Υδατοπρομήθεια",
        "Αποχέτευση",
        "Άλλο",
    ]


@pytest.mark.django_db
def test_section_4_shows_utility_services_as_sortable_grid(community, staff_client):
    case = _make_case(community)
    case.utility_services.create(service_type=_service_type("ΑΗΚ"), proximity="20 μ.")
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "4"])).content.decode()
    assert "data-utility-service-container" in html
    assert reverse("cases:utility_service_create", args=[case.pk]) in html
    assert 'id="utility-service-dialog"' in html
    assert "utility_services-TOTAL_FORMS" not in html
    for key in ("service", "proximity", "comments"):
        assert f'data-utility-service-sort="{key}"' in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "20 μ." in detail
    assert 'data-utility-service-sort="service"' in detail
    assert "data-utility-service-open" not in detail
    assert "data-utility-service-delete" not in detail


@pytest.mark.django_db
def test_utility_service_modal_adds_the_same_service_more_than_once(community, staff_client):
    case = _make_case(community)
    url = reverse("cases:utility_service_create", args=[case.pk])
    assert staff_client.get(url).status_code == 404

    form = staff_client.get(url, **JSON).json()
    assert form["ok"] is True
    assert "4.2 Νέα υπηρεσία" in form["html"]
    for name in ("Τηλεπικοινωνίες", "ΑΗΚ", "Υδατοπρομήθεια", "Αποχέτευση", "Άλλο"):
        assert name in form["html"]

    water = _service_type("Υδατοπρομήθεια")
    first = staff_client.post(url, _service_values(water, proximity="Δίπλα στο τεμάχιο 123"), **JSON)
    second = staff_client.post(url, _service_values(water, proximity="300 μ. από το 456"), **JSON)
    assert first.json()["ok"] is True
    payload = second.json()
    assert payload["ok"] is True
    assert "Υδατοπρομήθεια" in payload["message"]
    assert "300 μ. από το 456" in payload["grid_html"]
    assert list(case.utility_services.values_list("service_type__name", flat=True)) == [
        "Υδατοπρομήθεια",
        "Υδατοπρομήθεια",
    ]
    assert ActionHistory.objects.filter(
        entity_type="UtilityService", action="CREATE", case_id=case.pk, section_ref="4.2"
    ).count() == 2

    missing = staff_client.post(url, {**_service_values(water), "service_type": ""}, **JSON)
    assert missing.status_code == 400
    assert missing.json()["ok"] is False
    assert case.utility_services.count() == 2


@pytest.mark.django_db
def test_utility_service_modal_edits_and_deletes_rows(community, staff_client):
    case = _make_case(community)
    service = case.utility_services.create(service_type=_service_type("ΑΗΚ"), proximity="20 μ.")
    edit_url = reverse("cases:utility_service_edit", args=[case.pk, service.pk])

    payload = staff_client.post(
        edit_url,
        _service_values(_service_type("Αποχέτευση"), proximity="", comments="Σύνδεση με κεντρικό αγωγό"),
        **JSON,
    ).json()
    assert payload["ok"] is True
    service.refresh_from_db()
    assert service.service_type.name == "Αποχέτευση"
    assert service.comments == "Σύνδεση με κεντρικό αγωγό"
    assert ActionHistory.objects.filter(
        entity_type="UtilityService",
        action="UPDATE",
        case_id=case.pk,
        section_ref="4.2",
        field_name="service_type",
    ).exists()

    delete_url = reverse("cases:utility_service_delete", args=[case.pk, service.pk])
    assert staff_client.get(delete_url, **JSON).status_code == 404
    payload = staff_client.post(delete_url, **JSON).json()
    assert payload["ok"] is True
    assert "Αποχέτευση" in payload["message"]
    assert not case.utility_services.exists()
    assert ActionHistory.objects.filter(
        entity_type="UtilityService", action="DELETE", case_id=case.pk, section_ref="4.2"
    ).exists()


@pytest.mark.django_db
def test_utility_service_modal_is_scoped_to_its_case(community, staff_client):
    case = _make_case(community)
    other_case = _make_case(community, number="CASE-ABG-02")
    service = other_case.utility_services.create(service_type=_service_type("ΑΗΚ"))
    edit_url = reverse("cases:utility_service_edit", args=[case.pk, service.pk])
    assert staff_client.get(edit_url, **JSON).status_code == 404
    delete_url = reverse("cases:utility_service_delete", args=[case.pk, service.pk])
    assert staff_client.post(delete_url, **JSON).status_code == 404
    assert other_case.utility_services.count() == 1

    unallocated = _make_case(
        community, case_type=Case.CaseType.UNALLOCATED_PLOTS, number="CASE-ABG-03"
    )
    url = reverse("cases:utility_service_create", args=[unallocated.pk])
    assert staff_client.get(url, **JSON).status_code == 404


@pytest.mark.django_db
def test_inactive_service_is_kept_on_existing_rows_only(community, staff_client):
    case = _make_case(community)
    telecom = _service_type("Τηλεπικοινωνίες")
    service = case.utility_services.create(service_type=telecom)
    telecom.is_active = False
    telecom.save()

    new_form = staff_client.get(reverse("cases:utility_service_create", args=[case.pk]), **JSON).json()
    assert "Τηλεπικοινωνίες" not in new_form["html"]
    rejected = staff_client.post(
        reverse("cases:utility_service_create", args=[case.pk]), _service_values(telecom), **JSON
    )
    assert rejected.status_code == 400

    edit_url = reverse("cases:utility_service_edit", args=[case.pk, service.pk])
    assert "Τηλεπικοινωνίες" in staff_client.get(edit_url, **JSON).json()["html"]
    assert staff_client.post(edit_url, _service_values(telecom), **JSON).json()["ok"] is True


def _consultation_values(**overrides):
    values = {
        "department": Consultation.Department.TKX,
        "department_other": "",
        "topic": "Θέμα δοκιμής",
        "sent_date": "2026-02-01",
        "due_date": "2026-02-15",
        "response_date": "",
        "response_text": "",
        "comments": "",
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_section_5_shows_consultations_as_sortable_grid(community, staff_client):
    case = _make_case(community)
    case.consultations.create(
        stage=Consultation.Stage.SUITABILITY,
        department=Consultation.Department.AHK,
        topic="Αίτημα γνώμης",
    )
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "5"])).content.decode()
    assert "data-suitability-consultation-container" in html
    assert reverse("cases:suitability_consultation_create", args=[case.pk]) in html
    assert 'id="suitability-consultation-dialog"' in html
    assert "consultations-TOTAL_FORMS" not in html
    for key in ("department", "topic", "sent", "due", "response", "opinion", "status", "comments"):
        assert f'data-suitability-consultation-sort="{key}"' in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Αίτημα γνώμης" in detail
    assert "data-suitability-consultation-open" not in detail


@pytest.mark.django_db
def test_suitability_consultation_modal_crud_and_attachment(community, staff_client):
    case = _make_case(community)
    create_url = reverse("cases:suitability_consultation_create", args=[case.pk])
    assert staff_client.get(create_url).status_code == 404

    form = staff_client.get(create_url, **JSON).json()
    assert form["ok"] is True
    assert "Τ.Κ.Χ" in form["html"]
    assert "Τ.Α.Υ" in form["html"]

    payload = staff_client.post(create_url, _consultation_values(), **JSON).json()
    assert payload["ok"] is True
    consultation = case.consultations.get()
    assert consultation.department == Consultation.Department.TKX
    assert consultation.get_status_display() == "Εκκρεμεί"

    edit_url = reverse("cases:suitability_consultation_edit", args=[case.pk, consultation.pk])
    with_attachment = _consultation_values(
        department=Consultation.Department.OTHER,
        department_other="ΤΠΟ",
        response_date="2026-02-20",
        response_text="Θετική",
    )
    staff_client.post(
        edit_url,
        {**with_attachment, "new_files": SimpleUploadedFile("apantisi.pdf", b"pdf", "application/pdf")},
        **JSON,
    )
    consultation.refresh_from_db()
    assert consultation.department_display == "ΤΠΟ"
    assert consultation.get_status_display() == "Λήφθηκε"
    assert consultation.attachments.filter(section_ref="5").count() == 1

    delete_url = reverse("cases:suitability_consultation_delete", args=[case.pk, consultation.pk])
    staff_client.post(delete_url, **JSON)
    assert not case.consultations.exists()
    assert not Attachment.objects.filter(section_ref="5").exists()
    assert ActionHistory.objects.filter(
        entity_type="Consultation", action="DELETE", case_id=case.pk, section_ref="5"
    ).exists()
