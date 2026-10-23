"""«Άτομα»: list, add, edit and delete registered persons; the ΑΔΤ never changes."""

from datetime import date

import pytest
from django.urls import reverse

from applications.models import Person
from cases.models import SubmissionCycle
from core.models import Community
from plot_applications.models import PlotApplication
from plots.models import Plot
from tests.fixtures.plot_applications import make_plot_application


@pytest.fixture
def community(db):
    return Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )


@pytest.fixture
def staff_client(client, make_user):
    client.force_login(make_user("supervisor", "Προϊστάμενος ελέγχου"))
    return client


def _person(identity="ID-100", **extra):
    values = {
        "first_name": "Μαρία",
        "last_name": "Παπαδοπούλου",
        "date_of_birth": date(1990, 5, 1),
        "birth_place": "Λευκωσία",
        "birth_country": "Κύπρος",
        "parents_birth_place": "Λευκωσία",
        "parents_birth_country": "Κύπρος",
    }
    values.update(extra)
    return Person.objects.create(identity_number=identity, **values)


def _payload(identity="ID-200", **overrides):
    data = {
        "identity_number": identity,
        "first_name": "Γιώργος",
        "last_name": "Γεωργίου",
        "date_of_birth": "1988-02-03",
        "birth_place": "Λεμεσός",
        "birth_country": "Κύπρος",
        "parents_birth_place": "Λεμεσός",
        "parents_birth_country": "Κύπρος",
        "document_type": "",
    }
    data.update(overrides)
    return data


def _application(community, person, spouse=None):
    return make_plot_application(community, person, spouse)


@pytest.mark.django_db
def test_menu_and_list_show_registered_persons(community, staff_client):
    with_application = _person("ID-1", last_name="Αλεξάνδρου")
    _person("ID-2", last_name="Βασιλείου")
    _application(community, with_application)

    home = staff_client.get(reverse("home")).content.decode()
    assert reverse("persons:list") in home

    html = staff_client.get(reverse("persons:list")).content.decode()
    assert "ID-1" in html and "Αλεξάνδρου" in html
    assert "ID-2" in html and "Βασιλείου" in html

    html = staff_client.get(reverse("persons:list") + "?q=Βασιλ").content.decode()
    assert "ID-2" in html
    assert "ID-1" not in html


@pytest.mark.django_db
def test_add_person(staff_client):
    response = staff_client.post(reverse("persons:create"), _payload(" ID-200 "))
    assert response.status_code == 302
    person = Person.objects.get()
    assert person.identity_number == "ID-200"
    assert person.date_of_birth == date(1988, 2, 3)


@pytest.mark.django_db
def test_add_refuses_an_existing_identity_number(staff_client):
    _person("ID-200")
    response = staff_client.post(reverse("persons:create"), _payload("id-200"))
    assert response.status_code == 200
    assert "Υπάρχει ήδη άτομο" in response.content.decode()
    assert Person.objects.count() == 1


@pytest.mark.django_db
def test_edit_changes_details_but_never_the_identity_number(community, staff_client):
    person = _person("ID-100")
    _application(community, person)
    url = reverse("persons:detail", args=[person.pk])

    html = staff_client.get(url).content.decode()
    assert 'name="identity_number"' in html and "disabled" in html

    response = staff_client.post(url, _payload("ID-999", first_name="Μαρίνα"))
    assert response.status_code == 302
    person.refresh_from_db()
    assert person.first_name == "Μαρίνα"
    assert person.identity_number == "ID-100"
    assert PlotApplication.objects.get().applicant == person


@pytest.mark.django_db
def test_person_with_applications_is_not_deleted(community, staff_client):
    person1 = _person("ID-1")
    person2 = _person("ID-2")
    _application(community, person1, person2)

    for person in (person1, person2):
        html = staff_client.get(reverse("persons:detail", args=[person.pk])).content.decode()
        assert "συμμετέχει σε αιτήσεις" in html
        assert reverse("persons:delete", args=[person.pk]) not in html
        response = staff_client.post(reverse("persons:delete", args=[person.pk]), follow=True)
        assert "συμμετέχει σε αιτήσεις" in response.content.decode()
    assert Person.objects.count() == 2


@pytest.mark.django_db
def test_plot_owner_is_not_deleted(community, staff_client):
    person = _person("ID-1")
    Plot.objects.create(community=community, design_number="1", owner=person)
    staff_client.post(reverse("persons:delete", args=[person.pk]))
    assert Person.objects.filter(pk=person.pk).exists()


@pytest.mark.django_db
def test_person_without_applications_is_deleted(staff_client):
    person = _person("ID-1")
    response = staff_client.post(reverse("persons:delete", args=[person.pk]))
    assert response.status_code == 302
    assert not Person.objects.exists()


@pytest.mark.django_db
def test_read_only_role_cannot_change_persons(client, make_user):
    person = _person("ID-1")
    client.force_login(make_user("reader", "Μόνο ανάγνωση"))
    assert client.get(reverse("persons:list")).status_code == 200
    html = client.get(reverse("persons:detail", args=[person.pk])).content.decode()
    assert ">Αποθήκευση</button>" not in html
    assert client.post(reverse("persons:detail", args=[person.pk]), _payload()).status_code == 403
    assert client.get(reverse("persons:create")).status_code == 403
    assert client.post(reverse("persons:delete", args=[person.pk])).status_code == 403
    assert Person.objects.filter(pk=person.pk).exists()


@pytest.mark.django_db
def test_person_screen_shows_applications_and_reorders_priority_via_drag_and_drop(
    community, staff_client, client, make_user
):
    second_community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        name="ΔΕΖ",
        contact_email="ks.dez@example.org",
        community_folder_code="002",
    )
    person = _person("ID-100")
    app1 = make_plot_application(community, person, preference_order=1)
    app2 = make_plot_application(second_community, person, preference_order=2)

    detail_url = reverse("persons:detail", args=[person.pk])
    reorder_url = reverse("persons:applications_reorder", args=[person.pk])

    html = staff_client.get(detail_url).content.decode()
    assert 'data-person-applications-sortable' in html
    assert f'data-reorder-url="{reorder_url}"' in html
    assert 'draggable="true"' in html
    assert html.index(app1.protocol_number) < html.index(app2.protocol_number)

    # Reorder so app2 becomes 1st priority and app1 becomes 2nd priority
    response = staff_client.post(
        reorder_url,
        data=f'{{"order": [{app2.pk}, {app1.pk}]}}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    app1.refresh_from_db()
    app2.refresh_from_db()
    assert app2.preference_order == 1
    assert app1.preference_order == 2

    html_after = staff_client.get(detail_url).content.decode()
    assert html_after.index(app2.protocol_number) < html_after.index(app1.protocol_number)

    # Read-only user cannot reorder
    client.force_login(make_user("reader_order", "Μόνο ανάγνωση"))
    assert (
        client.post(
            reorder_url,
            data=f'{{"order": [{app1.pk}, {app2.pk}]}}',
            content_type="application/json",
        ).status_code
        == 403
    )
