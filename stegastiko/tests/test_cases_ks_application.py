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
    ApprovedDesignPlot,
    Case,
    CompletenessCheck,
    Consultation,
    Field,
    InfrastructureCheck,
    LandPlot,
    MinistryDecisionRound,
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
def test_unallocated_case_skips_sections_2_to_7_7(community):
    """§Α.3.3 An unallocated-plots case has no Αίτηση Α, so it goes straight to 7.9."""
    unallocated = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    assert unallocated.applicable_sections == ("1", "7-plots", "8")
    for skipped in ("2", "3", "4", "5", "6", "7"):
        assert skipped not in unallocated.applicable_sections


@pytest.mark.django_db
def test_unallocated_case_blocks_section_screen(community, staff_client):
    unallocated = _make_case(community, case_type=Case.CaseType.UNALLOCATED_PLOTS)
    blocked = staff_client.get(
        reverse("cases:section_edit", args=[unallocated.pk, "3"])
    )
    assert blocked.status_code == 404
    allowed = staff_client.get(
        reverse("cases:section_edit", args=[unallocated.pk, "7-plots"])
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


# --- Scenario 11: the 8.4 readiness check gates the announcement ---


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

    # 8.1 available plots are counted across both cases of the community.
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
    assert "7. Σχεδιασμός και υλοποίηση διαχωρισμού" in detail_html

    assert staff_client.get(reverse("cases:list")).status_code == 200
    assert staff_client.get(reverse("cases:create")).status_code == 200
    assert staff_client.get(reverse("cases:history", args=[case.pk])).status_code == 200
    assert (
        staff_client.get(reverse("cases:announcement_create", args=[case.pk])).status_code == 200
    )
    for section in section_screens_for(case):
        response = staff_client.get(reverse("cases:section_edit", args=[case.pk, section]))
        assert response.status_code == 200, f"Ενότητα {section} δεν ανοίγει"

    # Ενότητα 8 lives on the announcement screens, not the generic section screen.
    assert "8" in case.applicable_sections
    assert "8" not in section_screens_for(case)


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
    assert reverse("cases:section_edit", args=[case.pk, "7-plots"]) in html
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
    save_case_section_label("7-plots", "Οικόπεδα από ρυθμίσεις")

    main = _detail_main_html(staff_client, case)
    assert '<h2 class="card__title">1. Βασικά στοιχεία και προτεραιότητα</h2>' in main
    assert '<h2 class="card__title">2. Πληρότητα αίτησης από ρυθμίσεις</h2>' in main
    assert '<h2 class="card__title">7. Οικόπεδα από ρυθμίσεις</h2>' in main
    assert '<h2 class="card__title">8. Γνωστοποίηση έναρξης αιτήσεων</h2>' in main
    assert main.count('<h2 class="card__title">') == 9


@pytest.mark.django_db
def test_stored_section_7_titles_follow_the_7_7_to_7_9_renumbering():
    from importlib import import_module

    from django.apps import apps

    from core.models import SystemSetting

    migration = import_module("core.migrations.0016_renumber_case_labels_7_7_to_7_9")
    stored = {
        "caseSubsectionLabel.7.5": "Διαγωνισμός από ρυθμίσεις",
        "caseSubsectionLabel.7.7": "Αίτηση ΤΚΧ από ρυθμίσεις",
        "caseSubsectionLabel.7.7-parcels": "Χωράφια από ρυθμίσεις",
        "caseSubsectionLabel.7.8.2": "Έλεγχος από ρυθμίσεις",
        "caseSectionLabel.7-plots": "Οικόπεδα, αξία και τιμή (7.7–7.8)",
    }
    for key, value in stored.items():
        set_setting(key, value)

    migration.renumber_case_labels(apps, None)

    values = dict(SystemSetting.objects.values_list("key", "value"))
    assert values["caseSubsectionLabel.7.7"] == "Διαγωνισμός από ρυθμίσεις"
    assert values["caseSubsectionLabel.7.8"] == "Αίτηση ΤΚΧ από ρυθμίσεις"
    assert values["caseSubsectionLabel.7.8-parcels"] == "Χωράφια από ρυθμίσεις"
    assert values["caseSubsectionLabel.7.9.2"] == "Έλεγχος από ρυθμίσεις"
    assert values["caseSectionLabel.7-plots"] == "Οικόπεδα, αξία και τιμή (7.8–7.9)"
    for old_key in (
        "caseSubsectionLabel.7.5",
        "caseSubsectionLabel.7.7-parcels",
        "caseSubsectionLabel.7.8.2",
    ):
        assert old_key not in values


@pytest.mark.django_db
def test_stored_section_7_titles_move_tender_heading_to_7_5():
    from importlib import import_module

    from django.apps import apps

    from core.models import SystemSetting

    migration = import_module("core.migrations.0018_rename_subsection_labels_7_5_7_7")
    set_setting("caseSubsectionLabel.7.7", "Παλιός τίτλος διαγωνισμού")

    migration.rename_subsection_labels_7_5_7_7(apps, None)

    values = dict(SystemSetting.objects.values_list("key", "value"))
    assert values["caseSubsectionLabel.7.5"] == "Προκυρηξη και κατακυρωσης συμβασης"
    assert values["caseSubsectionLabel.7.7"] == "Τρέχον στάδιο / πορεία εργασιών και σχόλια"


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
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert "Ημερομηνία ανάθεσης μελέτης" in html
    assert "7.1 Ημερομηνία ανάθεσης μελέτης" not in html
    assert "Survey assignment date" not in html
    assert "Works progress stage" not in html


@pytest.mark.django_db
def test_publication_rows_use_greek_labels(community, staff_client):
    """8.2 The publication formset is a separate model and needs labels too."""
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
    assert "8.2 Τρόπος δημοσίευσης" not in html
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

    from django.template.loader import render_to_string

    report_html = render_to_string("cases/pdf/section_6_report.html", context)
    assert context["heading_62"] in report_html
    assert "4.1 Τεχνική αξιολόγηση ανά τεμάχιο" not in report_html
    assert "Συνοπτικός πίνακας τεμαχίων" not in report_html
    assert "Εκτιμώμενος αριθμός οικοπέδων" in report_html

    # Ενότητα 6 shows the 4.1-style grid read-only under heading 6.2.
    section6_html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "6"])).content.decode()
    assert "Εκτιμώμενος αριθμός οικοπέδων" in section6_html
    assert "data-land-plot-open" not in section6_html

    pdf_url = reverse("cases:section_6_report_pdf", args=[case.pk])
    for url_name, section in (("cases:section_edit", "6"), ("cases:detail", None)):
        args = [case.pk, section] if section else [case.pk]
        html = staff_client.get(reverse(url_name, args=args)).content.decode()
        assert "section-6-report-pdf-dialog" in html
        assert pdf_url in html
        assert 'data-dialog-open="section-6-report-pdf-dialog"' in html

    from cases.section6_report_pdf import parse_section6_report_includes

    partial = section6_report_context(
        case, includes=parse_section6_report_includes({"include": ["6.1"]})
    )
    partial_html = render_to_string("cases/pdf/section_6_report.html", partial)
    assert context["heading_61"] in partial_html
    assert context["heading_63"] not in partial_html

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


def _section7_post(**overrides):
    return dict(overrides)


@pytest.mark.django_db
def test_section_7_screen_groups_fields_under_7_1_to_7_3(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    headings = [
        "7.1 Ανάθεση μελέτης",
        "7.2 Σχεδιασμός διαχωρισμού",
        "7.3 Στοιχεία αίτησης για έγκριση σχεδιασμού",
    ]
    positions = [html.index(heading) for heading in headings]
    assert positions == sorted(positions)
    design_block = html[positions[1]:positions[2]]
    for label in (
        "Κατάσταση σχεδιασμού",
        "Ημερομηνία ολοκλήρωσης σχεδιασμού",
        "Αριθμός οικοπέδων",
        "Επισυναπτόμενα έγγραφα",
        'name="new_division_design_files"',
        'name="division_design_comments"',
    ):
        assert label in design_block
    assert "Αριθμός οικοπέδων στον ολοκληρωμένο σχεδιασμό" not in html
    tpo_block = html[positions[2]:]
    for label in (
        "Ημερομηνία υποβολής αίτησης στο ΤΠΟ",
        "Αριθμός αίτησης ΤΠΟ",
        "Απάντηση Διευθυντή ΤΠΟ",
        "Ημερομηνία απάντησης ΤΠΟ",
        'name="new_tpo_application_files"',
        'name="tpo_comments"',
    ):
        assert label in tpo_block
    assert 'enctype="multipart/form-data"' in html


@pytest.mark.django_db
def test_section_7_keeps_separate_files_for_7_2_and_7_3(community, staff_client):
    case = _make_case(community)
    url = reverse("cases:section_edit", args=[case.pk, "7"])
    data = _section7_post(
        division_design_plots_count="12",
        tpo_application_number="ΤΠΟ/123",
        new_division_design_files=[
            SimpleUploadedFile("sxediasmos.pdf", b"%PDF-design", content_type="application/pdf"),
        ],
        new_tpo_application_files=[
            SimpleUploadedFile("apantisi_tpo.pdf", b"%PDF-tpo", content_type="application/pdf"),
        ],
    )
    assert staff_client.post(url, data).status_code == 302

    case.refresh_from_db()
    assert case.division_design_plots_count == 12
    assert case.tpo_application_number == "ΤΠΟ/123"
    assert [a.filename for a in case.division_design_attachments()] == ["sxediasmos.pdf"]
    assert [a.filename for a in case.tpo_application_attachments()] == ["apantisi_tpo.pdf"]
    for section_ref in ("7.2", "7.3"):
        assert ActionHistory.objects.filter(
            entity_type="Attachment", action="CREATE", case_id=case.pk, section_ref=section_ref
        ).exists()

    design_file = case.division_design_attachments().get()
    download_url = reverse("cases:attachment_download", args=[case.pk, design_file.pk])
    assert staff_client.get(download_url).content == b"%PDF-design"
    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert download_url in detail
    assert "apantisi_tpo.pdf" in detail

    edit_html = staff_client.get(url).content.decode()
    assert 'name="remove_division_design_attachments"' in edit_html
    staff_client.post(
        url,
        _section7_post(
            division_design_plots_count="12",
            remove_division_design_attachments=[str(design_file.pk)],
        ),
    )
    assert not case.division_design_attachments().exists()
    assert case.tpo_application_attachments().count() == 1
    assert ActionHistory.objects.filter(
        entity_type="Attachment", action="DELETE", case_id=case.pk, section_ref="7.2"
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
    assert "data-consultation-container" in html
    assert reverse("cases:suitability_consultation_create", args=[case.pk]) in html
    assert 'id="consultation-dialog"' in html
    assert "consultations-TOTAL_FORMS" not in html
    for key in ("department", "topic", "sent", "due", "response", "opinion", "status", "comments"):
        assert f'data-consultation-sort="{key}"' in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Αίτημα γνώμης" in detail
    assert "data-consultation-open" not in detail


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


@pytest.mark.django_db
def test_section_7_4_has_consultations_grid_then_construction_plans_fields(community, staff_client):
    case = _make_case(community)
    case.consultations.create(
        stage=Consultation.Stage.SUITABILITY, department=Consultation.Department.TKX, topic="Θέμα 5"
    )
    case.consultations.create(
        stage=Consultation.Stage.DIVISION, department=Consultation.Department.AHK, topic="Θέμα 7.4"
    )
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    positions = [
        html.index("data-approved-design-plot-table"),
        html.index("7.4 Κατασκευαστικά Σχέδια και Διαβουλεύσεις"),
        html.index("data-consultation-table"),
        html.index('name="construction_plans_stage"'),
        html.index('name="land_expropriation_required"'),
        html.index("7.5 Προκυρηξη και κατακυρωσης συμβασης"),
    ]
    assert positions == sorted(positions)
    assert "Στάδιο κατασκευαστικών σχεδίων" in html
    assert "Απαιτείται απαλλοτρίωση γης" in html
    assert reverse("cases:division_consultation_create", args=[case.pk]) in html
    assert reverse("cases:suitability_consultation_create", args=[case.pk]) not in html
    assert 'id="consultation-dialog"' in html
    assert "consultations-TOTAL_FORMS" not in html
    for key in ("department", "topic", "sent", "due", "response", "opinion", "status", "comments"):
        assert f'data-consultation-sort="{key}"' in html
    assert "Θέμα 7.4" in html
    assert "Θέμα 5" not in html


@pytest.mark.django_db
def test_section_7_4_construction_plans_fields_are_saved_and_shown_in_folder(community, staff_client):
    case = _make_case(community)
    url = reverse("cases:section_edit", args=[case.pk, "7"])
    response = staff_client.post(
        url,
        _section7_post(
            construction_plans_stage="Υποβλήθηκαν στο ΤΔΕ για έγκριση",
            land_expropriation_required=YesNo.YES,
        ),
    )
    assert response.status_code == 302
    case.refresh_from_db()
    assert case.construction_plans_stage == "Υποβλήθηκαν στο ΤΔΕ για έγκριση"
    assert case.land_expropriation_required == YesNo.YES

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    block = detail[
        detail.index("7.4 Κατασκευαστικά Σχέδια και Διαβουλεύσεις"):detail.index("7.5 Προκυρηξη και κατακυρωσης συμβασης")
    ]
    assert "Διαβουλεύσεις Κατασκευαστικών Σχεδίων" in block
    assert "data-consultation-table" in block
    assert "Στάδιο κατασκευαστικών σχεδίων" in block
    assert "Υποβλήθηκαν στο ΤΔΕ για έγκριση" in block
    assert "Απαιτείται απαλλοτρίωση γης" in block
    assert "ΝΑΙ" in block


@pytest.mark.django_db
def test_division_consultation_modal_crud_keeps_rows_and_files_apart_from_section_5(
    community, staff_client
):
    case = _make_case(community)
    suitability = case.consultations.create(
        stage=Consultation.Stage.SUITABILITY, department=Consultation.Department.TKX, topic="Θέμα 5"
    )
    create_url = reverse("cases:division_consultation_create", args=[case.pk])
    assert staff_client.get(create_url).status_code == 404
    form = staff_client.get(create_url, **JSON).json()
    assert create_url in form["html"]

    payload = staff_client.post(
        create_url, _consultation_values(topic="Κατασκευαστικά σχέδια ΑΗΚ"), **JSON
    ).json()
    assert payload["ok"] is True
    assert "Κατασκευαστικά σχέδια ΑΗΚ" in payload["grid_html"]
    assert "Θέμα 5" not in payload["grid_html"]
    consultation = case.consultations.get(stage=Consultation.Stage.DIVISION)
    assert ActionHistory.objects.filter(
        entity_type="Consultation", action="CREATE", case_id=case.pk, section_ref="7.4"
    ).exists()

    edit_url = reverse("cases:division_consultation_edit", args=[case.pk, consultation.pk])
    staff_client.post(
        edit_url,
        {
            **_consultation_values(response_date="2026-02-20", response_text="Θετική"),
            "new_files": SimpleUploadedFile("sxedia.pdf", b"pdf-7.4", "application/pdf"),
        },
        **JSON,
    )
    consultation.refresh_from_db()
    assert consultation.get_status_display() == "Λήφθηκε"
    attachment = consultation.attachments.get()
    assert attachment.section_ref == "7.4"
    download_url = reverse("cases:attachment_download", args=[case.pk, attachment.pk])
    assert staff_client.get(download_url).content == b"pdf-7.4"

    section_5 = staff_client.get(reverse("cases:section_edit", args=[case.pk, "5"])).content.decode()
    assert "Κατασκευαστικά σχέδια ΑΗΚ" not in section_5
    assert staff_client.get(
        reverse("cases:division_consultation_edit", args=[case.pk, suitability.pk]), **JSON
    ).status_code == 404
    assert staff_client.get(
        reverse("cases:suitability_consultation_edit", args=[case.pk, consultation.pk]), **JSON
    ).status_code == 404

    delete_url = reverse("cases:division_consultation_delete", args=[case.pk, consultation.pk])
    assert staff_client.post(delete_url, **JSON).json()["ok"] is True
    assert list(case.consultations.all()) == [suitability]
    assert not Attachment.objects.filter(section_ref="7.4").exists()
    assert ActionHistory.objects.filter(
        entity_type="Consultation", action="DELETE", case_id=case.pk, section_ref="7.4"
    ).exists()


@pytest.mark.django_db
def test_suitability_and_construction_plans_consultations_coexist(community, staff_client):
    case = _make_case(community)
    staff_client.post(
        reverse("cases:suitability_consultation_create", args=[case.pk]),
        _consultation_values(topic="Καταλληλότητα τεμαχίου"),
        **JSON,
    )
    staff_client.post(
        reverse("cases:division_consultation_create", args=[case.pk]),
        _consultation_values(topic="Κατασκευαστικά σχέδια οδών"),
        **JSON,
    )
    assert case.consultations.filter(stage=Consultation.Stage.SUITABILITY).count() == 1
    assert case.consultations.filter(stage=Consultation.Stage.DIVISION).count() == 1

    section_5 = staff_client.get(reverse("cases:section_edit", args=[case.pk, "5"])).content.decode()
    section_7 = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert "Καταλληλότητα τεμαχίου" in section_5
    assert "Κατασκευαστικά σχέδια οδών" not in section_5
    assert "Κατασκευαστικά σχέδια οδών" in section_7
    assert "Καταλληλότητα τεμαχίου" not in section_7

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Καταλληλότητα τεμαχίου" in detail
    assert "Κατασκευαστικά σχέδια οδών" in detail


@pytest.mark.django_db
def test_division_consultation_needs_section_7_edit_access(community, client, make_user):
    case = _make_case(community)
    consultation = case.consultations.create(
        stage=Consultation.Stage.DIVISION, department=Consultation.Department.AHK, topic="Θέμα 7.4"
    )
    client.force_login(make_user("reader", "Μόνο ανάγνωση"))

    html = client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert "Θέμα 7.4" in html
    assert "data-consultation-open" not in html
    assert "data-consultation-delete" not in html
    create_url = reverse("cases:division_consultation_create", args=[case.pk])
    assert client.get(create_url, **JSON).status_code == 403
    assert client.post(create_url, _consultation_values(), **JSON).status_code == 403
    delete_url = reverse("cases:division_consultation_delete", args=[case.pk, consultation.pk])
    assert client.post(delete_url, **JSON).status_code == 403
    assert case.consultations.count() == 1


def _ministry_round_values(**overrides):
    values = {
        "letter_sent_date": "2026-04-10",
        "recommendation": MinistryDecisionRound.Recommendation.POSITIVE,
        "recommendation_other": "",
        "ministry_response_date": "",
        "ministry_decision": "",
        "ministry_decision_other": "",
        "comments": "",
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_section_6_7_ministry_decision_round_grid(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "6"])).content.decode()
    assert "6.7 Λήψη απόφασης από υπουργό" in html
    assert "data-ministry-decision-round-container" in html
    assert reverse("cases:ministry_decision_round_create", args=[case.pk]) in html

    create_url = reverse("cases:ministry_decision_round_create", args=[case.pk])
    payload = staff_client.post(
        create_url,
        _ministry_round_values(
            ministry_decision=MinistryDecisionRound.MinistryDecision.OTHER,
            ministry_decision_other="Αναμονή",
            ministry_response_date="2026-05-20",
        ),
        **JSON,
    ).json()
    assert payload["ok"] is True
    row = case.ministry_decision_rounds.get()
    assert row.ministry_decision_display == "Άλλο: Αναμονή"

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Αναμονή" in detail
    assert "data-ministry-decision-round-table" in detail
    assert "Επισυναπτόμενο έγγραφο σύστασης" in detail
    assert "Επισυναπτόμενο έγγραφο απάντησης" in detail
    assert staff_client.get(reverse("cases:section_edit", args=[case.pk, "8"])).status_code == 404

    from django.core.files.uploadedfile import SimpleUploadedFile

    edit_url = reverse("cases:ministry_decision_round_edit", args=[case.pk, row.pk])
    payload = staff_client.post(
        edit_url,
        {
            **_ministry_round_values(
                ministry_decision=MinistryDecisionRound.MinistryDecision.OTHER,
                ministry_decision_other="Αναμονή",
                ministry_response_date="2026-05-20",
            ),
            "new_recommendation_files": SimpleUploadedFile(
                "systasi.pdf", b"%PDF-rec", content_type="application/pdf"
            ),
            "new_response_files": SimpleUploadedFile(
                "apantisi.pdf", b"%PDF-res", content_type="application/pdf"
            ),
        },
        **JSON,
    ).json()
    assert payload["ok"] is True
    row.refresh_from_db()
    assert row.recommendation_attachments().get().filename == "systasi.pdf"
    assert row.response_attachments().get().filename == "apantisi.pdf"


def _approved_design_plot_values(**overrides):
    values = {
        "plot_type": ApprovedDesignPlot.PlotType.DIVISION_PLOT,
        "plot_type_other": "",
        "design_number": "1",
        "tkx_number": "",
        "title_deed_number": "",
        "parcel_number": "123",
        "sheet_plan": "30/12",
        "numbering_status": ApprovedDesignPlot.NumberingStatus.DESIGN,
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_section_7_3_approved_design_plots_grid_sits_after_7_3_comments(community, staff_client):
    case = _make_case(community)
    case.approved_design_plots.create(
        plot_type=ApprovedDesignPlot.PlotType.GREEN_SPACE,
        design_number="Π-1",
        final_area_sqm=Decimal("512.75"),
    )
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    positions = [
        html.index('name="tpo_comments"'),
        html.index("Στοιχεία Εγκεκριμένου Σχεδιασμού Οικοπέδων"),
        html.index("data-approved-design-plot-table"),
        html.index("7.4 Κατασκευαστικά Σχέδια και Διαβουλεύσεις"),
    ]
    assert positions == sorted(positions)
    assert reverse("cases:approved_design_plot_create", args=[case.pk]) in html
    assert 'id="approved-design-plot-dialog"' in html
    for key in ("type", "number", "tkx", "title", "parcel", "sheet", "area", "status"):
        assert f'data-approved-design-plot-sort="{key}"' in html
    assert "Τελικό εμβαδόν (τ.μ.)" in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Στοιχεία Εγκεκριμένου Σχεδιασμού Οικοπέδων" in detail
    assert "Χώρος πρασίνου" in detail
    assert "Π-1" in detail
    assert "Τελικό εμβαδόν (τ.μ.)" in detail
    assert "data-approved-design-plot-open" not in detail
    assert "data-approved-design-plot-delete" not in detail


@pytest.mark.django_db
def test_section_7_5_and_7_6_close_the_section_7_screen(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    heading_7_5 = "7.5 Προκυρηξη και κατακυρωσης συμβασης"
    heading_7_6 = "7.6 Παρακολουθηση κατασκευαστικων εργασιων"
    assert html.index("7.4 Κατασκευαστικά Σχέδια και Διαβουλεύσεις") < html.index(heading_7_5)
    assert html.index(heading_7_5) < html.index('name="tender_announcement_date"')
    assert html.index('name="tender_announcement_date"') < html.index(heading_7_6)
    assert html.index(heading_7_6) < html.index("data-infrastructure-check-table")
    assert html.index("data-infrastructure-check-table") < html.index('name="section8_comments"')
    assert html.index('name="section8_comments"') < html.rindex('class="form-actions form-span-all"')
    for removed in (
        "7.7 Έλεγχος υποδομών",
        "infrastructure_checks-TOTAL_FORMS",
        'name="works_progress_stage"',
        'name="works_progress_updated_on"',
        'name="works_progress_comments"',
        "Σχόλια / Παρατηρήσεις Ενότητας 8",
    ):
        assert removed not in html
    assert "Σχόλια / Παρατηρήσεις Ενότητας 7" in html

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert detail.index("7.4 Κατασκευαστικά Σχέδια και Διαβουλεύσεις") < detail.index(heading_7_5)
    assert detail.index(heading_7_5) < detail.index(heading_7_6)
    assert detail.index(heading_7_6) < detail.index("data-infrastructure-check-table")
    assert detail.index("data-infrastructure-check-table") < detail.index("7.8 Αίτηση στο ΤΚΧ")
    assert "7.7 Έλεγχος υποδομών" not in detail
    assert 'name="contract_duration_unit"' not in html
    tender_block = detail[detail.index(heading_7_5):detail.index(heading_7_6)]
    assert "Διάρκεια σύμβασης (μήνες)" in tender_block
    assert "Διάρκεια σύμβασης (μονάδα" not in tender_block
    for heading in (
        "7.8 Χωράφια",
        "7.9.1 Παραπομπές προς ΤΚΧ",
        "7.8 / 7.9 Πίνακας αντιστοίχισης οικοπέδων",
        "7.9.2 Έλεγχος ολοκλήρωσης (αυτόματο)",
    ):
        assert heading in detail


@pytest.mark.django_db
def test_approved_design_plot_modal_adds_rows_and_requires_other_type(community, staff_client):
    case = _make_case(community)
    url = reverse("cases:approved_design_plot_create", args=[case.pk])
    assert staff_client.get(url).status_code == 404

    form = staff_client.get(url, **JSON).json()
    assert form["ok"] is True
    for label in (
        "Υπό διαχωρισμό οικόπεδο",
        "Χώρος πρασίνου",
        "Υποσταθμός ΑΗΚ",
        "Χώρος κοινοτικού εξοπλισμού",
        "Άλλο",
        "Αρίθμηση σχεδιασμού",
        "Αρίθμηση ΤΚΧ",
        "Αρίθμηση βάσει τίτλου ιδιοκτησίας",
    ):
        assert label in form["html"]

    missing_type = staff_client.post(url, _approved_design_plot_values(plot_type=""), **JSON)
    assert missing_type.status_code == 400
    missing_other = staff_client.post(
        url, _approved_design_plot_values(plot_type=ApprovedDesignPlot.PlotType.OTHER), **JSON
    )
    assert missing_other.status_code == 400
    assert "Συμπληρώστε τον τύπο" in missing_other.json()["html"]
    assert not case.approved_design_plots.exists()

    staff_client.post(url, _approved_design_plot_values(), **JSON)
    payload = staff_client.post(
        url,
        _approved_design_plot_values(
            plot_type=ApprovedDesignPlot.PlotType.OTHER,
            plot_type_other="Χώρος στάθμευσης",
            design_number="Σ-1",
        ),
        **JSON,
    ).json()
    assert payload["ok"] is True
    assert "Άλλο: Χώρος στάθμευσης" in payload["grid_html"]
    rows = list(case.approved_design_plots.all())
    assert [row.plot_type_display for row in rows] == [
        "Υπό διαχωρισμό οικόπεδο",
        "Άλλο: Χώρος στάθμευσης",
    ]
    assert rows[0].numbering_status == ApprovedDesignPlot.NumberingStatus.DESIGN
    assert ActionHistory.objects.filter(
        entity_type="ApprovedDesignPlot", action="CREATE", case_id=case.pk, section_ref="7.3"
    ).count() == 2


@pytest.mark.django_db
def test_approved_design_plot_modal_edits_and_deletes_rows(community, staff_client):
    case = _make_case(community)
    plot = case.approved_design_plots.create(
        plot_type=ApprovedDesignPlot.PlotType.OTHER, plot_type_other="Πλατεία", design_number="1"
    )
    edit_url = reverse("cases:approved_design_plot_edit", args=[case.pk, plot.pk])
    payload = staff_client.post(
        edit_url,
        _approved_design_plot_values(
            plot_type_other="Πλατεία",
            tkx_number="301",
            title_deed_number="0/1234",
            final_area_sqm="450.50",
            numbering_status=ApprovedDesignPlot.NumberingStatus.TITLE_DEED,
        ),
        **JSON,
    ).json()
    assert payload["ok"] is True
    plot.refresh_from_db()
    assert plot.plot_type == ApprovedDesignPlot.PlotType.DIVISION_PLOT
    assert plot.plot_type_other == ""
    assert plot.tkx_number == "301"
    assert plot.final_area_sqm == Decimal("450.50")
    assert plot.get_numbering_status_display() == "Αρίθμηση βάσει τίτλου ιδιοκτησίας"
    for field_name in ("numbering_status", "final_area_sqm"):
        assert ActionHistory.objects.filter(
            entity_type="ApprovedDesignPlot",
            action="UPDATE",
            case_id=case.pk,
            section_ref="7.3",
            field_name=field_name,
        ).exists()

    delete_url = reverse("cases:approved_design_plot_delete", args=[case.pk, plot.pk])
    assert staff_client.get(delete_url, **JSON).status_code == 404
    payload = staff_client.post(delete_url, **JSON).json()
    assert payload["ok"] is True
    assert not case.approved_design_plots.exists()
    assert ActionHistory.objects.filter(
        entity_type="ApprovedDesignPlot", action="DELETE", case_id=case.pk, section_ref="7.3"
    ).exists()


@pytest.mark.django_db
def test_approved_design_plot_modal_is_scoped_to_its_case(community, staff_client):
    case = _make_case(community)
    other_case = _make_case(community, number="CASE-ABG-02")
    plot = other_case.approved_design_plots.create(
        plot_type=ApprovedDesignPlot.PlotType.GREEN_SPACE
    )
    edit_url = reverse("cases:approved_design_plot_edit", args=[case.pk, plot.pk])
    assert staff_client.get(edit_url, **JSON).status_code == 404
    delete_url = reverse("cases:approved_design_plot_delete", args=[case.pk, plot.pk])
    assert staff_client.post(delete_url, **JSON).status_code == 404
    assert other_case.approved_design_plots.count() == 1

    unallocated = _make_case(
        community, case_type=Case.CaseType.UNALLOCATED_PLOTS, number="CASE-ABG-03"
    )
    url = reverse("cases:approved_design_plot_create", args=[unallocated.pk])
    assert staff_client.get(url, **JSON).status_code == 404


@pytest.mark.django_db
def test_approved_design_plot_needs_section_7_edit_access(community, client, make_user):
    case = _make_case(community)
    plot = case.approved_design_plots.create(plot_type=ApprovedDesignPlot.PlotType.GREEN_SPACE)
    client.force_login(make_user("reader", "Μόνο ανάγνωση"))

    html = client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert "Χώρος πρασίνου" in html
    assert "data-approved-design-plot-open" not in html
    create_url = reverse("cases:approved_design_plot_create", args=[case.pk])
    assert client.get(create_url, **JSON).status_code == 403
    assert client.post(create_url, _approved_design_plot_values(), **JSON).status_code == 403
    delete_url = reverse("cases:approved_design_plot_delete", args=[case.pk, plot.pk])
    assert client.post(delete_url, **JSON).status_code == 403
    assert case.approved_design_plots.count() == 1
    bulk_url = reverse("cases:approved_design_plot_bulk_create", args=[case.pk])
    assert client.get(bulk_url, **JSON).status_code == 403
    assert client.post(
        bulk_url,
        {"plot_type": ApprovedDesignPlot.PlotType.GREEN_SPACE, "count": "2", "numbering_mode": "serial"},
        **JSON,
    ).status_code == 403
    assert case.approved_design_plots.count() == 1


@pytest.mark.django_db
def test_approved_design_plot_bulk_add_numbers_rows_serially(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    bulk_url = reverse("cases:approved_design_plot_bulk_create", args=[case.pk])
    assert "Μαζική προσθήκη" in html
    assert bulk_url in html
    assert staff_client.get(bulk_url).status_code == 404

    form = staff_client.get(bulk_url, **JSON).json()
    assert form["ok"] is True
    for label in ("Τύπος", "Αριθμός εγγραφών", "Σειριακή", "Χειροκίνητη", "Υπό διαχωρισμό οικόπεδο"):
        assert label in form["html"]
    for absent in ('name="tkx_number"', 'name="parcel_number"', 'name="numbering_status"'):
        assert absent not in form["html"]

    payload = staff_client.post(
        bulk_url,
        {
            "plot_type": ApprovedDesignPlot.PlotType.DIVISION_PLOT,
            "count": "3",
            "numbering_mode": "serial",
            "manual_numbers": ["ignored"],
        },
        **JSON,
    ).json()
    assert payload["ok"] is True
    assert "Προστέθηκαν 3 εγγραφές" in payload["message"]
    rows = list(case.approved_design_plots.all())
    assert [row.design_number for row in rows] == ["1", "2", "3"]
    assert {row.plot_type for row in rows} == {ApprovedDesignPlot.PlotType.DIVISION_PLOT}
    assert {row.numbering_status for row in rows} == {ApprovedDesignPlot.NumberingStatus.DESIGN}
    assert all(row.tkx_number == "" and row.final_area_sqm is None for row in rows)
    assert ActionHistory.objects.filter(
        entity_type="ApprovedDesignPlot", action="CREATE", case_id=case.pk, section_ref="7.3"
    ).count() == 3


@pytest.mark.django_db
def test_approved_design_plot_bulk_add_uses_manual_numbers(community, staff_client):
    case = _make_case(community)
    bulk_url = reverse("cases:approved_design_plot_bulk_create", args=[case.pk])
    values = {
        "plot_type": ApprovedDesignPlot.PlotType.OTHER,
        "plot_type_other": "Χώρος στάθμευσης",
        "count": "2",
        "numbering_mode": "manual",
        "manual_numbers": ["Σ-1", "Σ-2"],
    }
    payload = staff_client.post(bulk_url, values, **JSON).json()
    assert payload["ok"] is True
    assert "Άλλο: Χώρος στάθμευσης" in payload["grid_html"]
    rows = list(case.approved_design_plots.all())
    assert [row.design_number for row in rows] == ["Σ-1", "Σ-2"]
    assert {row.plot_type_other for row in rows} == {"Χώρος στάθμευσης"}


@pytest.mark.django_db
def test_approved_design_plot_bulk_add_rejects_invalid_input(community, staff_client):
    case = _make_case(community)
    bulk_url = reverse("cases:approved_design_plot_bulk_create", args=[case.pk])
    base = {
        "plot_type": ApprovedDesignPlot.PlotType.GREEN_SPACE,
        "count": "3",
        "numbering_mode": "manual",
        "manual_numbers": ["Π-1", "Π-2", "Π-3"],
    }
    cases = [
        ({"plot_type": ""}, None),
        ({"plot_type": ApprovedDesignPlot.PlotType.OTHER}, "Συμπληρώστε τον τύπο"),
        ({"count": "0"}, None),
        ({"count": "501"}, None),
        ({"numbering_mode": ""}, None),
        ({"manual_numbers": ["Π-1", "", "Π-3"]}, "Συμπληρώστε την αρίθμηση σε όλες τις γραμμές"),
        ({"manual_numbers": ["Π-1", "Π-2"]}, "Συμπληρώστε την αρίθμηση σε όλες τις γραμμές"),
        ({"manual_numbers": ["Π-1", "Π-1", "Π-3"]}, "δεν μπορεί να επαναλαμβάνεται"),
        ({"manual_numbers": ["Π-1", "Π-2", "x" * 65]}, "δεν μπορεί να υπερβαίνει"),
    ]
    for overrides, message in cases:
        response = staff_client.post(bulk_url, {**base, **overrides}, **JSON)
        assert response.status_code == 400, overrides
        html = response.json()["html"]
        if message:
            assert message in html
    duplicate = staff_client.post(
        bulk_url, {**base, "manual_numbers": ["Π-1", "Π-1", "Π-3"]}, **JSON
    ).json()["html"]
    assert duplicate.count('name="manual_numbers"') == 3
    assert 'value="Π-3"' in duplicate
    assert not case.approved_design_plots.exists()


INFRASTRUCTURE_CHECK_LABELS = (
    "Στάδιο",
    "Ημερομηνία ελέγχου",
    "Ρείθρα",
    "Κράσπεδα",
    "Οδόστρωμα με ασφαλτικό σκυρόδεμα",
    "Επιχωμάτωση πεζοδρομίων",
    "Υδατοπρομήθεια",
    "Τηλεπικοινωνίες",
    "Παροχή ηλεκτρικού ρεύματος",
    "Οδικός φωτισμός",
    "Σχόλια",
)


def _infrastructure_check_values(**overrides):
    values = {
        "stage": "Ολοκλήρωση υποδομών οδοποιίας",
        "check_date": "2027-05-15",
        "comments": "",
        **{name: "False" for name in InfrastructureCheck.WORK_FIELDS},
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_section_7_6_checks_grid_adds_edits_and_deletes_rows(community, staff_client):
    case = _make_case(community)
    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert 'id="infrastructure-check-dialog"' in html
    assert reverse("cases:infrastructure_check_create", args=[case.pk]) in html
    grid = html[html.index("data-infrastructure-check-table"):]
    for label in INFRASTRUCTURE_CHECK_LABELS:
        assert label in grid

    url = reverse("cases:infrastructure_check_create", args=[case.pk])
    assert staff_client.get(url).status_code == 404
    form = staff_client.get(url, **JSON).json()
    assert form["ok"] is True
    for label in INFRASTRUCTURE_CHECK_LABELS:
        assert label in form["html"]
    assert form["html"].count(">ΝΑΙ</option>") == len(InfrastructureCheck.WORK_FIELDS)
    assert form["html"].count(">ΟΧΙ</option>") == len(InfrastructureCheck.WORK_FIELDS)

    missing_date = staff_client.post(url, _infrastructure_check_values(check_date=""), **JSON)
    assert missing_date.status_code == 400
    assert not case.infrastructure_checks.exists()

    payload = staff_client.post(
        url,
        _infrastructure_check_values(
            curbs_ready="True", water_ready="True", comments="Εκκρεμεί ο φωτισμός."
        ),
        **JSON,
    ).json()
    assert payload["ok"] is True
    assert "Ολοκλήρωση υποδομών οδοποιίας" in payload["grid_html"]
    assert "Εκκρεμεί ο φωτισμός." in payload["grid_html"]
    check = case.infrastructure_checks.get()
    assert check.stage == "Ολοκλήρωση υποδομών οδοποιίας"
    assert check.check_date == date(2027, 5, 15)
    assert check.curbs_ready and check.water_ready
    assert not (check.pavements_ready or check.asphalt_ready or check.street_light_ready)
    assert ActionHistory.objects.filter(
        entity_type="InfrastructureCheck", action="CREATE", case_id=case.pk, section_ref="7.6"
    ).exists()

    edit_url = reverse("cases:infrastructure_check_edit", args=[case.pk, check.pk])
    assert 'value="Ολοκλήρωση υποδομών οδοποιίας"' in staff_client.get(edit_url, **JSON).json()["html"]
    staff_client.post(
        edit_url, _infrastructure_check_values(stage="Ασφαλτόστρωση", asphalt_ready="True"), **JSON
    )
    check.refresh_from_db()
    assert check.stage == "Ασφαλτόστρωση"
    assert check.asphalt_ready and not check.curbs_ready
    assert ActionHistory.objects.filter(
        entity_type="InfrastructureCheck",
        action="UPDATE",
        case_id=case.pk,
        section_ref="7.6",
        field_name="stage",
    ).exists()

    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Ασφαλτόστρωση" in detail
    assert "data-infrastructure-check-open" not in detail
    assert "data-infrastructure-check-delete" not in detail

    delete_url = reverse("cases:infrastructure_check_delete", args=[case.pk, check.pk])
    assert staff_client.get(delete_url, **JSON).status_code == 404
    payload = staff_client.post(delete_url, **JSON).json()
    assert payload["ok"] is True
    assert not case.infrastructure_checks.exists()
    assert ActionHistory.objects.filter(
        entity_type="InfrastructureCheck", action="DELETE", case_id=case.pk, section_ref="7.6"
    ).exists()


@pytest.mark.django_db
def test_section_7_6_checks_need_edit_access_and_stay_on_their_case(
    community, client, staff_client, make_user
):
    case = _make_case(community)
    other_case = _make_case(community, number="CASE-ABG-02")
    foreign = InfrastructureCheck.objects.create(case=other_case, check_date=date(2027, 1, 1))
    edit_url = reverse("cases:infrastructure_check_edit", args=[case.pk, foreign.pk])
    assert staff_client.get(edit_url, **JSON).status_code == 404
    delete_url = reverse("cases:infrastructure_check_delete", args=[case.pk, foreign.pk])
    assert staff_client.post(delete_url, **JSON).status_code == 404
    assert other_case.infrastructure_checks.count() == 1

    InfrastructureCheck.objects.create(case=case, check_date=date(2027, 2, 1), stage="Θεμέλια")
    client.force_login(make_user("reader", "Μόνο ανάγνωση"))
    html = client.get(reverse("cases:section_edit", args=[case.pk, "7"])).content.decode()
    assert "Θεμέλια" in html
    assert "data-infrastructure-check-open" not in html
    create_url = reverse("cases:infrastructure_check_create", args=[case.pk])
    assert client.get(create_url, **JSON).status_code == 403
    assert client.post(create_url, _infrastructure_check_values(), **JSON).status_code == 403
    assert case.infrastructure_checks.count() == 1


@pytest.mark.django_db
def test_section_7_6_latest_check_drives_the_8_4_readiness(community, staff_client):
    case = _make_case(community)
    case.dls_response_date = date(2027, 6, 1)
    case.save()
    _ready_parcel(case)
    url = reverse("cases:infrastructure_check_create", args=[case.pk])
    ready = {"curbs_ready": "True", "pavements_ready": "True", "asphalt_ready": "True"}

    staff_client.post(url, _infrastructure_check_values(check_date="2027-03-01", **ready), **JSON)
    assert announcement_readiness(case)["can_start"]

    staff_client.post(url, _infrastructure_check_values(check_date="2027-04-01"), **JSON)
    assert not announcement_readiness(case)["can_start"]


def test_section_7_6_migration_keeps_old_comments_and_flat_fields():
    from importlib import import_module
    from types import SimpleNamespace

    migration = import_module("cases.migrations.0023_section_7_6_works_checks")

    def row(**values):
        item = SimpleNamespace(**values)
        item.save = lambda update_fields: setattr(item, "saved", update_fields)
        return item

    blank_items = {name: "" for name, _ in migration.ITEM_COMMENT_FIELDS}
    check = row(**{**blank_items, "comments": "Γενικό σχόλιο", "curbs_comments": " Λείπουν 10 μ. "})
    untouched_check = row(**blank_items, comments="")
    case = row(
        works_progress_stage="Υπό κατασκευή",
        works_progress_updated_on=date(2027, 3, 4),
        works_progress_comments="",
        section8_comments="",
    )
    empty_case = row(
        works_progress_stage="",
        works_progress_updated_on=None,
        works_progress_comments="",
        section8_comments="Υφιστάμενο",
    )
    models = {
        "InfrastructureCheck": [check, untouched_check],
        "Case": [case, empty_case],
    }
    apps = SimpleNamespace(
        get_model=lambda app, name: SimpleNamespace(
            objects=SimpleNamespace(all=lambda: models[name])
        )
    )

    migration.merge_old_7_6_values(apps, None)

    assert check.comments == "Γενικό σχόλιο\nΡείθρα: Λείπουν 10 μ."
    assert not hasattr(untouched_check, "saved")
    assert case.section8_comments == (
        "Τρέχον στάδιο / γενική πορεία εργασιών: Υπό κατασκευή\n"
        "Ημερομηνία ενημέρωσης πορείας: 04/03/2027"
    )
    assert empty_case.section8_comments == "Υφιστάμενο"
    assert not hasattr(empty_case, "saved")


@pytest.mark.django_db
def test_stored_7_7_title_is_removed_with_the_infrastructure_table():
    from importlib import import_module

    from django.apps import apps

    from core.models import Role, SystemSetting

    migration = import_module("core.migrations.0020_remove_subsection_label_7_7")
    set_setting("caseSubsectionLabel.7.7", "Έλεγχος υποδομών")
    role = Role.objects.get(name="Τεχνικός λειτουργός")
    role.description = role.description.replace("(7.1–7.6)", "(7.1–7.7)")
    role.save()

    migration.remove_subsection_label_7_7(apps, None)

    assert not SystemSetting.objects.filter(key="caseSubsectionLabel.7.7").exists()
    role.refresh_from_db()
    assert "υποδομές διαχωρισμού (7.1–7.6)" in role.description
