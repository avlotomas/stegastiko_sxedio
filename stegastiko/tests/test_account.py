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
