import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from cases.section_labels import get_case_section_label, save_case_section_label
from core.configuration_forms import SystemConfigurationForm
from core.models import ActionHistory, Community
from core.permissions import ROLE_SYSTEM_ADMIN, ensure_groups
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
