"""HTTP tests: login, create applicant application, verify persistence (UAT §Β.7.5)."""

import pytest
from django.urls import reverse

from applications.models import Application
from core.models import ActionHistory
from tests.fixtures.golden_application import golden_application_post_data, seed_application_cycle


@pytest.fixture
def application_cycle(db):
    return seed_application_cycle()


def _login_clerk(client, make_user):
    client.force_login(make_user("clerk-golden", "Λειτουργός καταχώρισης"))


@pytest.mark.django_db
def test_application_create_via_post_persists_and_redirects(client, make_user, application_cycle):
    """UAT-5 (partial): new application saved with generated folder number and audit."""
    cycle = application_cycle["cycle"]
    _login_clerk(client, make_user)
    url = reverse("applications:create")
    assert client.get(url).status_code == 200

    response = client.post(url, golden_application_post_data(cycle))
    assert response.status_code == 302, response.content.decode()[:500]

    app = Application.objects.get(applicant_email="golden.applicant@example.org")
    assert app.submission_cycle_id == cycle.pk
    assert app.person.identity_number == "GOLD-APP-001"
    assert app.folder_number
    assert response.url == reverse("applications:detail", args=[app.pk])

    detail = client.get(response.url)
    assert detail.status_code == 200
    assert app.folder_number.encode() in detail.content
    assert ActionHistory.objects.filter(entity_type="Application", entity_id=str(app.pk), action="CREATE").exists()


@pytest.mark.django_db
def test_application_create_sequential_folder_numbers(client, make_user, application_cycle):
    """UAT §Β.7.5: two new applications in the same community get consecutive folder numbers."""
    cycle = application_cycle["cycle"]
    _login_clerk(client, make_user)
    url = reverse("applications:create")

    r1 = client.post(url, golden_application_post_data(cycle, identity="GOLD-SEQ-001", applicant_email="seq1@example.org"))
    r2 = client.post(
        url,
        golden_application_post_data(cycle, identity="GOLD-SEQ-002", applicant_email="seq2@example.org"),
    )
    assert r1.status_code == 302 and r2.status_code == 302

    app1 = Application.objects.get(applicant_email="seq1@example.org")
    app2 = Application.objects.get(applicant_email="seq2@example.org")
    assert app1.folder_number != app2.folder_number
    suffix1 = app1.folder_number.split("-")[-1]
    suffix2 = app2.folder_number.split("-")[-1]
    assert suffix1.isdigit() and suffix2.isdigit()
    assert int(suffix2) == int(suffix1) + 1


@pytest.mark.django_db
def test_application_create_requires_login(client, application_cycle):
    cycle = application_cycle["cycle"]
    url = reverse("applications:create")
    assert client.get(url).status_code == 302
    assert client.post(url, golden_application_post_data(cycle)).status_code == 302


@pytest.mark.django_db
def test_application_create_real_login_flow(client, make_user, application_cycle):
    """Session login (not force_login) then create — mirrors browser login."""
    cycle = application_cycle["cycle"]
    user = make_user("login-clerk", "Λειτουργός καταχώρισης", password="e2e-secret")
    assert client.login(username=user.username, password="e2e-secret")

    response = client.post(reverse("applications:create"), golden_application_post_data(cycle, identity="GOLD-LOGIN-001"))
    assert response.status_code == 302
    assert Application.objects.filter(person__identity_number="GOLD-LOGIN-001").exists()
