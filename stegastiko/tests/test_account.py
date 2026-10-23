import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.fixture
def user_client(db, client):
    user = get_user_model().objects.create_user(username="officer", password="old-secret")
    client.force_login(user)
    return client, user


@pytest.mark.django_db
def test_account_requires_login(client):
    assert client.get(reverse("account")).status_code == 302


@pytest.mark.django_db
def test_account_shows_username(user_client):
    client, user = user_client
    html = client.get(reverse("account")).content.decode()
    assert "Ο λογαριασμός μου" in html
    assert user.get_username() in html


@pytest.mark.django_db
def test_account_password_change(user_client):
    client, user = user_client
    response = client.post(
        reverse("account"),
        {
            "old_password": "old-secret",
            "new_password1": "new-secret-9",
            "new_password2": "new-secret-9",
        },
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("new-secret-9")
    assert client.login(username="officer", password="new-secret-9")


@pytest.mark.django_db
def test_admin_creates_user_with_must_change_password_and_enforces_on_login(client, make_user):
    from core.models import ActionHistory, Role, user_must_change_password

    admin = make_user("sysadmin", "Διαχειριστής συστήματος")
    client.force_login(admin)
    reader = Role.objects.get(name="Μόνο ανάγνωση")

    create_page = client.get(reverse("settings_user_create")).content.decode()
    assert 'name="must_change_password"' in create_page
    assert "Υποχρεωτική αλλαγή κωδικού στην επόμενη σύνδεση" in create_page

    resp = client.post(
        reverse("settings_user_create"),
        {
            "username": "temp.user",
            "first_name": "Προσωρινός",
            "last_name": "Χρήστης",
            "email": "temp@example.org",
            "is_active": "on",
            "roles": [reader.pk],
            "password1": "123",
            "password2": "123",
            "must_change_password": "on",
        },
    )
    assert resp.status_code == 302
    created = get_user_model().objects.get(username="temp.user")
    assert user_must_change_password(created) is True
    assert ActionHistory.objects.filter(
        entity_type="User",
        entity_id=str(created.pk),
        field_name="must_change_password",
        new_value="True",
    ).exists()

    # Log out admin and log in as the new user: redirected to /account/ and blocked from / until password is changed
    client.logout()
    login_resp = client.post(
        reverse("login"),
        {"username": "temp.user", "password": "123"},
    )
    assert login_resp.status_code == 302
    assert login_resp.url == reverse("account")

    home_resp = client.get(reverse("home"))
    assert home_resp.status_code == 302
    assert home_resp.url == reverse("account")

    account_html = client.get(reverse("account")).content.decode()
    assert "Πρέπει να αλλάξετε τον κωδικό πρόσβασής σας πριν συνεχίσετε στην εφαρμογή." in account_html

    # Change password on /account/
    change_resp = client.post(
        reverse("account"),
        {
            "old_password": "123",
            "new_password1": "456",
            "new_password2": "456",
        },
    )
    assert change_resp.status_code == 302
    assert change_resp.url == reverse("home")

    created.refresh_from_db()
    assert user_must_change_password(created) is False
    assert client.get(reverse("home")).status_code == 200
