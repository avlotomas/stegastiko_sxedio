import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from cases.section_labels import DEFAULT_CASE_SECTION_LABELS, get_case_section_label
from cases.subsection_labels import DEFAULT_CASE_SUBSECTION_LABELS, get_case_subsection_label
from core.branding import APP_SUBTITLE_DEFAULT, APP_TITLE_DEFAULT, get_app_subtitle, get_app_title
from core.forms import label_without_section_reference, split_section_reference
from core.menu_labels import DEFAULT_MENU_LABELS, get_menu_labels
from core.models import ActionHistory, Role, SystemSetting
from core.services import get_setting
from core.ui_texts import get_ui_text_overrides


def test_split_section_reference_single():
    assert split_section_reference("8.1 Ημερομηνία ανάθεσης μελέτης") == (
        "8.1",
        "Ημερομηνία ανάθεσης μελέτης",
    )


def test_split_section_reference_compound_consultation_fields():
    assert split_section_reference("5 / 8.4 Τμήμα / Υπηρεσία") == (
        "8.4",
        "Τμήμα / Υπηρεσία",
    )
    assert label_without_section_reference("5 / 8.4 Θέμα διαβούλευσης") == "Θέμα διαβούλευσης"


def _login_with_role(client, username, role_name):
    user = get_user_model().objects.create_user(username=username, password="secret")
    Role.objects.get(name=role_name).members.add(user)
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_ui_edit_mode_toggle_and_permissions(client):
    _login_with_role(client, "officer_ui", "Λειτουργός καταχώρισης")
    resp = client.post(reverse("ui_edit_mode_toggle"))
    assert resp.status_code == 403

    home_html = client.get(reverse("home")).content.decode()
    assert "data-ui-edit-mode-toggle" not in home_html

    _login_with_role(client, "admin_ui", "Διαχειριστής συστήματος")
    home_html = client.get(reverse("home")).content.decode()
    assert "data-ui-edit-mode-toggle" in home_html
    assert 'id="ui-text-edit-dialog"' in home_html

    resp = client.post(reverse("ui_edit_mode_toggle"))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "ui_edit_mode": True}

    active_html = client.get(reverse("home")).content.decode()
    assert "ui-edit-mode" in active_html

    resp_off = client.post(reverse("ui_edit_mode_toggle"), {"enabled": "0"})
    assert resp_off.status_code == 200
    assert resp_off.json() == {"ok": True, "ui_edit_mode": False}


@pytest.mark.django_db
def test_ui_text_save_and_reset_syncs_settings_and_audit_history(client):
    _login_with_role(client, "admin_save_ui", "Διαχειριστής συστήματος")
    save_url = reverse("ui_text_save")

    # 1. Generic screen text override (uiText.*)
    key = "uiText.btn_1234567890abcdef"
    resp = client.post(
        save_url,
        {
            "key": key,
            "value": "Νέα Αναζήτηση",
            "description": "Κουμπί αναζήτησης",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["value"] == "Νέα Αναζήτηση"
    assert get_setting(key) == "Νέα Αναζήτηση"
    assert get_ui_text_overrides()[key] == "Νέα Αναζήτηση"
    assert ActionHistory.objects.filter(
        entity_type="SystemSetting", action="CREATE"
    ).exists()

    # Reset deletes the custom uiText.* entry
    resp_reset = client.post(save_url, {"key": key, "reset": "1"})
    assert resp_reset.status_code == 200
    assert resp_reset.json()["reset"] is True
    assert not SystemSetting.objects.filter(key=key).exists()
    assert key not in get_ui_text_overrides()
    assert ActionHistory.objects.filter(
        entity_type="SystemSetting", action="DELETE"
    ).exists()

    # 2. Existing settings synchronization: appTitle, appSubtitle, menuLabel, caseSectionLabel, caseSubsectionLabel
    assert client.post(save_url, {"key": "appTitle", "value": "Νέος Τίτλος"}).status_code == 200
    assert get_app_title() == "Νέος Τίτλος"
    assert client.post(save_url, {"key": "appTitle", "reset": "1"}).status_code == 200
    assert get_app_title() == APP_TITLE_DEFAULT

    assert client.post(save_url, {"key": "appSubtitle", "value": "Επαρχία Λεμεσού"}).status_code == 200
    assert get_app_subtitle() == "Επαρχία Λεμεσού"
    assert client.post(save_url, {"key": "appSubtitle", "reset": "1"}).status_code == 200
    assert get_app_subtitle() == APP_SUBTITLE_DEFAULT

    assert client.post(save_url, {"key": "menuLabel.announcements", "value": "Ανακοινώσεις"}).status_code == 200
    assert get_menu_labels()["announcements"] == "Ανακοινώσεις"
    assert client.post(save_url, {"key": "menuLabel.announcements", "reset": "1"}).status_code == 200
    assert get_menu_labels()["announcements"] == DEFAULT_MENU_LABELS["announcements"]

    assert client.post(save_url, {"key": "caseSectionLabel.1", "value": "Στοιχεία Αίτησης"}).status_code == 200
    assert get_case_section_label("1") == "Στοιχεία Αίτησης"
    assert client.post(save_url, {"key": "caseSectionLabel.1", "reset": "1"}).status_code == 200
    assert get_case_section_label("1") == DEFAULT_CASE_SECTION_LABELS["1"]

    assert client.post(save_url, {"key": "caseSubsectionLabel.1.1", "value": "Ταυτότητα Αίτησης"}).status_code == 200
    assert get_case_subsection_label("1.1") == "Ταυτότητα Αίτησης"
    assert client.post(save_url, {"key": "caseSubsectionLabel.1.1", "reset": "1"}).status_code == 200
    assert get_case_subsection_label("1.1") == DEFAULT_CASE_SUBSECTION_LABELS["1.1"]

    # 3. Rejects arbitrary non-UI keys (e.g. smtpPassword) and blank values
    assert client.post(save_url, {"key": "smtpPassword", "value": "hacked"}).status_code == 400
    assert client.post(save_url, {"key": key, "value": "   "}).status_code == 400

