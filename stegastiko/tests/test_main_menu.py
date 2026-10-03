"""Main menu structure and configurable menu labels (§Α.9.1)."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.menu_labels import DEFAULT_MENU_LABELS, MENU_LABEL_FIELDS
from core.models import Role


def _nav(html):
    return re.search(r'<nav class="site-nav".*?</nav>', html, re.S).group(0)


@pytest.mark.django_db
def test_menu_groups_requests_and_settings(client, make_user):
    client.force_login(make_user("supervisor", "Προϊστάμενος ελέγχου", "Διαχειριστής συστήματος"))
    nav = _nav(client.get(reverse("home")).content.decode())
    order = [
        "Αρχική",
        "Αιτήσεις",
        "Διαχωρισμού",
        "Απόκτησης οικοπέδου",
        "Υπενθυμίσεις",
        "Ρυθμίσεις",
        "Βασικές",
    ]
    positions = [nav.index(label) for label in order]
    assert positions == sorted(positions)
    assert reverse("cases:list") in nav
    assert reverse("applications:list") in nav
    assert reverse("system_configuration") in nav
    assert "Εισαγωγή Excel" not in nav
    assert "/admin/" not in nav


@pytest.mark.django_db
def test_system_entry_is_the_technical_admin_for_staff_only(client):
    staff = get_user_model().objects.create_user("support", password="secret", is_staff=True)
    client.force_login(staff)
    nav = _nav(client.get(reverse("home")).content.decode())
    assert 'href="/admin/"' in nav
    assert "Συστήματος" in nav
    assert reverse("system_configuration") not in nav
    assert "Διαχωρισμού" not in nav


@pytest.mark.django_db
def test_menu_shows_only_permitted_sub_entries(client, make_user):
    client.force_login(make_user("engineer", "Τεχνικός λειτουργός"))
    nav = _nav(client.get(reverse("home")).content.decode())
    assert "Διαχωρισμού" in nav
    assert "Απόκτησης οικοπέδου" not in nav
    assert "Ρυθμίσεις" not in nav


@pytest.mark.django_db
def test_menu_labels_are_edited_from_basic_settings(client, make_user):
    client.force_login(make_user("sysadmin", "Διαχειριστής συστήματος"))
    url = reverse("system_settings_menu_labels")
    page = client.get(url).content.decode()
    assert "Ονόματα μενού" in page
    data = {f"menu_{key}": DEFAULT_MENU_LABELS[key] for key, _, _ in MENU_LABEL_FIELDS}
    data["menu_applications"] = "Φάκελοι"
    data["menu_settings_basic"] = "Παράμετροι"
    assert client.post(url, data).status_code == 302

    nav = _nav(client.get(reverse("home")).content.decode())
    assert "Φάκελοι" in nav
    assert "Παράμετροι" in nav
    assert ">Αιτήσεις<" not in nav


@pytest.mark.django_db
def test_menu_labels_page_follows_branding_access(client, make_user):
    admin_role = Role.objects.get(name="Διαχειριστής συστήματος")
    assert {"settings_menu_labels:view", "settings_menu_labels:edit"} <= set(admin_role.grants)
    assert not any(key.startswith("settings_menu_labels") for key in Role.objects.get(name="Λειτουργός καταχώρισης").grants)

    client.force_login(make_user("officer", "Λειτουργός καταχώρισης"))
    assert client.get(reverse("system_settings_menu_labels")).status_code == 403
