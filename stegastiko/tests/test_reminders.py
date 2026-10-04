from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from cases.models import Case, Consultation
from core.models import Community
from core.reminders import (
    CONSULTATION_DUE_REMINDER_TYPE,
    consultation_due_reminder_key,
)
from core.services import set_setting


@pytest.fixture
def officer_client(client, make_user):
    client.force_login(make_user("officer-rem", "Λειτουργός καταχώρισης"))
    return client


def _case_with_consultation(due_date):
    community, _ = Community.objects.get_or_create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="Κοινότητα Υπενθυμίσεων",
        defaults={
            "contact_email": "community@example.org",
            "community_folder_code": "091",
        },
    )
    case = Case.objects.create(
        community=community,
        case_number=f"CASE-REM-{due_date:%d%m%y}",
        case_type=Case.CaseType.NEW_DIVISION,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )
    consultation = Consultation.objects.create(
        case=case,
        stage=Consultation.Stage.SUITABILITY,
        department=Consultation.Department.TKX,
        topic="Έλεγχος προθεσμίας απάντησης",
        due_date=due_date,
    )
    return case, consultation


def _division_consultation(case, due_date):
    return Consultation.objects.create(
        case=case,
        stage=Consultation.Stage.DIVISION,
        department=Consultation.Department.AHK,
        topic="Διαβούλευση διαχωρισμού",
        due_date=due_date,
    )


@pytest.mark.django_db
def test_marking_reminder_as_read_hides_it_from_dashboard_but_keeps_it_on_reminders_page(
    officer_client,
):
    case, consultation = _case_with_consultation(timezone.localdate() + timedelta(days=2))
    dashboard_html = officer_client.get(reverse("home")).content.decode()
    assert case.case_number in dashboard_html

    response = officer_client.post(
        reverse("reminder_mark_read"),
        {
            "reminder_key": consultation_due_reminder_key(consultation.pk),
            "reminder_type": CONSULTATION_DUE_REMINDER_TYPE,
            "next": reverse("home"),
        },
    )
    assert response.status_code == 302

    dashboard_html = officer_client.get(reverse("home")).content.decode()
    assert case.case_number not in dashboard_html

    reminders_html = officer_client.get(reverse("reminders")).content.decode()
    assert case.case_number in reminders_html
    assert "Διαβασμένο" in reminders_html


@pytest.mark.django_db
def test_dashboard_includes_division_consultations_with_near_due_date(officer_client):
    case, _ = _case_with_consultation(timezone.localdate() + timedelta(days=2))
    _division_consultation(case, timezone.localdate() + timedelta(days=1))

    dashboard_html = officer_client.get(reverse("home")).content.decode()
    assert "Διαβούλευση διαχωρισμού" in dashboard_html
    reminders_html = officer_client.get(reverse("reminders")).content.decode()
    assert reverse("cases:section_edit", args=[case.pk, "7"]) in reminders_html


@pytest.mark.django_db
def test_consultation_reminders_follow_the_configured_days_threshold(officer_client):
    set_setting("consultationDueReminderDays", "1")
    far_case, _ = _case_with_consultation(timezone.localdate() + timedelta(days=3))
    due_now_case, _ = _case_with_consultation(timezone.localdate() + timedelta(days=1))

    dashboard_html = officer_client.get(reverse("home")).content.decode()
    assert due_now_case.case_number in dashboard_html
    assert far_case.case_number not in dashboard_html
    assert "Δεν υπάρχουν υπενθυμίσεις" not in dashboard_html
    reminders_html = officer_client.get(reverse("reminders")).content.decode()
    assert due_now_case.case_number in reminders_html
    assert far_case.case_number not in reminders_html
