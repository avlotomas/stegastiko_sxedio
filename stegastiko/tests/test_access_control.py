"""Roles and access per function / sub-function (§Β.3, Ε-42)."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from cases.models import Case
from core.function_catalog import FUNCTIONS, FUNCTIONS_BY_CODE, grant_key
from core.models import ActionHistory, Community, Role
from core.permissions import grant_dependency_errors, has_access

DEFAULT_ROLE_NAMES = {
    "Διαχειριστής συστήματος",
    "Προϊστάμενος ελέγχου",
    "Λειτουργός καταχώρισης",
    "Τεχνικός λειτουργός",
    "Μέλος Επιτροπής",
    "Έπαρχος",
    "Μόνο ανάγνωση",
}


@pytest.fixture
def case(db):
    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )
    return Case.objects.create(
        community=community,
        case_number="CASE-ACL-01",
        case_type=Case.CaseType.NEW_DIVISION,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
    )


def _login(client, make_user, username, *roles):
    user = make_user(username, *roles)
    client.force_login(user)
    return user


def _role_post(name, grants, is_active=True):
    data = {"name": name, "description": ""}
    if is_active:
        data["is_active"] = "on"
    for key in grants:
        code, _, action = key.partition(":")
        data[f"grant__{code}__{action}"] = "on"
    return data


@pytest.mark.django_db
def test_default_roles_are_seeded_with_valid_grants():
    roles = {role.name: role for role in Role.objects.all()}
    assert DEFAULT_ROLE_NAMES <= set(roles)
    for role in roles.values():
        for key in role.grants:
            code, _, action = key.partition(":")
            assert action in FUNCTIONS_BY_CODE[code].actions, key
        assert grant_dependency_errors(set(role.grants)) == [], role.name

    officer = set(roles["Λειτουργός καταχώρισης"].grants)
    supervisor = set(roles["Προϊστάμενος ελέγχου"].grants)
    assert "case_section_9:publish" in supervisor
    assert "case_section_9:publish" not in officer
    assert not any(key.startswith("settings") for key in officer)
    admin = set(roles["Διαχειριστής συστήματος"].grants)
    assert {"settings_roles:edit", "settings_users:create"} <= admin
    assert not any(key.split(":")[1] in {"edit", "create", "delete"} for key in admin if key.startswith("case"))
    assert not any(key.startswith("application") for key in roles["Τεχνικός λειτουργός"].grants)


@pytest.mark.django_db
def test_user_without_role_only_reaches_home_and_account(client, make_user, case):
    _login(client, make_user, "nobody")
    html = client.get(reverse("home")).content.decode()
    assert reverse("cases:list") not in html
    assert reverse("system_configuration") not in html
    assert client.get(reverse("account")).status_code == 200
    for url in (
        reverse("cases:list"),
        reverse("cases:detail", args=[case.pk]),
        reverse("applications:list"),
        reverse("applications:import"),
        reverse("reminders"),
        reverse("system_configuration"),
    ):
        response = client.get(url)
        assert response.status_code == 403, url
        assert "Χωρίς πρόσβαση" in response.content.decode()


@pytest.mark.django_db
def test_read_only_role_sees_section_without_save_and_cannot_post(client, make_user, case):
    _login(client, make_user, "reader", "Μόνο ανάγνωση")
    url = reverse("cases:section_edit", args=[case.pk, "1"])
    html = client.get(url).content.decode()
    assert "Προβολή μόνο" in html
    assert ">Αποθήκευση</button>" not in html
    assert "disabled" in html
    assert client.post(url, {}).status_code == 403

    response = client.get(
        reverse("cases:land_plot_create", args=[case.pk]), HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 403
    assert response.json()["ok"] is False

    section_3 = client.get(reverse("cases:section_edit", args=[case.pk, "3"])).content.decode()
    assert reverse("cases:land_plot_create", args=[case.pk]) not in section_3


@pytest.mark.django_db
def test_publish_needs_publish_access_before_anything_else(client, make_user, case):
    url = reverse("cases:announcement_publish", args=[case.pk, 999])
    _login(client, make_user, "officer", "Λειτουργός καταχώρισης")
    assert client.post(url).status_code == 403

    _login(client, make_user, "supervisor", "Προϊστάμενος ελέγχου")
    assert client.post(url).status_code == 404


@pytest.mark.django_db
def test_technical_role_edits_section_4_only(client, make_user, case):
    _login(client, make_user, "engineer", "Τεχνικός λειτουργός")
    assert client.get(reverse("cases:section_edit", args=[case.pk, "4"])).status_code == 200
    assert client.post(reverse("cases:section_edit", args=[case.pk, "1"]), {}).status_code == 403
    assert client.get(reverse("cases:section_4_blank_pdf", args=[case.pk])).status_code == 200
    assert client.get(reverse("applications:list")).status_code == 403


@pytest.mark.django_db
def test_sub_function_needs_view_on_its_parent_function(make_user):
    user = make_user("partial")
    role = Role.objects.create(name="Μόνο Ενότητα 1", grants=["case_section_1:view"])
    role.members.add(user)
    user = get_user_model().objects.get(pk=user.pk)
    assert not has_access(user, "case_section_1")

    role.grants = ["cases:view", "case_section_1:view"]
    role.save()
    user = get_user_model().objects.get(pk=user.pk)
    assert has_access(user, "case_section_1")
    assert not has_access(user, "case_section_1", "edit")


@pytest.mark.django_db
def test_inactive_role_grants_nothing(make_user):
    user = make_user("inactive-holder", "Προϊστάμενος ελέγχου")
    assert has_access(user, "cases")
    role = Role.objects.get(name="Προϊστάμενος ελέγχου")
    role.is_active = False
    role.save()
    user = get_user_model().objects.get(pk=user.pk)
    assert not has_access(user, "cases")


@pytest.mark.django_db
def test_superuser_has_every_access():
    user = get_user_model().objects.create_superuser("root", "root@example.org", "secret")
    assert all(has_access(user, function.code, action) for function in FUNCTIONS for action in function.actions)


@pytest.mark.django_db
def test_admin_creates_role_from_matrix_and_history_is_kept(client, make_user):
    _login(client, make_user, "sysadmin", "Διαχειριστής συστήματος")
    page = client.get(reverse("settings_role_create")).content.decode()
    assert "data-access-matrix" in page
    assert "Ενότητα 4 — Τεχνική αξιολόγηση" in page

    grants = ["cases:view", "case_section_4:view", "case_section_4:export"]
    response = client.post(reverse("settings_role_create"), _role_post("Εξαγωγή Ενότητας 4", grants))
    assert response.status_code == 302
    role = Role.objects.get(name="Εξαγωγή Ενότητας 4")
    assert role.grants == sorted(grants)

    response = client.post(
        reverse("settings_role_edit", args=[role.pk]),
        _role_post("Εξαγωγή Ενότητας 4", grants + ["case_section_6:view", "case_section_6:export"]),
    )
    assert response.status_code == 302
    assert ActionHistory.objects.filter(entity_type="Role", entity_id=str(role.pk), field_name="grants").exists()
    history = client.get(reverse("settings_role_edit", args=[role.pk])).content.decode()
    assert "Ενότητα 6 — Απόφαση καταλληλότητας: Εξαγωγή PDF" in history


@pytest.mark.django_db
def test_role_matrix_rejects_grants_that_cannot_take_effect(client, make_user):
    _login(client, make_user, "sysadmin", "Διαχειριστής συστήματος")
    response = client.post(
        reverse("settings_role_create"), _role_post("Λάθος", ["case_section_2:send"])
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "απαιτεί και «Προβολή»" in html
    assert "απαιτείται «Προβολή» στη λειτουργία «Αιτήσεις Κ.Σ. / Δ.Δ.»" in html
    assert not Role.objects.filter(name="Λάθος").exists()


@pytest.mark.django_db
def test_admin_creates_user_with_roles_and_assignment_is_audited(client, make_user):
    _login(client, make_user, "sysadmin", "Διαχειριστής συστήματος")
    reader = Role.objects.get(name="Μόνο ανάγνωση")
    response = client.post(
        reverse("settings_user_create"),
        {
            "username": "new.reader",
            "first_name": "Νέα",
            "last_name": "Χρήστρια",
            "email": "reader@example.org",
            "is_active": "on",
            "roles": [reader.pk],
            "password1": "Gr8-Passw0rd!",
            "password2": "Gr8-Passw0rd!",
        },
    )
    assert response.status_code == 302
    created = get_user_model().objects.get(username="new.reader")
    assert list(created.app_roles.all()) == [reader]
    assert ActionHistory.objects.filter(entity_type="User", entity_id=str(created.pk), action="CREATE").exists()
    assert ActionHistory.objects.filter(
        entity_type="Role", entity_id=str(reader.pk), field_name="members", new_value=str(created.pk)
    ).exists()
    assert has_access(created, "cases")
    assert not has_access(created, "cases", "create")

    page = client.get(reverse("settings_user_edit", args=[created.pk])).content.decode()
    assert "Μόνο ανάγνωση" in page
    assert client.login(username="new.reader", password="Gr8-Passw0rd!")


@pytest.mark.django_db
def test_admin_cannot_lock_themselves_out(client, make_user):
    admin = _login(client, make_user, "sysadmin", "Διαχειριστής συστήματος")
    response = client.post(
        reverse("settings_user_edit", args=[admin.pk]),
        {"username": "sysadmin", "is_active": "on", "roles": []},
    )
    assert response.status_code == 200
    assert "Δεν μπορείτε να αφαιρέσετε από τον εαυτό σας" in response.content.decode()
    assert admin.app_roles.filter(name="Διαχειριστής συστήματος").exists()

    role = Role.objects.get(name="Διαχειριστής συστήματος")
    response = client.post(
        reverse("settings_role_edit", args=[role.pk]),
        _role_post(role.name, [key for key in role.grants if not key.startswith("settings_roles")]),
    )
    assert response.status_code == 200
    role.refresh_from_db()
    assert grant_key("settings_roles", "edit") in role.grants


@pytest.mark.django_db
def test_role_with_members_is_not_deleted(client, make_user):
    _login(client, make_user, "sysadmin", "Διαχειριστής συστήματος")
    in_use = Role.objects.get(name="Μόνο ανάγνωση")
    make_user("someone", "Μόνο ανάγνωση")
    client.post(reverse("settings_role_delete", args=[in_use.pk]))
    assert Role.objects.filter(pk=in_use.pk).exists()

    empty = Role.objects.create(name="Προσωρινός")
    assert client.post(reverse("settings_role_delete", args=[empty.pk])).status_code == 302
    assert not Role.objects.filter(pk=empty.pk).exists()


@pytest.mark.django_db
def test_settings_navigation_lists_only_permitted_pages(client, make_user):
    user = make_user("catalog-only")
    Role.objects.create(
        name="Μόνο κατάλογος",
        grants=["settings:view", "settings_catalogs:view"],
    ).members.add(user)
    client.force_login(user)
    html = client.get(reverse("utility_service_types")).content.decode()
    assert reverse("utility_service_types") in html
    assert reverse("settings_roles") not in html
    assert "Αποθήκευση καταλόγου" not in html
    assert client.get(reverse("settings_roles")).status_code == 403
    assert client.post(reverse("utility_service_types"), {}).status_code == 403
