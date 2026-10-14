"""Νέα Αίτηση Παραρτήματος 3 (plot_applications): καταχώριση και κατ' αρχήν έλεγχος."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from applications.models import Person
from core.models import Community, SystemSetting
from plot_applications.models import (
    ApplicationChild,
    ApplicationParty,
    IncomeDeclaration,
    PlotApplication,
    ResidenceCategory,
)
from plot_applications.rules import apply_evaluation, evaluate
from plots.models import Plot
from tests.fixtures.cycles import make_cycle

SUBMITTED = date(2026, 10, 1)


@pytest.fixture
def community(db):
    return Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ", name="ΑΒΓ", contact_email="ks@example.org", community_folder_code="007"
    )


@pytest.fixture
def cycle(community):
    return make_cycle(
        community,
        announcement_date=date(2026, 9, 18),
        submission_months=1,
        published_at=timezone.now(),
    )


@pytest.fixture
def available_plot(community):
    return Plot.objects.create(
        community=community, valuation_amount=Decimal("40000"), disposal_price=Decimal("10000")
    )


@pytest.fixture
def staff_client(client, make_user):
    client.force_login(make_user("supervisor", "Προϊστάμενος ελέγχου"))
    return client


def _person(identity, born=date(1990, 1, 1), **extra):
    values = dict(
        first_name="Όνομα", last_name="Επίθετο", date_of_birth=born, birth_place="Λευκωσία",
        birth_country="Κύπρος", parents_birth_place="Λευκωσία", parents_birth_country="Κύπρος",
    )
    values.update(extra)
    return Person.objects.create(identity_number=identity, **values)


def _application(cycle, *, couple=True, income=Decimal("30000"), **extra):
    values = dict(
        community=cycle.communities.get(),
        protocol_number=f"T-{PlotApplication.objects.count() + 1}",
        submitted_on=SUBMITTED,
        applicant=_person(f"A{PlotApplication.objects.count()}"),
        spouse=_person(f"S{PlotApplication.objects.count()}") if couple else None,
        email="a@example.org",
        residence_category=ResidenceCategory.AUTOCHTHON,
        residence_community="ΑΒΓ",
        family_status=(
            PlotApplication.FamilyStatus.MARRIED if couple else PlotApplication.FamilyStatus.SINGLE_PARENT
        ),
        single_parent_status="" if couple else PlotApplication.SingleParentStatus.DIVORCED,
        has_dwelling=False,
        has_residential_land=False,
        has_alienated_property=False,
        previous_housing_aid=False,
        applicant_signed=True,
        spouse_signed=couple,
    )
    values.update(extra)
    application = PlotApplication.objects.create(**values)
    ApplicationParty.objects.create(
        application=application, role=ApplicationParty.Role.APPLICANT,
        citizenship=ApplicationParty.Citizenship.CYPRIOT,
    )
    if couple:
        ApplicationParty.objects.create(
            application=application, role=ApplicationParty.Role.SPOUSE,
            citizenship=ApplicationParty.Citizenship.OTHER, citizenship_other="Πολίτης ΕΕ",
        )
    IncomeDeclaration.objects.create(
        application=application, member=IncomeDeclaration.Member.APPLICANT, gross_annual_income=income
    )
    return application


def _results(application):
    return {c.code: c.result for c in evaluate(application)["criteria"]}


@pytest.mark.django_db
class TestRules:
    def test_couple_passes(self, cycle):
        application = _application(cycle)
        outcome = evaluate(application)
        assert outcome["overall"] == "pass", [(c.code, c.note) for c in outcome["criteria"]]
        assert outcome["priority_primary"] == 1 and outcome["priority_secondary"] == 4

    def test_couple_signed_by_one_only_is_rejected(self, cycle):
        application = _application(cycle, spouse_signed=False)
        assert _results(application)["signatures"] == "fail"

    def test_single_parent_without_child_is_rejected(self, cycle):
        application = _application(cycle, couple=False)
        assert _results(application)["family"] == "fail"

    def test_single_parent_with_minor_child(self, cycle):
        application = _application(cycle, couple=False)
        ApplicationChild.objects.create(
            application=application, first_name="Τ", last_name="Τ", date_of_birth=date(2015, 1, 1),
            status=ApplicationChild.Status.MINOR,
        )
        outcome = evaluate(application)
        assert outcome["overall"] == "pass"
        assert outcome["family_members_count"] == 2
        assert outcome["priority_secondary"] == 3

    def test_student_age_limit_depends_on_sex(self, cycle):
        application = _application(cycle)
        for sex in ("F", "M"):
            ApplicationChild.objects.create(
                application=application, first_name=sex, last_name="Τ", date_of_birth=date(2002, 1, 1),
                sex=sex, status=ApplicationChild.Status.STUDENT,
            )
        children = {item.child.sex: item.recognized for item in evaluate(application)["children"]}
        assert children == {"F": False, "M": True}  # ηλικία 24: θήλυ ≤ 23, άρρεν ≤ 25

    def test_age_one_of_couple_under_45_is_enough(self, cycle):
        application = _application(cycle)
        application.applicant.date_of_birth = date(1970, 1, 1)
        application.applicant.save()
        assert _results(application)["age"] == "pass"
        application.spouse.date_of_birth = date(1975, 1, 1)
        application.spouse.save()
        assert _results(application)["age"] == "fail"

    def test_citizenship_needs_one_cypriot(self, cycle):
        application = _application(cycle)
        party = application.applicant_party
        party.citizenship = ApplicationParty.Citizenship.OTHER
        party.save()
        assert _results(application)["citizenship"] == "fail"

    def test_income_limit_and_setting_override(self, cycle):
        application = _application(cycle, income=Decimal("45000.01"))
        assert _results(application)["income"] == "fail"
        SystemSetting.objects.create(key="incomeLimitUpTo2Members", value="50000")
        assert _results(application)["income"] == "pass"

    def test_neighbouring_community_is_free_text_without_distance_check(self, cycle):
        application = _application(
            cycle, residence_category=ResidenceCategory.NEIGHBOURING, residence_community="Γειτονικό Χωριό",
        )
        assert _results(application)["residence"] == "pass"
        assert evaluate(application)["priority_primary"] == 5
        application.residence_community = " "
        assert _results(application)["residence"] == "pending"

    def test_repatriated_years(self, cycle):
        application = _application(
            cycle, residence_category=ResidenceCategory.REPATRIATED,
            abroad_from=date(2010, 1, 1), abroad_to=date(2022, 1, 1),
            community_residence_since=date(2022, 6, 1),
        )
        assert _results(application)["residence"] == "pass"
        application.community_residence_since = date(2024, 6, 1)
        assert _results(application)["residence"] == "fail"

    def test_property_yes_fails_and_unanswered_is_pending(self, cycle):
        application = _application(cycle, has_residential_land=True, has_alienated_property=None)
        results = _results(application)
        assert results["land"] == "fail" and results["alienation"] == "pending"

    def test_no_deadline_criterion(self, cycle):
        # Η Αίτηση δεν συνδέεται με Γνωστοποιήσεις.
        application = _application(cycle, submitted_on=date(2026, 11, 2))
        assert "deadline" not in _results(application)

    def test_large_family_priority(self, cycle):
        application = _application(cycle)
        for index in range(4):
            ApplicationChild.objects.create(
                application=application, first_name=str(index), last_name="Τ",
                date_of_birth=date(2012 + index, 1, 1), status=ApplicationChild.Status.MINOR,
            )
        outcome = apply_evaluation(application)
        assert outcome["priority_secondary"] == 1
        application.refresh_from_db()
        assert application.family_members_count == 6
        assert "Πολύτεκνη" in application.priority_label


def _post_data(cycle, **overrides):
    data = {
        "main-community": cycle.communities.get().pk,
        "main-submitted_on": "2026-10-01",
        "main-email": "couple@example.org",
        "main-residence_category": "autochthon",
        "main-residence_community": "ΑΒΓ",
        "main-family_status": "married",
        "main-has_dwelling": "False",
        "main-has_residential_land": "False",
        "main-has_alienated_property": "False",
        "main-previous_housing_aid": "False",
        "main-applicant_signed": "on",
        "main-spouse_signed": "on",
        "main-email_declaration_accepted": "on",
        "main-attached_documents": ["A1", "B1"],
        "applicant-identity_number": "900001",
        "applicant-first_name": "Ανδρέας",
        "applicant-last_name": "Ανδρέου",
        "applicant-date_of_birth": "1992-03-04",
        "applicant-birth_place": "Λευκωσία",
        "applicant-birth_country": "Κύπρος",
        "applicant-parents_birth_place": "Λευκωσία",
        "applicant-parents_birth_country": "Κύπρος",
        "applicant_party-citizenship": "cypriot",
        "applicant_party-mobile_phone": "99123456",
        "spouse-identity_number": "900002",
        "spouse-first_name": "Ελένη",
        "spouse-last_name": "Ανδρέου",
        "spouse-date_of_birth": "1994-05-06",
        "spouse-birth_place": "Αθήνα",
        "spouse-birth_country": "Ελλάδα",
        "spouse-parents_birth_place": "Αθήνα",
        "spouse-parents_birth_country": "Ελλάδα",
        "spouse_party-citizenship": "other",
        "spouse_party-mobile_phone": "99654321",
        "spouse_party-citizenship_other": "Ελλάδα",
        "children-TOTAL_FORMS": "1",
        "children-INITIAL_FORMS": "0",
        "children-0-first_name": "Νίκος",
        "children-0-last_name": "Ανδρέου",
        "children-0-date_of_birth": "2020-01-01",
        "children-0-status": "minor",
        "income_applicant-employment_type": "employee",
        "income_applicant-gross_annual_income": "28000",
        "income_spouse-employment_type": "employee",
        "income_spouse-gross_annual_income": "15000",
        "income_spouse-other_income_1_description": "Ενοίκια",
        "income_spouse-other_income_1_amount": "2000",
        "income_other-gross_annual_income": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestViews:
    def test_create_couple_application(self, staff_client, cycle, available_plot):
        response = staff_client.post(reverse("plot_applications:create"), _post_data(cycle))
        assert response.status_code == 302, response.context and [
            f.errors for f in response.context["forms"]._active_forms()
        ]
        application = PlotApplication.objects.get()
        assert application.protocol_number == "Π3-007-001"
        assert application.spouse.identity_number == "900002"
        assert application.attached_documents == ["A1", "B1"]
        assert application.family_income_total == Decimal("45000")
        assert application.family_members_count == 3
        assert application.eligibility_result == "pass"
        assert not application.incomes.filter(member="other").exists()
        detail = staff_client.get(reverse("plot_applications:detail", args=[application.pk]))
        assert detail.status_code == 200
        assert "Π3-007-001" in detail.content.decode()

    def test_couple_requires_spouse(self, staff_client, cycle):
        data = _post_data(cycle)
        for key in [k for k in data if k.startswith("spouse-")]:
            data[key] = ""
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 200
        assert not PlotApplication.objects.exists()

    def test_single_parent_ignores_spouse_and_reuses_person(self, staff_client, cycle, available_plot):
        existing = _person("900001", born=date(1992, 3, 4))
        data = _post_data(
            cycle, **{"main-family_status": "single_parent", "main-single_parent_status": "widowed"}
        )
        for name in ("first_name", "last_name", "date_of_birth", "birth_place"):
            data[f"applicant-{name}"] = ""
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()
        assert application.applicant == existing
        assert application.spouse is None
        assert not application.incomes.filter(member="spouse").exists()

    @pytest.mark.parametrize("category", ["autochthon", "displaced", "repatriated"])
    def test_residence_community_locked_to_application_community(
        self, staff_client, cycle, available_plot, category
    ):
        data = _post_data(cycle, **{"main-residence_category": category, "main-residence_community": "ΛΑΘΟΣ"})
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        assert PlotApplication.objects.get().residence_community == "ΑΒΓ"

    def test_internal_emigrant_community_is_free_text(self, staff_client, cycle, available_plot):
        data = _post_data(
            cycle, **{"main-residence_category": "internal_emigrant", "main-residence_community": "ΕΛΕΥΘΕΡΟ ΚΕΙΜΕΝΟ"}
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        assert PlotApplication.objects.get().residence_community == "ΕΛΕΥΘΕΡΟ ΚΕΙΜΕΝΟ"

    def test_internal_emigrant_requires_community_text(self, staff_client, cycle, available_plot):
        data = _post_data(cycle, **{"main-residence_category": "internal_emigrant", "main-residence_community": " "})
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 200
        assert "residence_community" in response.context["forms"].main.errors

    def test_neighbouring_community_comes_from_appendix1(self, staff_client, cycle, available_plot):
        data = _post_data(
            cycle, **{"main-residence_category": "neighbouring", "main-neighbouring_community": "ΠΕΔΟΥΛΑΣ"}
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        assert PlotApplication.objects.get().residence_community == "ΠΕΔΟΥΛΑΣ"

    @pytest.mark.parametrize("value", ["", "ΔΕΝ ΥΠΑΡΧΕΙ ΣΤΟ ΠΑΡΑΡΤΗΜΑ"])
    def test_neighbouring_community_must_be_listed(self, staff_client, cycle, available_plot, value):
        data = _post_data(
            cycle, **{"main-residence_category": "neighbouring", "main-neighbouring_community": value}
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 200
        assert "neighbouring_community" in response.context["forms"].main.errors
        assert not PlotApplication.objects.exists()

    def test_citizenship_other_requires_free_text(self, staff_client, cycle, available_plot):
        data = _post_data(cycle, **{"applicant_party-citizenship": "other", "applicant_party-citizenship_other": " "})
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 200
        assert "citizenship_other" in response.context["forms"].applicant_party.errors

    def test_citizenship_other_text_saved_and_cleared_for_cypriot(self, staff_client, cycle, available_plot):
        data = _post_data(
            cycle, **{"applicant_party-citizenship": "other", "applicant_party-citizenship_other": "Ελληνική"}
        )
        assert staff_client.post(reverse("plot_applications:create"), data).status_code == 302
        assert PlotApplication.objects.get().applicant_party.citizenship_other == "Ελληνική"
        PlotApplication.objects.all().delete()
        data = _post_data(
            cycle, **{"applicant_party-citizenship": "cypriot", "applicant_party-citizenship_other": "Ελληνική"}
        )
        assert staff_client.post(reverse("plot_applications:create"), data).status_code == 302
        assert PlotApplication.objects.get().applicant_party.citizenship_other == ""

    @pytest.mark.parametrize(
        ("field", "error_form"),
        [
            ("applicant_party-mobile_phone", "applicant_party"),
            ("spouse_party-mobile_phone", "spouse_party"),
            ("main-email", "main"),
            ("spouse-first_name", "spouse"),
        ],
    )
    def test_required_fields(self, staff_client, cycle, available_plot, field, error_form):
        response = staff_client.post(reverse("plot_applications:create"), _post_data(cycle, **{field: ""}))
        assert response.status_code == 200
        assert field.split("-", 1)[1] in getattr(response.context["forms"], error_form if error_form != "main" else "main").errors
        assert not PlotApplication.objects.exists()

    def test_required_labels_are_marked(self, staff_client):
        html = staff_client.get(reverse("plot_applications:create")).content.decode()
        for name in ("applicant-first_name", "applicant-last_name", "applicant-date_of_birth",
                     "applicant_party-mobile_phone", "main-email"):
            assert f'class="required" for="id_{name}"' in html or f'for="id_{name}" class="required"' in html, name

    def test_appendix1_covers_all_districts(self):
        from core.appendix1 import appendix1_choices, appendix1_communities

        districts = {entry["district"] for entry in appendix1_communities()}
        assert districts == {"ΛΕΥΚΩΣΙΑΣ", "ΛΕΜΕΣΟΥ", "ΛΑΡΝΑΚΑΣ", "ΠΑΦΟΥ", "ΑΜΜΟΧΩΣΤΟΥ"}
        assert len(appendix1_communities()) == 380
        assert len(appendix1_choices()) == 1 + len(districts)

    def test_community_list_has_only_communities_with_available_plots(self, staff_client, community):
        empty = Community.objects.create(
            district="ΛΕΥΚΩΣΙΑΣ", name="ΔΕΖ", contact_email="dez@example.org", community_folder_code="008"
        )
        for _ in range(2):
            Plot.objects.create(
                community=community, valuation_amount=Decimal("40000"), disposal_price=Decimal("10000")
            )
        Plot.objects.create(community=empty, valuation_amount=None, disposal_price=None)
        response = staff_client.get(reverse("plot_applications:create"))
        field = response.context["forms"].main.fields["community"]
        assert [field.label_from_instance(c) for c in field.queryset] == ["ΑΒΓ (2)"]

    def test_application_does_not_depend_on_announcement(self, staff_client, cycle, available_plot):
        cycle.published_at = None
        cycle.save()
        response = staff_client.post(reverse("plot_applications:create"), _post_data(cycle))
        assert response.status_code == 302

    def test_edit_keeps_protocol_number(self, staff_client, cycle, available_plot):
        staff_client.post(reverse("plot_applications:create"), _post_data(cycle))
        application = PlotApplication.objects.get()
        data = _post_data(cycle, **{"main-spouse_signed": ""})
        data.update({
            "children-INITIAL_FORMS": "1",
            "children-0-id": application.children.get().pk,
        })
        response = staff_client.post(reverse("plot_applications:edit", args=[application.pk]), data)
        assert response.status_code == 302
        application.refresh_from_db()
        assert application.protocol_number == "Π3-007-001"
        assert application.eligibility_result == "fail"  # υπογραφή μόνο από τον έναν (Ενότ. 5)

    def test_list_and_form_render(self, staff_client, cycle):
        _application(cycle)
        assert staff_client.get(reverse("plot_applications:list")).status_code == 200
        assert staff_client.get(reverse("plot_applications:list"), {"order": "priority"}).status_code == 200
        assert staff_client.get(reverse("plot_applications:create")).status_code == 200

    def test_person_in_plot_application_is_not_deleted(self, client, make_user, cycle):
        from applications.person_views import delete_refusal

        application = _application(cycle)
        assert delete_refusal(application.applicant)
        assert delete_refusal(application.spouse)
