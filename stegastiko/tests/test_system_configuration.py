import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from cases.section_labels import get_case_section_label, save_case_section_label
from core.models import Community
from core.permissions import ROLE_SYSTEM_ADMIN, ensure_groups


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
    assert custom in html
    assert get_case_section_label("1") == custom
