from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from applications.models import Application, EligibilityCheck, Person
from applications.rules import evaluate_eligibility
from applications.person_identity import compare_person_with_payload
from django.contrib.auth import get_user_model
from django.urls import reverse

from applications.services import application_form_initial, ensure_person, generate_folder_number
from cases.models import Case, Parcel, SubmissionCycle
from core.models import ActionHistory, Community, SystemSetting


@pytest.fixture
def baseline_data(db):
    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        municipality="",
        name="ΑΓΙΑ ΒΑΡΒΑΡΑ",
        contact_email="community-0001@example.org",
        community_folder_code="001",
    )
    case = Case.objects.create(
        community=community,
        case_number="CASE-001",
        start_date=date(2026, 1, 1),
        contact_email="case@example.org",
    )
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2026, 6, 1),
        submission_start_date=date(2026, 6, 2),
        submission_end_date=date(2026, 7, 1),
        published_at="2026-06-01T10:00:00Z",
    )
    cycle.cases.add(case)
    SystemSetting.objects.update_or_create(
        key="applicationFolderPrefix",
        defaults={"value": "12", "description": "prefix"},
    )
    SystemSetting.objects.update_or_create(
        key="folderSequenceDigits",
        defaults={"value": "3", "description": "digits"},
    )
    return {"community": community, "case": case, "cycle": cycle}


def _create_person(identity, first_name="A", last_name="B", year=1990):
    return Person.objects.create(
        identity_number=identity,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date(year, 1, 1),
        birth_place="Nicosia",
        birth_country="Cyprus",
        parents_birth_place="Nicosia",
        parents_birth_country="Cyprus",
    )


def _create_application(cycle, p1, p2=None):
    folder = generate_folder_number(cycle)
    return Application.objects.create(
        submission_cycle=cycle,
        person=p1,
        person2=p2,
        folder_number=folder,
        submitted_on=date(2026, 6, 10),
        family_type=Application.FamilyType.COUPLE_NO_CHILDREN if p2 else Application.FamilyType.OTHER,
        applicant_email="applicant@example.org",
    )


@pytest.mark.django_db
def test_audit_history_create_update_delete(baseline_data):
    case = baseline_data["case"]
    cycle = baseline_data["cycle"]
    p1 = _create_person("ID-1")
    p2 = _create_person("ID-2")

    # CREATE audit for Person
    create_events = ActionHistory.objects.filter(entity_type="Person", action="CREATE")
    assert create_events.count() >= 2

    app = _create_application(cycle, p1, p2)
    check = EligibilityCheck.objects.create(
        application=app,
        criterion=EligibilityCheck.Criterion.CITIZENSHIP,
        person1_result=EligibilityCheck.Result.PASS,
        person2_result=EligibilityCheck.Result.PASS,
        overall_result=EligibilityCheck.Result.PASS,
    )
    parcel = Parcel.objects.create(case=case)

    # UPDATE audit
    app.applicant_email = "new-email@example.org"
    app.save()

    # DELETE audit
    parcel_id = parcel.id
    parcel.delete()

    assert ActionHistory.objects.filter(entity_type="Application", action="CREATE").exists()
    assert ActionHistory.objects.filter(
        entity_type="Application", action="UPDATE", field_name="applicant_email"
    ).exists()
    assert ActionHistory.objects.filter(entity_type="Parcel", entity_id=str(parcel_id), action="DELETE").exists()
    assert ActionHistory.objects.filter(entity_type="EligibilityCheck", action="CREATE").exists()

    history_entry = create_events.first()
    with pytest.raises(ValueError):
        history_entry.delete()


@pytest.mark.django_db
def test_folder_numbering_per_community_and_prefix_freeze(baseline_data):
    cycle = baseline_data["cycle"]
    p1 = _create_person("ID-10")
    app1 = _create_application(cycle, p1)
    app2 = _create_application(cycle, p1)
    assert app1.folder_number.endswith("001")
    assert app2.folder_number.endswith("002")

    prefix_setting = SystemSetting.objects.get(key="applicationFolderPrefix")
    prefix_setting.value = "99"
    prefix_setting.save()
    app1.refresh_from_db()
    assert app1.folder_number.startswith("12")

    p2 = _create_person("ID-11")
    app3 = _create_application(cycle, p2)
    assert app3.folder_number.startswith("99001")


@pytest.mark.django_db
def _person_payload(**overrides):
    base = {
        "first_name": "Maria",
        "last_name": "Georgiou",
        "identity_number": "ID-20",
        "refugee_identity_number": "",
        "citizenship_cypriot": True,
        "citizenship_repatriated": False,
        "citizenship_eu": False,
        "citizenship_other": "",
        "date_of_birth": date(1992, 2, 2),
        "birth_place": "Larnaca",
        "birth_country": "Cyprus",
        "parents_birth_place": "Larnaca",
        "parents_birth_country": "Cyprus",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_person_reuse_and_conflict_detection():
    payload = _person_payload()
    payload.pop("identity_number")
    person1 = ensure_person("ID-20", payload)
    person2 = ensure_person("ID-20", payload)
    assert person1.id == person2.id
    assert Person.objects.filter(identity_number="ID-20").count() == 1

    bad_payload = dict(payload)
    bad_payload["first_name"] = "Different"
    with pytest.raises(ValidationError):
        ensure_person("ID-20", bad_payload)


@pytest.mark.django_db
def test_person_compare_lists_differing_identity_fields():
    payload = _person_payload()
    payload.pop("identity_number")
    ensure_person("ID-21", payload)

    incoming = _person_payload(first_name="Different", identity_number="ID-21")
    result = compare_person_with_payload("ID-21", incoming)
    assert result.exists
    assert result.has_differences
    assert any(d.field == "first_name" for d in result.differences)


@pytest.mark.django_db
def test_eligibility_rules_age_income_and_overall(baseline_data):
    cycle = baseline_data["cycle"]
    p1 = _create_person("ID-30", year=1980)
    p2 = _create_person("ID-31", year=1995)
    app = _create_application(cycle, p1, p2)
    p1.citizenship_cypriot = False
    p1.save()
    p2.citizenship_cypriot = True
    p2.save()
    app.residence_category = "Αυτόχθονας"
    app.family_members_count = 4
    app.person1_income = Decimal("20000")
    app.person2_income = Decimal("15000")
    app.children_income = Decimal("1000")
    app.person1_has_property = False
    app.person2_has_property = False
    app.person1_non_alienation_clear = True
    app.person2_non_alienation_clear = True
    app.person1_previous_aid_clear = True
    app.person2_previous_aid_clear = True
    app.save()

    results, p1_age, p2_age, income_total, income_limit = evaluate_eligibility(app)
    assert p1_age >= 45
    assert p2_age < 45
    assert income_total == Decimal("36000")
    assert income_limit == Decimal("55000")
    assert results[EligibilityCheck.Criterion.AGE] == EligibilityCheck.Result.PASS
    assert results[EligibilityCheck.Criterion.INCOME] == EligibilityCheck.Result.PASS
    assert app.outcome_104 == Application.Outcome104.PASS

    app.person2_income = Decimal("40000")
    app.save()
    results, *_ = evaluate_eligibility(app)
    assert results[EligibilityCheck.Criterion.INCOME] == EligibilityCheck.Result.FAIL
    assert app.outcome_104 == Application.Outcome104.FAIL


@pytest.mark.django_db
def test_application_form_initial_includes_person_fields(baseline_data):
    cycle = baseline_data["cycle"]
    p1 = _create_person("ID-EDIT", first_name="Nikos", last_name="Papas")
    app = _create_application(cycle, p1)
    initial = application_form_initial(app)
    assert initial["person1_identity_number"] == "ID-EDIT"
    assert initial["person1_first_name"] == "Nikos"


@pytest.mark.django_db
def test_application_edit_page_login_and_folder_read_only(baseline_data, client):
    cycle = baseline_data["cycle"]
    p1 = _create_person("ID-EDIT-2")
    app = _create_application(cycle, p1)
    url = reverse("applications:edit", args=[app.pk])
    assert client.get(url).status_code == 302

    user = get_user_model().objects.create_user(username="staff", password="secret")
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 200
    assert app.folder_number.encode() in response.content


@pytest.mark.django_db
def test_app_login_page_and_redirect(client):
    login_url = reverse("login")
    assert client.get(login_url).status_code == 200
    home_url = reverse("home")
    assert client.get(home_url).status_code == 302
    assert client.get(home_url).url.startswith(login_url)

    user = get_user_model().objects.create_user(username="loginuser", password="secret")
    assert client.login(username="loginuser", password="secret")
    assert client.get(home_url).status_code == 200
