import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from cases.section_labels import get_case_section_label, save_case_section_label
from cases.subsection_labels import get_case_subsection_label, save_case_subsection_label
from core.configuration_forms import SystemConfigurationForm
from core.models import ActionHistory, Community
from core.permissions import ROLE_SYSTEM_ADMIN, ensure_groups
from core.reminders import CONSULTATION_DUE_REMINDER_DAYS_KEY
from core.services import get_setting, set_setting


@pytest.fixture
def staff_client(db, client):
    user = get_user_model().objects.create_user(username="officer", password="secret")
    client.force_login(user)
    return client


@pytest.fixture
def admin_client(db, client):
    ensure_groups()
    user = get_user_model().objects.create_user(username="sysadmin", password="secret")
    user.groups.add(Group.objects.get(name=ROLE_SYSTEM_ADMIN))
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_system_configuration_requires_admin(staff_client):
    assert staff_client.get(reverse("system_configuration")).status_code == 302


@pytest.mark.django_db
def test_system_configuration_accessible_to_admin(admin_client):
    assert admin_client.get(reverse("system_configuration")).status_code == 200


def _configuration_post_data(**overrides):
    """Every field of the settings screen as currently rendered, plus overrides."""
    form = SystemConfigurationForm()
    data = {
        name: "" if field.initial is None else field.initial
        for name, field in form.fields.items()
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_smtp_settings_are_saved_from_the_settings_screen(admin_client):
    html = admin_client.get(reverse("system_configuration")).content.decode()
    assert "Αποστολή email (SMTP)" in html
    assert "Θέμα email ελλείψεων (2.2)" in html

    response = admin_client.post(
        reverse("system_configuration"),
        _configuration_post_data(
            email_smtpHost="smtp.example.org",
            email_smtpPort="465",
            email_smtpSecurity="ssl",
            email_smtpUsername="mailer",
            email_smtpPassword="s3cret",
            email_smtpFromEmail="stegastiko@example.org",
            email_deficiencyEmailSubject="Ελλείψεις {case_number}",
        ),
    )
    assert response.status_code == 302
    assert get_setting("smtpHost") == "smtp.example.org"
    assert get_setting("smtpPort") == "465"
    assert get_setting("smtpSecurity") == "ssl"
    assert get_setting("smtpPassword") == "s3cret"
    assert get_setting("deficiencyEmailSubject") == "Ελλείψεις {case_number}"
    assert "s3cret" not in admin_client.get(reverse("system_configuration")).content.decode()


@pytest.mark.django_db
def test_blank_smtp_password_keeps_the_stored_one(admin_client):
    set_setting("smtpPassword", "s3cret")
    response = admin_client.post(
        reverse("system_configuration"),
        _configuration_post_data(email_smtpHost="smtp.example.org"),
    )
    assert response.status_code == 302
    assert get_setting("smtpPassword") == "s3cret"


@pytest.mark.django_db
def test_consultation_reminder_days_are_saved_from_settings(admin_client):
    response = admin_client.post(
        reverse("system_configuration"),
        _configuration_post_data(setting_consultationDueReminderDays="3"),
    )
    assert response.status_code == 302
    assert get_setting(CONSULTATION_DUE_REMINDER_DAYS_KEY) == "3"


@pytest.mark.django_db
def test_smtp_password_is_masked_in_the_action_history(db):
    set_setting("smtpPassword", "first-secret")
    set_setting("smtpPassword", "second-secret")
    values = ActionHistory.objects.filter(
        entity_type="SystemSetting", field_name="value"
    ).values_list("old_value", "new_value")
    assert values
    for old_value, new_value in values:
        assert "secret" not in old_value
        assert "secret" not in new_value


@pytest.mark.django_db
def test_section_label_appears_in_page_title_and_sidebar(staff_client):
    from cases.models import Case
    from datetime import date

    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )
    case = Case.objects.create(
        community=community,
        case_number="CASE-LABEL-01",
        case_type=Case.CaseType.NEW_DIVISION,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )
    custom = "Τίτλος ενότητας 1 από ρυθμίσεις"
    save_case_section_label("1", custom)

    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "1"])).content.decode()
    assert f"<h1>{custom}</h1>" in html
    assert f'class="case-actions-nav__link is-active"' in html
    assert f"1. {custom}" in html
    assert get_case_section_label("1") == custom


@pytest.mark.django_db
def test_subsection_label_appears_on_section_edit_screen(staff_client):
    from cases.models import Case
    from datetime import date

    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )
    case = Case.objects.create(
        community=community,
        case_number="CASE-SUB-01",
        case_type=Case.CaseType.NEW_DIVISION,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )
    custom = "3.2 από ρυθμίσεις"
    save_case_subsection_label("3.2", custom)

    html = staff_client.get(reverse("cases:section_edit", args=[case.pk, "3"])).content.decode()
    assert f"3.2 {custom}" in html
    assert get_case_subsection_label("3.2") == custom


def _service_types_post(rows, extra_rows=()):
    """Catalog formset data: existing rows (instance, overrides) plus new rows."""
    data = {
        "service_types-TOTAL_FORMS": str(len(rows) + len(extra_rows)),
        "service_types-INITIAL_FORMS": str(len(rows)),
        "service_types-MIN_NUM_FORMS": "0",
        "service_types-MAX_NUM_FORMS": "1000",
    }
    for index, (item, overrides) in enumerate(rows):
        values = {
            "id": str(item.pk),
            "name": item.name,
            "display_order": str(item.display_order),
            "is_active": "on" if item.is_active else "",
        }
        values.update(overrides)
        data.update({f"service_types-{index}-{key}": value for key, value in values.items() if value != ""})
    for offset, values in enumerate(extra_rows, start=len(rows)):
        data.update({f"service_types-{offset}-{key}": value for key, value in values.items()})
    return data


@pytest.mark.django_db
def test_utility_service_catalog_requires_admin(staff_client):
    assert staff_client.get(reverse("utility_service_types")).status_code == 302


@pytest.mark.django_db
def test_utility_service_catalog_is_linked_from_settings(admin_client):
    url = reverse("utility_service_types")
    html = admin_client.get(url).content.decode()
    assert "Κατάλογος υπηρεσιών κοινής ωφέλειας (4.2)" in html
    assert url in admin_client.get(reverse("system_configuration")).content.decode()


@pytest.mark.django_db
def test_utility_service_catalog_renames_and_adds_values(admin_client):
    from datetime import date

    from cases.models import Case, UtilityServiceType

    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ", name="ΑΒΓ", contact_email="ks@example.org", community_folder_code="001"
    )
    case = Case.objects.create(
        community=community,
        case_number="CASE-SRV-01",
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )
    electricity = UtilityServiceType.objects.get(name="ΑΗΚ")
    service = case.utility_services.create(service_type=electricity)
    rows = [
        (item, {"name": "Ηλεκτρισμός (ΑΗΚ)"} if item == electricity else {})
        for item in UtilityServiceType.objects.all()
    ]
    response = admin_client.post(
        reverse("utility_service_types"),
        _service_types_post(rows, [{"name": "Φυσικό αέριο", "display_order": "6", "is_active": "on"}]),
    )
    assert response.status_code == 302

    service.refresh_from_db()
    assert service.service_type.name == "Ηλεκτρισμός (ΑΗΚ)"
    assert UtilityServiceType.objects.filter(name="Φυσικό αέριο", is_active=True).exists()
    assert ActionHistory.objects.filter(
        entity_type="UtilityServiceType", action="UPDATE", field_name="name"
    ).exists()


@pytest.mark.django_db
def test_utility_service_in_use_cannot_be_deleted(admin_client):
    from datetime import date

    from cases.models import Case, UtilityServiceType

    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ", name="ΑΒΓ", contact_email="ks@example.org", community_folder_code="001"
    )
    case = Case.objects.create(
        community=community,
        case_number="CASE-SRV-02",
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )
    used = UtilityServiceType.objects.get(name="Αποχέτευση")
    unused = UtilityServiceType.objects.get(name="Τηλεπικοινωνίες")
    case.utility_services.create(service_type=used)
    url = reverse("utility_service_types")

    rows = [(item, {"DELETE": "on"} if item == used else {}) for item in UtilityServiceType.objects.all()]
    response = admin_client.post(url, _service_types_post(rows))
    assert response.status_code == 200
    assert "χρησιμοποιείται σε υποθέσεις" in response.content.decode()
    assert UtilityServiceType.objects.filter(pk=used.pk).exists()

    rows = [(item, {"DELETE": "on"} if item == unused else {}) for item in UtilityServiceType.objects.all()]
    assert admin_client.post(url, _service_types_post(rows)).status_code == 302
    assert not UtilityServiceType.objects.filter(pk=unused.pk).exists()
