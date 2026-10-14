"""One Person per ΑΔΤ across many applications (10.3.1): fixed fields on Person,
everything that can change between applications on Application."""

from decimal import Decimal

import pytest
from django.urls import reverse

from applications.models import Application, Person
from tests.fixtures.golden_application import golden_application_post_data, seed_application_cycle


@pytest.fixture
def application_cycle(db):
    return seed_application_cycle()


@pytest.fixture
def clerk_client(client, make_user):
    client.force_login(make_user("clerk-reuse", "Λειτουργός καταχώρισης"))
    return client


def _create(client, cycle, identity, **overrides):
    data = {
        "person1_birth_place": "Λευκωσία",
        "person1_birth_country": "Κύπρος",
        "person1_parents_birth_place": "Λευκωσία",
        "person1_parents_birth_country": "Κύπρος",
    }
    data.update(overrides)
    return client.post(
        reverse("applications:create"), golden_application_post_data(cycle, identity=identity, **data)
    )


def _child(index, name, dob="2015-01-01"):
    return {
        f"children-{index}-full_name": name,
        f"children-{index}-date_of_birth": dob,
        f"children-{index}-category": "minor",
        f"children-{index}-is_recognized_dependent": "on",
        f"children-{index}-DELETE": "",
    }


@pytest.mark.django_db
def test_second_application_reuses_person_and_keeps_own_variable_fields(clerk_client, application_cycle):
    cycle = application_cycle["cycle"]
    _create(
        clerk_client, cycle, "REUSE-1",
        person1_citizenship_cypriot="",
        person1_citizenship_eu="on",
        **_child(0, "Άννα"),
    )
    # Second application: fixed fields left blank (read-only on the form), new citizenship,
    # two children instead of one.
    response = _create(
        clerk_client, cycle, "REUSE-1",
        person1_first_name="", person1_last_name="", person1_date_of_birth="",
        person1_birth_place="", person1_birth_country="",
        person1_parents_birth_place="", person1_parents_birth_country="",
        person1_citizenship_cypriot="on",
        person1_income="21000.00",
        **{"children-TOTAL_FORMS": "2"}, **_child(0, "Άννα"), **_child(1, "Νίκος", "2020-03-03"),
    )
    assert response.status_code == 302

    assert Person.objects.filter(identity_number="REUSE-1").count() == 1
    first, second = Application.objects.filter(person__identity_number="REUSE-1").order_by("id")
    assert first.person_id == second.person_id
    assert second.person.first_name == "Μαρία"

    assert (first.person1_citizenship_eu, first.person1_citizenship_cypriot) == (True, False)
    assert (second.person1_citizenship_eu, second.person1_citizenship_cypriot) == (False, True)
    assert first.dependent_children.count() == 1
    assert second.dependent_children.count() == 2
    assert first.person1_income == Decimal("18000.00")
    assert second.person1_income == Decimal("21000.00")


@pytest.mark.django_db
def test_existing_person_fixed_field_cannot_change(clerk_client, application_cycle):
    cycle = application_cycle["cycle"]
    _create(clerk_client, cycle, "FIXED-1")
    response = _create(clerk_client, cycle, "FIXED-1", person1_first_name="Άλλο")
    assert response.status_code == 200
    errors = response.context["form"].errors
    assert "person1_first_name" in errors
    assert "δεν αλλάζει" in errors["person1_first_name"][0]
    assert Application.objects.filter(person__identity_number="FIXED-1").count() == 1
    assert Person.objects.get(identity_number="FIXED-1").first_name == "Μαρία"


@pytest.mark.django_db
def test_form_marks_existing_person_fixed_fields_read_only(clerk_client, application_cycle):
    _create(clerk_client, application_cycle["cycle"], "RO-1")
    application = Application.objects.get(person__identity_number="RO-1")
    response = clerk_client.get(reverse("applications:edit", args=[application.pk]))
    form = response.context["form"]
    assert form.fields["person1_first_name"].widget.attrs.get("readonly") == "readonly"
    assert "readonly" not in form.fields["person1_citizenship_other"].widget.attrs
    assert "readonly" not in form.fields["person2_first_name"].widget.attrs


@pytest.mark.django_db
def test_person2_cannot_repeat_person1(clerk_client, application_cycle):
    response = _create(
        clerk_client, application_cycle["cycle"], "SAME-1", person2_identity_number="SAME-1"
    )
    assert response.status_code == 200
    assert "person2_identity_number" in response.context["form"].errors


@pytest.mark.django_db
def test_person_search_by_identity_prefix_and_surname(clerk_client, application_cycle):
    _create(clerk_client, application_cycle["cycle"], "SRCH-778")
    url = reverse("applications:person_search")
    by_id = clerk_client.get(url, {"q": "SRCH-7"}).json()["results"]
    assert [r["identity_number"] for r in by_id] == ["SRCH-778"]
    by_name = clerk_client.get(url, {"q": "Δοκιμ"}).json()["results"]
    assert "SRCH-778" in [r["identity_number"] for r in by_name]
    assert clerk_client.get(url, {"q": "S"}).json()["results"] == []


@pytest.mark.django_db
def test_person_search_forbidden_without_access(client, make_user):
    client.force_login(make_user("nobody-search"))
    assert client.get(reverse("applications:person_search"), {"q": "AB"}).status_code == 403


@pytest.mark.django_db
def test_lookup_prefill_follows_the_slot_the_person_held(clerk_client, application_cycle):
    """Πρόσωπο 2 of an earlier application becomes Πρόσωπο 1 of a new one."""
    _create(
        clerk_client, application_cycle["cycle"], "HUSB-1",
        family_type="couple_no_children",
        person2_identity_number="WIFE-1",
        person2_first_name="Ελένη",
        person2_last_name="Δοκιμή",
        person2_date_of_birth="1991-02-02",
        person2_birth_place="Λεμεσός",
        person2_birth_country="Κύπρος",
        person2_parents_birth_place="Λεμεσός",
        person2_parents_birth_country="Κύπρος",
        person2_citizenship_repatriated="on",
        person2_income="9000.00",
    )
    url = reverse("applications:person_lookup")
    body = clerk_client.get(url, {"identity": "WIFE-1", "prefix": "person1"}).json()
    fields = body["prefill"]["fields"]
    assert body["applications"][0]["role"] == "Πρόσωπο 2"
    assert fields["person1_income"] == "9000.00"
    assert fields["person1_citizenship_repatriated"] is True
    assert fields["person2_income"] == "18000.00"
    assert fields["family_type"] == "couple_no_children"
    assert body["prefill"]["partner_identity_number"] == "HUSB-1"

    as_person2 = clerk_client.get(url, {"identity": "WIFE-1", "prefix": "person2"}).json()["prefill"]
    assert as_person2["fields"]["person2_income"] == "9000.00"
    assert "family_type" not in as_person2["fields"]
    assert as_person2["partner_identity_number"] == ""


@pytest.mark.django_db
def test_lookup_excludes_the_application_being_edited(clerk_client, application_cycle):
    _create(clerk_client, application_cycle["cycle"], "EXCL-1")
    application = Application.objects.get(person__identity_number="EXCL-1")
    body = clerk_client.get(
        reverse("applications:person_lookup"), {"identity": "EXCL-1", "exclude": application.pk}
    ).json()
    assert body["found"] is True
    assert body["applications_count"] == 0
    assert body["prefill"] is None
