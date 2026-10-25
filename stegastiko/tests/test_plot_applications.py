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
from plot_applications.rules import apply_evaluation, evaluate, required_documents
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
            PlotApplication.FamilyStatus.COUPLE_WITHOUT_CHILDREN
            if couple
            else PlotApplication.FamilyStatus.SINGLE_PARENT
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
        mobile_phone="99000001",
    )
    if couple:
        ApplicationParty.objects.create(
            application=application, role=ApplicationParty.Role.SPOUSE,
            citizenship=ApplicationParty.Citizenship.OTHER, citizenship_other="Πολίτης ΕΕ",
            mobile_phone="99000002",
        )
    IncomeDeclaration.objects.create(
        application=application, member=IncomeDeclaration.Member.APPLICANT, gross_annual_income=income
    )
    return attach_required_documents(application)


def attach_required_documents(application):
    application.attached_documents = [codes[0] for codes, _ in required_documents(application)]
    application.save()
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
        attach_required_documents(application)
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

    def test_repatriated_passes_without_period_dates(self, cycle):
        application = _application(cycle, residence_category=ResidenceCategory.REPATRIATED)
        assert _results(application)["residence"] == "pass"
        assert evaluate(application)["priority_primary"] == 4

    def test_internal_emigrant_passes_without_residence_period_dates(self, cycle):
        application = _application(
            cycle,
            residence_category=ResidenceCategory.INTERNAL_EMIGRANT,
            origin_parent_description="Πατέρας από ΑΒΓ",
            resides_in_controlled_areas=True,
        )
        assert _results(application)["residence"] == "pass"

        application.resides_in_controlled_areas = False
        outcome_unselected = evaluate(application)
        residence_unselected = next(c for c in outcome_unselected["eligibility_criteria"] if c.code == "residence")
        assert residence_unselected.result == "pending"
        assert "διαμονή σε ελεγχόμενες από την Κυπριακή Δημοκρατία περιοχές" in residence_unselected.note

        application.resides_in_controlled_areas = True
        application.origin_parent_description = " "
        outcome_no_origin = evaluate(application)
        residence_no_origin = next(c for c in outcome_no_origin["eligibility_criteria"] if c.code == "residence")
        assert residence_no_origin.result == "pending"
        assert "καταγωγή ως προς γονέα" in residence_no_origin.note

        application.resides_in_controlled_areas = False
        outcome_both_missing = evaluate(application)
        residence_both_missing = next(c for c in outcome_both_missing["eligibility_criteria"] if c.code == "residence")
        assert residence_both_missing.result == "pending"
        assert "καταγωγή ως προς γονέα" in residence_both_missing.note
        assert "διαμονή σε ελεγχόμενες από την Κυπριακή Δημοκρατία περιοχές" in residence_both_missing.note

    def test_property_yes_fails_and_unanswered_is_pending(self, cycle):
        application = _application(cycle, has_residential_land=True, has_alienated_property=None)
        results = _results(application)
        assert results["land"] == "fail" and results["alienation"] == "pending"

    def test_missing_required_documents_fail_completeness_not_eligibility(self, cycle):
        # Κριτήρια πληρότητας vs κριτήρια επιλεξιμότητας: τα δικαιολογητικά ανήκουν στην πληρότητα,
        # ενώ η επιλεξιμότητα κρίνει ανεξάρτητα αν ο αιτητής είναι δικαιούχος.
        application = _application(cycle)
        application.attached_documents = [c for c in application.attached_documents if c not in ("C1", "D3")]
        application.save()
        outcome = evaluate(application)
        documents = next(c for c in outcome["completeness_criteria"] if c.code == "documents")
        assert documents.result == "fail" and "ΑΗΚ" in documents.note
        assert outcome["documents_completeness"] == "incomplete"
        assert outcome["completeness_overall"] == "incomplete"
        assert outcome["eligibility_overall"] == "pass"
        assert outcome["overall"] == "pass"

    def test_documents_override_marks_application_complete_even_with_missing_documents(self, cycle):
        application = _application(cycle)
        application.attached_documents = [c for c in application.attached_documents if c not in ("C1", "D3")]
        application.documents_complete_override = True
        application.documents_complete_reason = "Προσκομίστηκαν σε φυσικό φάκελο"
        application.save()
        outcome = apply_evaluation(application)
        assert outcome["documents_criterion"].result == "pass"
        assert "Προσκομίστηκαν σε φυσικό φάκελο" in outcome["documents_criterion"].note
        assert outcome["documents_completeness"] == "complete"
        assert outcome["completeness_overall"] == "complete"
        assert outcome["eligibility_overall"] == "pass"
        application.refresh_from_db()
        assert application.documents_completeness == "complete"
        assert application.completeness_result == "complete"
        assert application.eligibility_result == "pass"

    def test_missing_required_fields_fail_completeness_only(self, cycle):
        application = _application(cycle, email="", submitted_on=None)
        outcome = evaluate(application)
        req_fields = outcome["required_fields_criterion"]
        assert req_fields.result == "fail"
        assert "Ημερομηνία υποβολής" in req_fields.note
        assert "Ηλεκτρονική Διεύθυνση" in req_fields.note
        assert outcome["completeness_overall"] == "incomplete"
        # Η ηλικία εξαρτάται από την ημερομηνία υποβολής -> εκκρεμεί στην επιλεξιμότητα,
        # αλλά αν συμπληρωθεί η ημερομηνία υποβολής και λείπει μόνο το email, η επιλεξιμότητα είναι pass.
        application.submitted_on = SUBMITTED
        application.save()
        outcome2 = evaluate(application)
        assert outcome2["required_fields_criterion"].result == "fail"
        assert outcome2["completeness_overall"] == "incomplete"
        assert outcome2["eligibility_overall"] == "pass"

    def test_required_documents_follow_the_declared_situation(self, cycle):
        application = _application(cycle, residence_category=ResidenceCategory.NEIGHBOURING)
        ApplicationChild.objects.create(
            application=application, first_name="Φ", last_name="Τ", date_of_birth=date(2003, 1, 1),
            sex="M", status=ApplicationChild.Status.STUDENT,
        )
        codes = {codes[0] for codes, _ in required_documents(application)}
        assert {"B1", "B11", "B12", "C9", "C10", "D1", "D2", "D3"} <= codes
        assert not {"C1", "B2", "B13"} & codes

        # D1, D2, D3 remain required even when has_dwelling=True and has_residential_land=True
        application.has_dwelling = True
        application.has_residential_land = True
        application.has_alienated_property = True
        application.save()
        codes_when_property_true = {codes[0] for codes, _ in required_documents(application)}
        assert {"D1", "D2", "D3"} <= codes_when_property_true
        assert not {"D4", "D5"} & codes_when_property_true

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
        "main-family_status": "couple_with_children",
        "main-has_dwelling": "False",
        "main-has_residential_land": "False",
        "main-has_alienated_property": "False",
        "main-previous_housing_aid": "False",
        "main-applicant_signed": "on",
        "main-spouse_signed": "on",
        "main-attached_documents": ["A1", "B1", "B11", "C1", "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6"],
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
        "incomes-TOTAL_FORMS": "3",
        "incomes-INITIAL_FORMS": "0",
        "incomes-0-member": "applicant",
        "incomes-0-employment_type": "employee",
        "incomes-0-description": "Μισθός",
        "incomes-0-gross_annual_income": "28000",
        "incomes-1-member": "spouse",
        "incomes-1-employment_type": "employee",
        "incomes-1-description": "Μισθός",
        "incomes-1-gross_annual_income": "15000",
        "incomes-2-member": "spouse",
        "incomes-2-employment_type": "other",
        "incomes-2-description": "Ενοίκια",
        "incomes-2-gross_annual_income": "2000",
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
        assert application.attached_documents == ["A1", "B1", "B11", "C1", "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6"]
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
            cycle, **{"main-family_status": "single_parent", "main-single_parent_status": "unmarried"}
        )
        for name in ("first_name", "last_name", "date_of_birth", "birth_place"):
            data[f"applicant-{name}"] = ""
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()
        assert application.applicant == existing
        assert application.spouse is None
        assert application.single_parent_status == "unmarried"
        assert not application.incomes.filter(member="spouse").exists()

    def test_family_status_and_single_parent_status_choices(self, staff_client):
        response = staff_client.get(reverse("plot_applications:create"))
        main = response.context["forms"].main
        assert main.fields["family_status"].choices == [
            ("couple_with_children", "Ζεύγος με τέκνα"),
            ("couple_without_children", "Ζεύγος χωρίς τέκνα"),
            ("single_parent", "Μονογονεϊκή οικογένεια"),
        ]
        assert main.fields["single_parent_status"].choices == [
            ("unmarried", "Άγαμος/η"),
            ("widowed", "Χήρος/α"),
            ("divorced", "Διαζευγμένος/η"),
            ("other", "Άλλο"),
        ]

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
            cycle,
            **{
                "main-residence_category": "internal_emigrant",
                "main-residence_community": "ΕΛΕΥΘΕΡΟ ΚΕΙΜΕΝΟ",
                "main-resides_in_controlled_areas": "on",
                "main-origin_parent_description": "Πατέρας από ΑΒΓ",
                "main-attached_documents": ["A1", "B1", "B11", "C1", "C6", "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6"],
            },
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        app = PlotApplication.objects.get()
        assert app.residence_community == "ΕΛΕΥΘΕΡΟ ΚΕΙΜΕΝΟ"
        assert app.resides_in_controlled_areas is True
        assert app.eligibility_result == "pass"

    def test_internal_emigrant_missing_community_text_marks_completeness_incomplete(
        self, staff_client, cycle, available_plot
    ):
        data = _post_data(cycle, **{"main-residence_category": "internal_emigrant", "main-residence_community": " "})
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()
        assert application.completeness_result == "incomplete"
        assert application.is_beneficiary is False

    def test_neighbouring_community_comes_from_appendix1(self, staff_client, cycle, available_plot):
        data = _post_data(
            cycle, **{"main-residence_category": "neighbouring", "main-neighbouring_community": "ΠΕΔΟΥΛΑΣ"}
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        assert PlotApplication.objects.get().residence_community == "ΠΕΔΟΥΛΑΣ"

    def test_neighbouring_community_must_be_listed(self, staff_client, cycle, available_plot):
        data = _post_data(
            cycle, **{"main-residence_category": "neighbouring", "main-neighbouring_community": "ΔΕΝ ΥΠΑΡΧΕΙ ΣΤΟ ΠΑΡΑΡΤΗΜΑ"}
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

        spouse_data = _post_data(cycle, **{"spouse_party-citizenship": "other", "spouse_party-citizenship_other": " "})
        spouse_resp = staff_client.post(reverse("plot_applications:create"), spouse_data)
        assert spouse_resp.status_code == 200
        assert "citizenship_other" in spouse_resp.context["forms"].spouse_party.errors

        min_other = {
            "main-community": cycle.communities.get().pk,
            "applicant-identity_number": "900001",
            "applicant-first_name": "Ανδρέας",
            "applicant-last_name": "Ανδρέου",
            "applicant_party-mobile_phone": "99123456",
            "applicant_party-citizenship": "other",
            "applicant_party-citizenship_other": " ",
        }
        min_resp = staff_client.post(reverse("plot_applications:create"), min_other)
        assert min_resp.status_code == 200
        assert "citizenship_other" in min_resp.context["forms"].applicant_party.errors

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
            ("main-community", "main"),
            ("applicant-identity_number", "applicant"),
            ("applicant-first_name", "applicant"),
            ("applicant-last_name", "applicant"),
            ("applicant_party-mobile_phone", "applicant_party"),
        ],
    )
    def test_required_fields(self, staff_client, cycle, available_plot, field, error_form):
        response = staff_client.post(reverse("plot_applications:create"), _post_data(cycle, **{field: ""}))
        assert response.status_code == 200
        assert field.split("-", 1)[1] in getattr(response.context["forms"], error_form if error_form != "main" else "main").errors
        assert not PlotApplication.objects.exists()

    def test_required_labels_are_marked(self, staff_client):
        html = staff_client.get(reverse("plot_applications:create")).content.decode()
        for name in (
            "applicant-first_name",
            "applicant-last_name",
            "applicant-date_of_birth",
            "applicant_party-mobile_phone",
            "applicant_party-citizenship_other",
            "spouse_party-citizenship_other",
            "main-email",
        ):
            assert f'class="required" for="id_{name}"' in html or f'for="id_{name}" class="required"' in html, name

    def test_main_form_fields_do_not_repeat_labels_as_help_text(self, staff_client):
        response = staff_client.get(reverse("plot_applications:create"))
        form = response.context["forms"].main
        assert all(not field.help_text for field in form.fields.values())
        html = response.content.decode()
        assert html.count("Αναλυτική περιγραφή / λοιπές πληροφορίες") == 1

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
        assert application.completeness_result == "incomplete"  # υπογραφή μόνο από τον έναν -> μη πλήρης (Ενότ. 5)
        assert application.eligibility_result == "pass"  # η επιλεξιμότητα δεν επηρεάζεται από την πληρότητα

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

    def test_save_requires_only_five_minimum_fields_and_can_be_completed_later(
        self, staff_client, cycle, available_plot
    ):
        html = staff_client.get(reverse("plot_applications:create")).content.decode()
        assert "Προσωρινή αποθήκευση" not in html
        assert 'name="save_draft"' not in html
        assert "data-save-button" in html

        min_data = {
            "main-community": cycle.communities.get().pk,
            "applicant-identity_number": "900001",
            "applicant-first_name": "Ανδρέας",
            "applicant-last_name": "Ανδρέου",
            "applicant_party-mobile_phone": "99123456",
        }
        response = staff_client.post(reverse("plot_applications:create"), min_data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()
        assert application.protocol_number == "Π3-007-001"
        assert application.applicant.identity_number == "900001"
        assert application.applicant.first_name == "Ανδρέας"
        assert application.applicant.last_name == "Ανδρέου"
        assert application.applicant.date_of_birth is None
        assert application.applicant_party.mobile_phone == "99123456"
        assert application.submitted_on is None
        assert application.completeness_result == "incomplete"
        assert application.is_beneficiary is False
        assert staff_client.get(reverse("plot_applications:detail", args=[application.pk])).status_code == 200

        # Completing the application with full fields updates the person and application.
        full_data = _post_data(cycle)
        response = staff_client.post(reverse("plot_applications:edit", args=[application.pk]), full_data)
        assert response.status_code == 302
        application.refresh_from_db()
        application.applicant.refresh_from_db()
        assert application.applicant.date_of_birth == date(1992, 3, 4)
        assert application.applicant.birth_place == "Λευκωσία"
        assert application.completeness_result == "complete"
        assert application.eligibility_result == "pass"
        assert application.is_beneficiary is True

    @pytest.mark.parametrize(
        ("missing_field", "error_form"),
        [
            ("main-community", "main"),
            ("applicant-identity_number", "applicant"),
            ("applicant-first_name", "applicant"),
            ("applicant-last_name", "applicant"),
            ("applicant_party-mobile_phone", "applicant_party"),
        ],
    )
    def test_save_validates_the_five_minimum_required_fields(
        self, staff_client, cycle, available_plot, missing_field, error_form
    ):
        min_data = {
            "main-community": cycle.communities.get().pk,
            "applicant-identity_number": "900001",
            "applicant-first_name": "Ανδρέας",
            "applicant-last_name": "Ανδρέου",
            "applicant_party-mobile_phone": "99123456",
            missing_field: "",
        }
        response = staff_client.post(reverse("plot_applications:create"), min_data)
        assert response.status_code == 200
        field_name = missing_field.split("-", 1)[1]
        assert field_name in getattr(response.context["forms"], error_form).errors
        assert not PlotApplication.objects.exists()

    def test_same_person_can_submit_multiple_applications_for_same_community(
        self, staff_client, cycle, available_plot
    ):
        community = cycle.communities.get()
        for expected_protocol in ("Π3-007-001", "Π3-007-002"):
            response = staff_client.post(reverse("plot_applications:create"), _post_data(cycle))
            assert response.status_code == 302
            assert PlotApplication.objects.order_by("-id").first().protocol_number == expected_protocol

        min_data = {
            "main-community": community.pk,
            "applicant-identity_number": "900001",
            "applicant-first_name": "Ανδρέας",
            "applicant-last_name": "Ανδρέου",
            "applicant_party-mobile_phone": "99123456",
        }
        response = staff_client.post(reverse("plot_applications:create"), min_data)
        assert response.status_code == 302
        assert PlotApplication.objects.filter(community=community, applicant__identity_number="900001").count() == 3
        assert PlotApplication.objects.order_by("-id").first().protocol_number == "Π3-007-003"

    def test_children_formset_renders_as_table(self, staff_client):
        html = staff_client.get(reverse("plot_applications:create")).content.decode()
        assert 'class="data-table data-table--inline-edit" data-formset-table' in html
        assert "data-formset-edit" in html
        assert "data-formset-remove" in html
        assert "data-child-modal" in html
        assert "data-income-modal" in html
        for header in ("Όνομα", "Επίθετο", "Ημερομηνία Γέννησης", "Αρ. Δελτίου Ταυτότητας", "Φύλο", "Κατάσταση", "Ενέργειες"):
            assert f">{header}<" in html

    def test_child_and_income_validations(self, staff_client, cycle, available_plot):
        # 1. Minor child aged >= 18 is rejected
        overage_minor = _post_data(cycle, **{"children-0-date_of_birth": "2005-01-01", "children-0-status": "minor"})
        resp = staff_client.post(reverse("plot_applications:create"), overage_minor)
        assert resp.status_code == 200
        assert "date_of_birth" in resp.context["forms"].children.forms[0].errors

        # 2. Student without sex or exceeding sex-specific age limit (23F / 25M) is rejected
        student_no_sex = _post_data(
            cycle, **{"children-0-date_of_birth": "2005-01-01", "children-0-status": "student", "children-0-sex": ""}
        )
        resp = staff_client.post(reverse("plot_applications:create"), student_no_sex)
        assert resp.status_code == 200
        assert "sex" in resp.context["forms"].children.forms[0].errors

        student_female_24 = _post_data(
            cycle, **{"children-0-date_of_birth": "2002-01-01", "children-0-status": "student", "children-0-sex": "F"}
        )
        resp = staff_client.post(reverse("plot_applications:create"), student_female_24)
        assert resp.status_code == 200
        assert "date_of_birth" in resp.context["forms"].children.forms[0].errors

        # 3. Adult disability child aged < 18 is rejected
        minor_as_adult_disability = _post_data(
            cycle, **{"children-0-date_of_birth": "2015-01-01", "children-0-status": "adult_disability"}
        )
        resp = staff_client.post(reverse("plot_applications:create"), minor_as_adult_disability)
        assert resp.status_code == 200
        assert "date_of_birth" in resp.context["forms"].children.forms[0].errors

        # 4. Future date of birth (after submitted_on) is rejected
        future_dob = _post_data(cycle, **{"children-0-date_of_birth": "2027-01-01", "children-0-status": "minor"})
        resp = staff_client.post(reverse("plot_applications:create"), future_dob)
        assert resp.status_code == 200
        assert "date_of_birth" in resp.context["forms"].children.forms[0].errors

        # 5. Child identity number matching applicant or spouse is rejected
        dup_parent_id = _post_data(cycle, **{"children-0-identity_number": "900001"})
        resp = staff_client.post(reverse("plot_applications:create"), dup_parent_id)
        assert resp.status_code == 200
        assert "identity_number" in resp.context["forms"].children.forms[0].errors

        # 6. Income row without employment_type or with 0 amount for employee is rejected
        missing_emp_type = _post_data(cycle, **{"incomes-0-employment_type": ""})
        resp = staff_client.post(reverse("plot_applications:create"), missing_emp_type)
        assert resp.status_code == 200
        assert "employment_type" in resp.context["forms"].incomes.forms[0].errors

        zero_employee_income = _post_data(cycle, **{"incomes-0-gross_annual_income": "0"})
        resp = staff_client.post(reverse("plot_applications:create"), zero_employee_income)
        assert resp.status_code == 200
        assert "gross_annual_income" in resp.context["forms"].incomes.forms[0].errors

        # 7. Income row with "other" source without description is rejected
        other_no_desc = _post_data(cycle, **{"incomes-2-description": " "})
        resp = staff_client.post(reverse("plot_applications:create"), other_no_desc)
        assert resp.status_code == 200
        assert "description" in resp.context["forms"].incomes.forms[2].errors

    def test_incomes_table_supports_multiple_incomes_per_member_and_child_linkage(
        self, staff_client, cycle, available_plot
    ):
        data = _post_data(
            cycle,
            **{
                "incomes-TOTAL_FORMS": "5",
                "incomes-INITIAL_FORMS": "0",
                "incomes-0-member": "applicant",
                "incomes-0-employment_type": "employee",
                "incomes-0-description": "Κύριος μισθός",
                "incomes-0-gross_annual_income": "20000",
                "incomes-1-member": "applicant",
                "incomes-1-employment_type": "other",
                "incomes-1-description": "Μερίσματα",
                "incomes-1-gross_annual_income": "3000",
                "incomes-2-member": "spouse",
                "incomes-2-employment_type": "employee",
                "incomes-2-description": "Μισθός",
                "incomes-2-gross_annual_income": "12000",
                "incomes-3-member": "spouse",
                "incomes-3-employment_type": "other",
                "incomes-3-description": "Ενοίκια",
                "incomes-3-gross_annual_income": "2000",
                "incomes-4-member": "child:0",
                "incomes-4-employment_type": "employee",
                "incomes-4-description": "Μερική απασχόληση",
                "incomes-4-gross_annual_income": "1500",
                "main-attached_documents": [
                    "A1", "B1", "B11", "C1", "D1", "D2", "D3", "D4", "D5",
                    "E1", "E3", "E4", "E6", "E7",
                ],
            },
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()
        assert application.incomes.count() == 5
        assert application.incomes.filter(member="applicant").count() == 2
        assert application.incomes.filter(member="spouse").count() == 2
        child_income = application.incomes.get(member="child")
        assert child_income.child == application.children.get()
        assert child_income.member_label == "Τέκνο: Νίκος Ανδρέου"
        assert application.family_income_total == Decimal("38500")
        assert application.eligibility_result == "pass"

        detail_html = staff_client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()
        assert "Τέκνο: Νίκος Ανδρέου" in detail_html
        assert "Μερίσματα" in detail_html
        assert "Ενοίκια" in detail_html
        assert "Οικογένεια 3 ατόμων" in detail_html
        assert "50.000,00" in detail_html

    @pytest.mark.parametrize(
        ("couple", "children_count", "expected_members", "expected_limit"),
        [
            (True, 0, 2, Decimal("45000")),
            (False, 1, 2, Decimal("45000")),
            (True, 1, 3, Decimal("50000")),
            (False, 2, 3, Decimal("50000")),
            (True, 2, 4, Decimal("55000")),
            (True, 3, 5, Decimal("65000")),
            (True, 4, 6, Decimal("65000")),
        ],
    )
    def test_income_criterion_by_family_composition(
        self, cycle, couple, children_count, expected_members, expected_limit
    ):
        application = _application(cycle, couple=couple, income=Decimal("0"))
        application.incomes.all().delete()
        for idx in range(children_count):
            ApplicationChild.objects.create(
                application=application,
                first_name=f"Τ{idx}",
                last_name="Τ",
                date_of_birth=date(2015, 1, 1),
                status=ApplicationChild.Status.MINOR,
            )
        # Split income across multiple entries summing to exactly expected_limit
        IncomeDeclaration.objects.create(
            application=application,
            member=IncomeDeclaration.Member.APPLICANT,
            employment_type=IncomeDeclaration.EmploymentType.EMPLOYEE,
            gross_annual_income=expected_limit - Decimal("5000"),
        )
        IncomeDeclaration.objects.create(
            application=application,
            member=IncomeDeclaration.Member.APPLICANT,
            employment_type=IncomeDeclaration.EmploymentType.OTHER_SOURCE,
            description="Ενοίκια",
            gross_annual_income=Decimal("5000"),
        )
        outcome = evaluate(application)
        assert outcome["family_members_count"] == expected_members
        assert outcome["family_income_total"] == expected_limit
        assert outcome["income_limit"] == expected_limit
        assert outcome["income_criterion"].result == "pass"

        # Exceeding the limit by €0.01 fails the income criterion
        IncomeDeclaration.objects.create(
            application=application,
            member=IncomeDeclaration.Member.OTHER,
            employment_type=IncomeDeclaration.EmploymentType.OTHER_SOURCE,
            description="Μερίσματα",
            gross_annual_income=Decimal("0.01"),
        )
        outcome = evaluate(application)
        assert outcome["family_income_total"] == expected_limit + Decimal("0.01")
        assert outcome["income_criterion"].result == "fail"

    def test_form_renders_live_income_criterion_summary(self, staff_client):
        html = staff_client.get(reverse("plot_applications:create")).content.decode()
        assert "data-income-summary" in html
        assert "data-income-composition" in html
        assert "data-income-limit" in html
        assert "data-income-criterion-badge" in html
        assert 'id="income-parameters"' in html

    def test_alienated_property_is_section_10_and_subsequent_sections_renumbered(self, staff_client):
        html = staff_client.get(reverse("plot_applications:create")).content.decode()
        assert "Υποβολή άλλης αίτησης στο πλαίσιο του Σχεδίου" not in html
        assert "Υπογραφές αιτητή / αιτητών" not in html
        assert "email_declaration_accepted" not in html
        assert "Για επίσημη χρήση" not in html
        for removed_field in ("received_at", "received_by", "district_file_number", "comments"):
            assert f'name="main-{removed_field}"' not in html
        expected_headings = (
            "9. Άλλη ακίνητη ιδιοκτησία",
            "10. Αποξένωση ακίνητης ιδιοκτησίας",
            "11. Παραχώρηση άλλης κρατικής στεγαστικής βοήθειας",
            "12. Υπεύθυνη δήλωση για τη δηλωθείσα ηλεκτρονική διεύθυνση",
        )
        positions = [html.index(heading) for heading in expected_headings]
        assert positions == sorted(positions)

    def test_document_labels_have_no_condition_prefixes_and_a3_removed(self):
        from plot_applications.documents import DOCUMENT_LABELS

        assert "A3" not in DOCUMENT_LABELS
        assert "C2" not in DOCUMENT_LABELS
        assert "Βεβαίωση Κοινότητας ότι ο αιτητής διαβιεί σε διεύθυνση εντός της Κοινότητας" not in DOCUMENT_LABELS.values()
        assert "C7" in DOCUMENT_LABELS
        forbidden_prefixes = (
            "Ζεύγος:",
            "Εκτοπισμένος/η:",
            "Επαναπατρισθείς:",
            "Πολίτης ΕΕ",
            "Μονογονεϊκή:",
            "Άγαμος/η γονέας:",
            "Διαζευγμένος/η:",
            "Σύζυγος που εκτίει ποινή:",
            "Χήρος/α ή θάνατος έτερου γονέα:",
            "Αφάνεια συζύγου:",
            "Πολύτεκνος:",
            "Άτομο με αναπηρία (αιτητής/σύζυγος):",
            "Τέκνα:",
            "Τέκνο φοιτητής/τρια:",
            "Τέκνο εθνοφρουρός:",
            "Ενήλικο τέκνο με αναπηρία:",
            "Διακοπή διαμονής:",
            "Απόδημος Εσωτερικού:",
            "Γειτονική Κοινότητα:",
            "Αιτητής μισθωτός:",
            "Αιτητής αυτοτελώς εργαζόμενος:",
            "Αιτητής:",
            "Σύζυγος μισθωτός:",
            "Σύζυγος αυτοτελώς εργαζόμενος:",
            "Σύζυγος:",
            "Άλλο μέλος μισθωτός:",
            "Άλλο μέλος αυτοτελώς εργαζόμενος:",
            "Άλλο μέλος:",
        )
        for code, label in DOCUMENT_LABELS.items():
            for prefix in forbidden_prefixes:
                assert not label.startswith(prefix), f"{code} still has prefix {prefix!r}: {label!r}"

    def test_applicable_documents_follow_sections_data(self):
        from plot_applications.documents import DocumentContext, applicable_codes_from_context

        # Empty context: A1 and D1–D3 are always enabled, A4 is not enabled
        empty_codes = applicable_codes_from_context(DocumentContext())
        assert {"A1", "D1", "D2", "D3"} <= empty_codes
        assert "A4" not in empty_codes

        # Applicant has "other" citizenship -> both A1 and A4 are enabled
        applicant_other_codes = applicable_codes_from_context(
            DocumentContext(applicant_citizenship="other")
        )
        assert {"A1", "A4"} <= applicant_other_codes

        # Spouse has "other" citizenship -> both A1 and A4 are enabled
        spouse_other_codes = applicable_codes_from_context(
            DocumentContext(spouse_citizenship="other")
        )
        assert {"A1", "A4"} <= spouse_other_codes

        # Both are Cypriot -> A1 is enabled, A4 is not enabled
        both_cypriot_codes = applicable_codes_from_context(
            DocumentContext(
                family_status="couple_without_children",
                applicant_citizenship="cypriot",
                spouse_citizenship="cypriot",
            )
        )
        assert "A1" in both_cypriot_codes
        assert "A4" not in both_cypriot_codes

        # Couple, autochthon, 1 student child, applicant employee (via section 4), property = False
        couple_ctx = DocumentContext(
            family_status="couple_with_children",
            residence_category="autochthon",
            applicant_citizenship="cypriot",
            applicant_is_employee=True,
            spouse_citizenship="other",
            children_count=1,
            child_statuses={"student"},
            has_dwelling=False,
            has_residential_land=False,
            has_alienated_property=False,
        )
        codes = applicable_codes_from_context(couple_ctx)
        assert {"A1", "A4", "B1", "B2", "B11", "B12", "C1", "C3", "C4", "C5", "D1", "D2", "D3", "D4", "D5", "E1"} <= codes
        assert not {"A2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B13", "B14", "C2", "C6", "C7", "C8", "C9", "C10", "E4"} & codes

        # Single parent with "other" status, repatriated, 4 children (large family), property = True
        single_other_ctx = DocumentContext(
            family_status="single_parent",
            single_parent_status="other",
            residence_category="repatriated",
            applicant_citizenship="cypriot",
            applicant_has_disability=True,
            children_count=4,
            child_statuses={"minor", "national_guard", "adult_disability"},
            has_dwelling=True,
            has_residential_land=True,
            has_alienated_property=True,
            income_pairs={("applicant", "self_employed"), ("other_member", "other")},
        )
        codes2 = applicable_codes_from_context(single_other_ctx)
        assert codes2 == {
            "A1",
            "B3", "B6", "B7", "B8", "B9", "B10", "B11", "B13", "B14",
            "C1", "C7", "C8",
            "D1", "D2", "D3",
            "E2", "E9",
        }

    def test_form_and_save_filter_non_applicable_documents(self, staff_client, cycle, available_plot):
        data = _post_data(
            cycle,
            **{
                "main-family_status": "single_parent",
                "main-single_parent_status": "unmarried",
                "main-attached_documents": ["A1", "B1", "B3", "B4", "B11", "C1", "D1", "D2", "D3", "D4", "D5", "E1", "E4"],
            },
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()
        # B1 and E4 are couple-only documents and are stripped on save for a single_parent application
        assert "B1" not in application.attached_documents
        assert "E4" not in application.attached_documents
        assert {"A1", "B3", "B4", "B11", "C1", "E1"} <= set(application.attached_documents)

        edit_html = staff_client.get(reverse("plot_applications:edit", args=[application.pk])).content.decode()
        assert 'id="plot-application-documents-dialog"' in edit_html
        assert "data-documents-modal" in edit_html
        assert 'data-dialog-open="plot-application-documents-dialog"' in edit_html
        assert "data-documents-modal-open" in edit_html
        assert 'class="checkbox-label" data-document-code="B3">' in edit_html
        assert 'class="checkbox-label" data-document-code="B4">' in edit_html
        assert 'class="checkbox-label is-disabled" data-document-code="B1">' in edit_html
        assert 'class="checkbox-label is-disabled" data-document-code="B5">' in edit_html
        assert 'value="B1"' in edit_html and 'disabled' in edit_html.split('data-document-code="B1">')[1].split("</label>")[0]
        assert 'disabled' not in edit_html.split('data-document-code="B3">')[1].split("</label>")[0]
        assert 'data-document-code="B1" hidden>' not in edit_html
        assert 'data-document-group hidden' not in edit_html

        detail_html = staff_client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()
        assert 'id="plot-application-documents-dialog"' in detail_html
        assert 'data-dialog-open="plot-application-documents-dialog"' in detail_html
        assert "data-documents-modal-open" in detail_html

    def test_save_redirects_to_edit_and_renders_save_tooltip(
        self, staff_client, cycle, available_plot
    ):
        create_html = staff_client.get(reverse("plot_applications:create")).content.decode()
        assert "data-save-button-wrapper" in create_html
        assert "data-save-button" in create_html
        assert "data-save-tooltip" in create_html

        min_data = {
            "main-community": cycle.communities.get().pk,
            "applicant-identity_number": "900001",
            "applicant-first_name": "Ανδρέας",
            "applicant-last_name": "Ανδρέου",
            "applicant_party-mobile_phone": "99123456",
        }
        min_resp = staff_client.post(reverse("plot_applications:create"), min_data)
        assert min_resp.status_code == 302
        application = PlotApplication.objects.get()
        assert min_resp.url == reverse("plot_applications:edit", args=[application.pk])

        full_resp = staff_client.post(
            reverse("plot_applications:edit", args=[application.pk]), _post_data(cycle)
        )
        assert full_resp.status_code == 302
        assert full_resp.url == reverse("plot_applications:edit", args=[application.pk])

    def test_send_email_with_missing_checkboxes_manual_edit_and_history(
        self, staff_client, cycle, available_plot, mailoutbox
    ):
        from core.models import ActionHistory, Communication
        from core.services import set_setting
        from plot_applications.services import (
            missing_documents_email_text,
            missing_documents_for_application,
        )

        set_setting("smtpHost", "smtp.example.org")
        set_setting("smtpFromEmail", "stegastiko@example.org")

        # Create an application with some missing checkboxes (e.g. C1 and D3 not checked)
        data = _post_data(
            cycle,
            **{
                "main-attached_documents": ["A1", "A4", "B1", "B2", "B11", "C3", "C4", "C5", "D1", "D2", "D4", "D5", "E1", "E4", "E6"],
            },
        )
        response = staff_client.post(reverse("plot_applications:create"), data)
        assert response.status_code == 302
        application = PlotApplication.objects.get()

        missing_codes = [code for code, _ in missing_documents_for_application(application)]
        assert missing_codes == ["C1", "D3"]
        missing_text = missing_documents_email_text(application)
        assert "Ελλείποντα δικαιολογητικά έγγραφα:" in missing_text
        assert "- Λογαριασμός ΑΗΚ στο όνομα αιτητή" in missing_text
        assert "- Πιστοποιητικό έρευνας ακίνητης ιδιοκτησίας — γονείς αιτητή" in missing_text
        # Checked documents and non-applicable documents are not in the missing text
        assert "Αντίγραφο πιστοποιητικού γάμου" not in missing_text
        assert "Διακανονισμός φύλαξης τέκνων" not in missing_text

        # Detail and Edit pages render the email button, modal, prefilled missing checkboxes, insert button, and sticky bars
        detail_html = staff_client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()
        assert 'id="plot-application-email-dialog"' in detail_html
        assert "data-insert-missing-documents" in detail_html
        assert "Λογαριασμός ΑΗΚ στο όνομα αιτητή" in detail_html
        assert "data-sticky-toolbar" in detail_html
        assert "toolbar--sticky" in detail_html

        edit_html = staff_client.get(reverse("plot_applications:edit", args=[application.pk])).content.decode()
        assert 'id="plot-application-email-dialog"' in edit_html
        assert 'data-collect-live-missing="1"' in edit_html
        assert "data-sticky-form-actions" in edit_html
        assert "form-actions--sticky" in edit_html

        # Send email with manually edited body containing the missing checkboxes
        custom_body = (
            "Αγαπητέ/ή κ. Ανδρέου,\n\n"
            + missing_text
            + "\n\nΠαρακαλούμε επικοινωνήστε με την Επαρχιακή Διοίκηση."
        )
        send_url = reverse("plot_applications:email_send", args=[application.pk])
        send_resp = staff_client.post(
            send_url,
            {
                "recipient": application.email,
                "subject": f"Ελλείποντα δικαιολογητικά — {application.protocol_number}",
                "body": custom_body,
            },
            HTTP_ACCEPT="application/json",
        )
        assert send_resp.status_code == 200
        payload = send_resp.json()
        assert payload["ok"] is True
        assert application.email in payload["message"]
        assert "Ελλείποντα δικαιολογητικά" in payload["log_html"]

        assert len(mailoutbox) == 1
        sent_mail = mailoutbox[0]
        assert sent_mail.to == ["couple@example.org"]
        assert sent_mail.subject == f"Ελλείποντα δικαιολογητικά — {application.protocol_number}"
        assert "Παρακαλούμε επικοινωνήστε με την Επαρχιακή Διοίκηση." in sent_mail.body
        assert "- Λογαριασμός ΑΗΚ στο όνομα αιτητή" in sent_mail.body

        comm = Communication.objects.get(object_id=application.pk)
        assert comm.status == "sent"
        assert comm.sent_at is not None
        assert comm.recipient == "couple@example.org"
        assert ActionHistory.objects.filter(
            entity_type="Communication", entity_id=str(comm.pk), application_id=application.pk
        ).exists()

        # Duplicate double-submit within 120s is rejected
        dup_resp = staff_client.post(
            send_url,
            {
                "recipient": application.email,
                "subject": f"Ελλείποντα δικαιολογητικά — {application.protocol_number}",
                "body": custom_body,
            },
            HTTP_ACCEPT="application/json",
        )
        assert dup_resp.status_code == 400
        assert dup_resp.json()["ok"] is False

        # Communication detail JSON endpoint returns the full email for the history modal
        detail_comm_resp = staff_client.get(
            reverse("plot_applications:communication_detail", args=[application.pk, comm.pk]),
            HTTP_ACCEPT="application/json",
        )
        assert detail_comm_resp.status_code == 200
        comm_data = detail_comm_resp.json()
        assert comm_data["ok"] is True
        assert comm_data["recipient"] == "couple@example.org"
        assert comm_data["body"] == custom_body
        assert comm_data["status"] == "sent"

        # Person detail page also displays the sent email history and send action
        person_html = staff_client.get(
            reverse("persons:detail", args=[application.applicant.pk])
        ).content.decode()
        assert "Ιστορικό απεσταλμένων email" in person_html
        assert f"Ελλείποντα δικαιολογητικά — {application.protocol_number}" in person_html
        assert reverse("plot_applications:communication_detail", args=[application.pk, comm.pk]) in person_html

    def test_subsection_visibility_in_view_and_edit_and_delete_action(
        self, cycle, available_plot, staff_client, client, make_user
    ):
        from core.models import ActionHistory, Role

        resp = staff_client.post(reverse("plot_applications:create"), _post_data(cycle))
        assert resp.status_code == 302
        application = PlotApplication.objects.get()
        original_applicant_id = application.applicant_id
        original_income_count = application.incomes.count()

        # Role that only views section_1 and section_8, and only edits section_2
        role = Role.objects.create(
            name="Περιορισμένος Λειτουργός Αιτήσεων",
            grants=[
                "plot_applications:view",
                "plot_app_section_1:view",
                "plot_app_section_8:view",
                "plot_applications:edit",
                "plot_app_section_2:edit",
            ],
        )
        limited_user = make_user("limited_plot_user")
        role.members.add(limited_user)
        client.force_login(limited_user)

        detail_html = client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert "1. Προσωπικά στοιχεία αιτητή/αιτήτριας" in detail_html
        assert "8. Εισοδήματα" in detail_html
        assert "2. Τόπος διαμονής" not in detail_html
        assert "7. Τέκνα" not in detail_html
        assert "Κατ' αρχήν έλεγχος κριτηρίων" not in detail_html
        assert "data-documents-modal-open" not in detail_html

        edit_html = client.get(
            reverse("plot_applications:edit", args=[application.pk])
        ).content.decode()
        assert "2. Τόπος διαμονής αιτητή/αιτήτριας" in edit_html
        assert "1. Προσωπικά στοιχεία αιτητή/αιτήτριας" not in edit_html
        assert "8. Εισοδήματα" not in edit_html
        assert "data-documents-modal-open" not in edit_html

        # Submitting edit with only section_2 updates section_2 and preserves all other subsections
        edit_resp = client.post(
            reverse("plot_applications:edit", args=[application.pk]),
            {
                "main-residence_category": ResidenceCategory.AUTOCHTHON,
                "main-residence_street": "Οδός Ανανεωμένη",
                "main-residence_number": "99",
                "main-residence_postal_code": "2000",
                "main-residence_notes": "Νέα σημείωση διαμονής",
            },
        )
        assert edit_resp.status_code == 302
        application.refresh_from_db()
        assert application.residence_street == "Οδός Ανανεωμένη"
        assert application.residence_number == "99"
        assert application.applicant_id == original_applicant_id
        assert application.incomes.count() == original_income_count

        # User without plot_applications:delete cannot delete
        delete_url = reverse("plot_applications:delete", args=[application.pk])
        assert client.post(delete_url).status_code == 403
        assert PlotApplication.objects.filter(pk=application.pk).exists()

        # Staff user (with plot_applications:delete) deletes the application
        client.force_login(make_user("supervisor_del", "Προϊστάμενος ελέγχου"))
        del_resp = client.post(delete_url)
        assert del_resp.status_code == 302
        assert not PlotApplication.objects.filter(pk=application.pk).exists()
        assert ActionHistory.objects.filter(
            entity_type="PlotApplication", action="DELETE"
        ).exists()

    def test_document_notes_icon_by_default_and_italic_bold_in_email(
        self, staff_client, cycle, available_plot, mailoutbox
    ):
        from core.services import set_setting
        from plot_applications.documents import DOCUMENT_LABELS
        from plot_applications.services import missing_documents_email_text

        set_setting("smtpHost", "smtp.example.org")
        set_setting("smtpFromEmail", "stegastiko@example.org")

        # 1. Create form renders note icon next to every certificate and hides note input by default
        create_html = staff_client.get(reverse("plot_applications:create")).content.decode()
        for code in DOCUMENT_LABELS:
            assert f'data-document-note-toggle="{code}"' in create_html
            assert f'data-document-note-wrap="{code}" hidden' in create_html
            assert f'data-document-note-input="{code}"' in create_html

        # 2. Save application with a note on C1 (unchecked) and B1 (checked)
        data = _post_data(
            cycle,
            **{
                "main-attached_documents": [
                    "A1", "A4", "B1", "B2", "B11", "C3", "C4", "C5",
                    "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6",
                ],
                "document_note_C1": "να είναι του τελευταίου τριμήνου",
            },
        )
        resp = staff_client.post(reverse("plot_applications:create"), data)
        assert resp.status_code == 302
        application = PlotApplication.objects.get()
        assert application.document_notes == {"C1": "να είναι του τελευταίου τριμήνου"}

        # 3. Missing documents email text formats the note next to the certificate as italic/bold (***...***)
        missing_text = missing_documents_email_text(application)
        c1_label = DOCUMENT_LABELS["C1"]
        assert f"- {c1_label} ***να είναι του τελευταίου τριμήνου***" in missing_text

        # 4. Edit and Detail pages render the icon with has-note class, keep input hidden by default,
        #    and render the rich email body editor for italic/bold display
        edit_html = staff_client.get(reverse("plot_applications:edit", args=[application.pk])).content.decode()
        assert 'class="document-note-btn has-note"' in edit_html
        assert 'data-document-note-wrap="C1" hidden' in edit_html
        assert 'value="να είναι του τελευταίου τριμήνου"' in edit_html
        assert "data-email-rich-body" in edit_html

        detail_html = staff_client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()
        assert 'data-document-note-toggle="C1"' in detail_html
        assert 'data-document-note-wrap="C1" hidden' in detail_html
        assert "data-email-rich-body" in detail_html

        # 5. Sending the email sends both the plain text and HTML alternative with <strong><em>...</em></strong>
        #    and also persists any live document_note_* fields submitted with the email form
        send_url = reverse("plot_applications:email_send", args=[application.pk])
        send_resp = staff_client.post(
            send_url,
            {
                "recipient": application.email,
                "subject": f"Ελλείποντα δικαιολογητικά — {application.protocol_number}",
                "body": missing_text,
                "document_note_C1": "να είναι του τελευταίου τριμήνου",
                "document_note_D3": "λείπει της συζύγου",
            },
            HTTP_ACCEPT="application/json",
        )
        assert send_resp.status_code == 200
        assert send_resp.json()["ok"] is True

        application.refresh_from_db()
        assert application.document_notes == {
            "C1": "να είναι του τελευταίου τριμήνου",
            "D3": "λείπει της συζύγου",
        }

        assert len(mailoutbox) == 1
        sent_mail = mailoutbox[0]
        assert f"- {c1_label} ***να είναι του τελευταίου τριμήνου***" in sent_mail.body
        assert len(sent_mail.alternatives) == 1
        html_body, mimetype = sent_mail.alternatives[0]
        assert mimetype == "text/html"
        assert f"- {c1_label} <strong><em>να είναι του τελευταίου τριμήνου</em></strong>" in html_body

    def test_completeness_and_eligibility_separation_and_documents_override_views(
        self, staff_client, cycle, available_plot
    ):
        # 1. Create an application that satisfies all eligibility criteria,
        #    but is missing required documents (C1 and D3 unchecked).
        data = _post_data(
            cycle,
            **{
                "main-attached_documents": [
                    "A1", "A4", "B1", "B2", "B11", "C3", "C4", "C5",
                    "D1", "D2", "D4", "D5", "E1", "E4", "E6",
                ],
            },
        )
        resp = staff_client.post(reverse("plot_applications:create"), data)
        assert resp.status_code == 302
        application = PlotApplication.objects.get()
        assert application.eligibility_result == "pass"
        assert application.documents_completeness == "incomplete"
        assert application.completeness_result == "incomplete"

        # 2. Detail page displays the two separate tables (completeness vs eligibility)
        detail_html = staff_client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()
        assert "1. Κριτήρια πληρότητας αίτησης" in detail_html
        assert "2. Κριτήρια επιλεξιμότητας δικαιούχου" in detail_html
        assert "data-completeness-criteria-table" in detail_html
        assert "data-eligibility-criteria-table" in detail_html
        assert "Υποχρεωτικά πεδία αίτησης" in detail_html

        # 3. Override documents completeness from detail view (even without a reason or with a reason)
        override_url = reverse("plot_applications:documents_completeness_save", args=[application.pk])
        override_resp = staff_client.post(
            override_url,
            {
                "documents_complete_override": "on",
                "documents_complete_reason": "Εγκρίθηκε παρά την έλλειψη λογαριασμού ΑΗΚ",
            },
        )
        assert override_resp.status_code == 302
        application.refresh_from_db()
        assert application.documents_complete_override is True
        assert application.documents_complete_reason == "Εγκρίθηκε παρά την έλλειψη λογαριασμού ΑΗΚ"
        assert application.documents_completeness == "complete"
        assert application.completeness_result == "complete"
        assert application.eligibility_result == "pass"

        # 4. Also allow overriding without reason text
        override_no_reason = staff_client.post(
            override_url,
            {
                "documents_complete_override": "on",
                "documents_complete_reason": "",
            },
        )
        assert override_no_reason.status_code == 302
        application.refresh_from_db()
        assert application.documents_complete_override is True
        assert application.documents_completeness == "complete"
        assert application.completeness_result == "complete"

        # 5. List filters by completeness, documents_completeness, and eligibility_result independently
        list_complete = staff_client.get(
            reverse("plot_applications:list"), {"completeness": "complete"}
        )
        assert list_complete.status_code == 200
        assert application in list_complete.context["applications"]

        list_incomplete = staff_client.get(
            reverse("plot_applications:list"), {"completeness": "incomplete"}
        )
        assert list_incomplete.status_code == 200
        assert application not in list_incomplete.context["applications"]

    def test_plot_application_change_history_timeline_and_permissions(
        self, client, make_user, cycle, available_plot
    ):
        from core.models import Role

        user = make_user("officer_hist", "Προϊστάμενος ελέγχου")
        user.first_name = "Νάντια"
        user.last_name = "Παπαδοπούλου"
        user.save()
        client.force_login(user)

        create_resp = client.post(reverse("plot_applications:create"), _post_data(cycle))
        assert create_resp.status_code == 302
        application = PlotApplication.objects.get()
        existing_child = application.children.get()
        incomes = list(application.incomes.all())

        # Edit main field (email), add a second child, and change first income
        edit_data = _post_data(
            cycle,
            **{
                "main-email": "updated@example.org",
                "children-TOTAL_FORMS": "2",
                "children-INITIAL_FORMS": "1",
                "children-0-id": str(existing_child.pk),
                "children-0-first_name": existing_child.first_name,
                "children-0-last_name": existing_child.last_name,
                "children-0-date_of_birth": existing_child.date_of_birth.isoformat(),
                "children-0-status": existing_child.status,
                "children-1-first_name": "Ελένη",
                "children-1-last_name": "Αιτητή",
                "children-1-date_of_birth": "2018-04-10",
                "children-1-identity_number": "CH100",
                "children-1-sex": "F",
                "children-1-status": ApplicationChild.Status.MINOR,
                "incomes-TOTAL_FORMS": "3",
                "incomes-INITIAL_FORMS": "3",
                "incomes-0-id": str(incomes[0].pk),
                "incomes-0-member": IncomeDeclaration.Member.APPLICANT,
                "incomes-0-employment_type": IncomeDeclaration.EmploymentType.EMPLOYEE,
                "incomes-0-description": "Μισθός",
                "incomes-0-gross_annual_income": "24500.00",
                "incomes-1-id": str(incomes[1].pk),
                "incomes-2-id": str(incomes[2].pk),
            },
        )
        edit_resp = client.post(
            reverse("plot_applications:edit", args=[application.pk]), edit_data
        )
        assert edit_resp.status_code == 302

        history_url = reverse("plot_applications:history", args=[application.pk])
        detail_html = client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        edit_html = client.get(
            reverse("plot_applications:edit", args=[application.pk])
        ).content.decode()
        assert f'data-history-timeline-open="{history_url}"' in detail_html
        assert f'data-history-timeline-open="{history_url}"' in edit_html
        assert 'id="history-timeline-dialog"' in detail_html
        assert 'id="history-timeline-dialog"' in edit_html

        hist_resp = client.get(history_url, HTTP_ACCEPT="application/json")
        assert hist_resp.status_code == 200
        payload = hist_resp.json()
        assert payload["ok"] is True
        timeline_html = payload["timeline_html"]
        assert "Νάντια Παπαδοπούλου (officer_hist)" in timeline_html
        assert "Ηλεκτρονική Διεύθυνση" in timeline_html
        assert "couple@example.org" in timeline_html
        assert "updated@example.org" in timeline_html
        assert "7. Τέκνο (Ελένη Αιτητή)" in timeline_html
        assert "Ετήσιο Ποσό (€)" in timeline_html
        assert "24500.00" in timeline_html

        # Automatically recalculated fields are hidden from the timeline
        for hidden_field in (
            "children_count",
            "recognized_children_count",
            "family_members_count",
            "family_income_total",
            "documents_completeness",
            "completeness_result",
            "completeness_details",
            "eligibility_result",
            "eligibility_details",
            "application_stage",
            "plot_allocation_status",
            "priority_primary",
            "priority_secondary",
            "priority_label",
        ):
            assert hidden_field not in timeline_html

        # User without plot_app_change_history:view gets 403 and does not see the button
        no_hist_role = Role.objects.create(
            name="Χωρίς Ιστορικό Αλλαγών",
            grants=["plot_applications:view", "plot_app_basic:view"],
        )
        restricted_user = make_user("restricted_hist")
        no_hist_role.members.add(restricted_user)
        client.force_login(restricted_user)

        restricted_detail = client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert f'data-history-timeline-open="{history_url}"' not in restricted_detail
        assert client.get(history_url, HTTP_ACCEPT="application/json").status_code == 403

    def test_build_timeline_groups_within_five_seconds_and_splits_later_saves(self, db):
        from datetime import timedelta

        from core.models import ActionHistory
        from core.timeline import build_timeline

        t0 = timezone.now()
        e1 = ActionHistory.objects.create(
            entity_type="PlotApplication",
            entity_id="999",
            action=ActionHistory.ActionType.UPDATE,
            field_name="email",
            old_value="a@example.org",
            new_value="b@example.org",
            user_id=7,
            timestamp=t0,
        )
        e2 = ActionHistory.objects.create(
            entity_type="PlotApplication",
            entity_id="999",
            action=ActionHistory.ActionType.UPDATE,
            field_name="correspondence_street",
            old_value="Οδός 1",
            new_value="Οδός 2",
            user_id=7,
            timestamp=t0 + timedelta(seconds=2),
        )
        e3 = ActionHistory.objects.create(
            entity_type="PlotApplication",
            entity_id="999",
            action=ActionHistory.ActionType.UPDATE,
            field_name="email",
            old_value="b@example.org",
            new_value="c@example.org",
            user_id=7,
            timestamp=t0 + timedelta(seconds=10),
        )
        entries = ActionHistory.objects.filter(pk__in=[e1.pk, e2.pk, e3.pk]).order_by(
            "-timestamp", "-id"
        )
        events = build_timeline(entries)
        assert len(events) == 2
        assert len(events[0]["changes"]) == 1
        assert events[0]["changes"][0]["new_value"] == "c@example.org"
        assert len(events[1]["changes"]) == 2

    def test_grid_navigation_buttons_and_no_is_examined_field(
        self, staff_client, cycle, available_plot
    ):
        # 1. Create/Edit/Detail/List do NOT contain is_examined
        create_html = staff_client.get(reverse("plot_applications:create")).content.decode()
        assert "is_examined" not in create_html
        assert "Εξετάστηκε" not in create_html

        response = staff_client.post(reverse("plot_applications:create"), _post_data(cycle))
        assert response.status_code == 302
        application = PlotApplication.objects.get()

        edit_html = staff_client.get(
            reverse("plot_applications:edit", args=[application.pk])
        ).content.decode()
        assert "is_examined" not in edit_html
        assert "Εξετάστηκε" not in edit_html
        assert f'href="{reverse("plot_applications:detail", args=[application.pk])}"' in edit_html

        detail_html = staff_client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert "Εξετάστηκε" not in detail_html

        # 2. Grid (list) shows Κατάσταση and Επεξεργασία buttons
        list_html = staff_client.get(reverse("plot_applications:list")).content.decode()
        assert "Εξετάστηκε" not in list_html
        assert f'href="{reverse("plot_applications:detail", args=[application.pk])}"' in list_html
        assert f'href="{reverse("plot_applications:edit", args=[application.pk])}"' in list_html
        assert "data-grid-status-link" in list_html
        assert "data-grid-edit-link" in list_html

    def test_beneficiary_badge_in_grid_derived_from_completeness_documents_and_eligibility(
        self, staff_client, cycle, available_plot
    ):
        # 1. Create an application where eligibility passes, but required documents are missing -> ΕΚΚΡΕΜΕΙ
        incomplete_data = _post_data(
            cycle,
            **{
                "main-attached_documents": ["A1", "B1", "B11", "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6"],
            },
        )
        resp = staff_client.post(reverse("plot_applications:create"), incomplete_data)
        assert resp.status_code == 302
        application = PlotApplication.objects.get()
        assert application.eligibility_result == "pass"
        assert application.documents_completeness == "incomplete"
        assert application.completeness_result == "incomplete"
        assert application.beneficiary_status == "pending"
        assert application.is_beneficiary is False
        assert application.beneficiary_label == "ΕΚΚΡΕΜΕΙ"

        list_html = staff_client.get(reverse("plot_applications:list")).content.decode()
        list_tbody = list_html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        assert "<th>Δικαιούχος</th>" in list_html
        assert "ΕΚΚΡΕΜΕΙ" in list_tbody
        assert "badge--pending" in list_tbody

        # Filter by beneficiary=pending includes it; pass and fail exclude it
        list_pending = staff_client.get(reverse("plot_applications:list"), {"beneficiary": "pending"})
        assert application in list_pending.context["applications"]
        list_pass = staff_client.get(reverse("plot_applications:list"), {"beneficiary": "pass"})
        assert application not in list_pass.context["applications"]
        list_fail = staff_client.get(reverse("plot_applications:list"), {"beneficiary": "fail"})
        assert application not in list_fail.context["applications"]

        # 2. If eligibility is ΔΕΝ ΠΛΗΡΟΙ (fail), then beneficiary column is ΜΗ ΔΙΚΑΙΟΥΧΟΣ
        fail_data = _post_data(cycle, **{"main-has_dwelling": "True"})
        resp_fail = staff_client.post(
            reverse("plot_applications:edit", args=[application.pk]), fail_data
        )
        assert resp_fail.status_code == 302
        application.refresh_from_db()
        assert application.eligibility_result == "fail"
        assert application.beneficiary_status == "fail"
        assert application.is_beneficiary is False
        assert application.beneficiary_label == "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"

        list_html_fail = staff_client.get(reverse("plot_applications:list")).content.decode()
        list_tbody_fail = list_html_fail.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        assert "ΜΗ ΔΙΚΑΙΟΥΧΟΣ" in list_tbody_fail
        assert application in staff_client.get(
            reverse("plot_applications:list"), {"beneficiary": "fail"}
        ).context["applications"]

        # 3. Once all 3 (Πληρότητα αίτησης, Δικαιολογητικά, Επιλεξιμότητα) are satisfied -> ΔΙΚΑΙΟΥΧΟΣ
        complete_data = _post_data(cycle)
        resp2 = staff_client.post(
            reverse("plot_applications:edit", args=[application.pk]), complete_data
        )
        assert resp2.status_code == 302
        application.refresh_from_db()
        assert application.completeness_result == "complete"
        assert application.documents_completeness == "complete"
        assert application.eligibility_result == "pass"
        assert application.beneficiary_status == "pass"
        assert application.is_beneficiary is True
        assert application.beneficiary_label == "ΔΙΚΑΙΟΥΧΟΣ"

        list_html_after = staff_client.get(reverse("plot_applications:list")).content.decode()
        list_tbody_after = list_html_after.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        assert "ΔΙΚΑΙΟΥΧΟΣ" in list_tbody_after
        assert "ΜΗ ΔΙΚΑΙΟΥΧΟΣ" not in list_tbody_after
        assert "ΕΚΚΡΕΜΕΙ" not in list_tbody_after

        detail_html_after = staff_client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert "ΔΙΚΑΙΟΥΧΟΣ" in detail_html_after

        person_html = staff_client.get(
            reverse("persons:detail", args=[application.applicant_id])
        ).content.decode()
        assert "<th>Δικαιούχος</th>" in person_html
        assert "ΔΙΚΑΙΟΥΧΟΣ" in person_html

        list_pass_after = staff_client.get(reverse("plot_applications:list"), {"beneficiary": "pass"})
        assert application in list_pass_after.context["applications"]
        list_fail_after = staff_client.get(reverse("plot_applications:list"), {"beneficiary": "fail"})
        assert application not in list_fail_after.context["applications"]
        list_pending_after = staff_client.get(reverse("plot_applications:list"), {"beneficiary": "pending"})
        assert application not in list_pending_after.context["applications"]

    def test_eligibility_report_pdf_export_and_permissions(
        self, client, staff_client, make_user, cycle, available_plot
    ):
        from django.template.loader import render_to_string

        from core.models import Role
        from plot_applications.eligibility_report_pdf import (
            REPORT_TITLE,
            eligibility_report_context,
        )

        # 1. Create an application with some passing and some failing criteria
        fail_data = _post_data(
            cycle,
            **{
                "main-has_dwelling": "True",
                "main-has_dwelling_details": "Κατοικία στη Λευκωσία",
                "main-spouse_signed": "",
            },
        )
        resp = staff_client.post(reverse("plot_applications:create"), fail_data)
        assert resp.status_code == 302
        application = PlotApplication.objects.get()

        pdf_url = reverse("plot_applications:eligibility_report_pdf", args=[application.pk])
        detail_html = staff_client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert f'href="{pdf_url}"' in detail_html
        assert "Εξαγωγή PDF ελέγχου κριτηρίων" in detail_html

        context = eligibility_report_context(application)
        assert context["report_title"] == REPORT_TITLE
        # Every criterion in both groups has a non-empty reason/note
        for criterion in context["outcome"]["criteria"]:
            assert criterion.note.strip(), f"Empty note for {criterion.code}"

        report_html = render_to_string("plot_applications/pdf/eligibility_report.html", context)
        assert "ΚΥΠΡΙΑΚΗ ΔΗΜΟΚΡΑΤΙΑ" in report_html
        assert "ΥΠΟΥΡΓΕΙΟ ΕΣΩΤΕΡΙΚΩΝ" in report_html
        assert "ΕΠΑΡΧΙΑΚΗ ΔΙΟΙΚΗΣΗ" in report_html
        assert REPORT_TITLE in report_html
        assert application.protocol_number in report_html
        assert application.community.name in report_html
        assert "1. Κριτήρια πληρότητας αίτησης" in report_html
        assert "2. Κριτήρια επιλεξιμότητας δικαιούχου" in report_html
        assert "badge--pass" in report_html
        assert "badge--fail" in report_html
        assert "ΠΛΗΡΟΥΤΑΙ" in report_html
        assert "ΔΕΝ ΠΛΗΡΟΥΤΑΙ" in report_html
        assert "ΜΗ ΔΙΚΑΙΟΥΧΟΣ" in report_html
        assert "Ζεύγος: η αίτηση πρέπει να υπογράφεται και από τα δύο πρόσωπα" in report_html
        assert "Δηλώθηκε εγγεγραμμένη κατοικία. (Κατοικία στη Λευκωσία)" in report_html

        pdf_resp = staff_client.get(pdf_url)
        assert pdf_resp.status_code == 200
        assert pdf_resp["Content-Type"] == "application/pdf"
        assert pdf_resp.content.startswith(b"%PDF")
        assert "elegchos_kritirion_" in pdf_resp["Content-Disposition"]

        # 2. User without plot_app_eligibility:view cannot see the button or download the PDF
        no_elig_role = Role.objects.create(
            name="Χωρίς Έλεγχο Κριτηρίων",
            grants=["plot_applications:view", "plot_app_basic:view"],
        )
        restricted_user = make_user("restricted_elig_pdf")
        no_elig_role.members.add(restricted_user)
        client.force_login(restricted_user)

        restricted_detail = client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert f'href="{pdf_url}"' not in restricted_detail
        assert client.get(pdf_url).status_code == 403

    def test_application_stages_and_plot_allocation_status(
        self, staff_client, cycle, available_plot
    ):
        from allocation.models import Allocation, RankingEntry, RankingList
        from plot_applications.models import ApplicationStage, PlotAllocationStatus

        # 1. Stage 1 — Συλλογή πληροφοριών και πιστοποιητικών (missing required document C1)
        incomplete_data = _post_data(
            cycle,
            **{
                "main-attached_documents": ["A1", "B1", "B11", "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6"],
            },
        )
        resp = staff_client.post(reverse("plot_applications:create"), incomplete_data)
        assert resp.status_code == 302
        application = PlotApplication.objects.get()
        assert application.application_stage == ApplicationStage.COLLECTION
        assert application.get_application_stage_display() == "Συλλογή πληροφοριών και πιστοποιητικών"
        assert application.plot_allocation_status == PlotAllocationStatus.PENDING
        assert application.get_plot_allocation_status_display() == "Εκκρεμεί"

        list_collection = staff_client.get(
            reverse("plot_applications:list"),
            {"stage": ApplicationStage.COLLECTION, "plot_allocation": PlotAllocationStatus.PENDING},
        )
        assert application in list_collection.context["applications"]

        # 2. Stage 2 — Εξέταση επιλεξιμότητας (complete fields & documents, but eligibility pending:
        #    e.g., Displaced category with all documents attached including A2, but missing refugee ID number)
        exam_data = _post_data(
            cycle,
            **{
                "main-residence_category": "displaced",
                "main-attached_documents": [
                    "A1", "A2", "B1", "B11", "C1", "D1", "D2", "D3", "D4", "D5", "E1", "E4", "E6"
                ],
                "applicant_party-refugee_identity_number": "",
            },
        )
        resp_exam = staff_client.post(
            reverse("plot_applications:edit", args=[application.pk]), exam_data
        )
        assert resp_exam.status_code == 302
        application.refresh_from_db()
        assert application.completeness_result == "complete"
        assert application.documents_completeness == "complete"
        assert application.eligibility_result == "pending"
        assert application.application_stage == ApplicationStage.EXAMINATION
        assert application.get_application_stage_display() == "Εξέταση επιλεξιμότητας"
        assert application.plot_allocation_status == PlotAllocationStatus.PENDING

        list_exam = staff_client.get(
            reverse("plot_applications:list"), {"stage": ApplicationStage.EXAMINATION}
        )
        assert application in list_exam.context["applications"]

        # 3. ΜΗ ΔΙΚΑΙΟΥΧΟΣ: remains open in stage 3 (shown in the prioritization list) until
        #    the community's list is finalized — Επιλογή και προτεραιοποίηση & Εκκρεμεί
        fail_data = _post_data(cycle, **{"main-has_dwelling": "True"})
        resp_fail = staff_client.post(
            reverse("plot_applications:edit", args=[application.pk]), fail_data
        )
        assert resp_fail.status_code == 302
        application.refresh_from_db()
        assert application.beneficiary_status == "fail"
        assert application.application_stage == ApplicationStage.PRIORITIZATION
        assert application.plot_allocation_status == PlotAllocationStatus.PENDING

        # 4. Stage 3 for ΔΙΚΑΙΟΥΧΟΣ before prioritization — Επιλογή και προτεραιοποίηση & Εκκρεμεί
        pass_data = _post_data(cycle)
        resp_pass = staff_client.post(
            reverse("plot_applications:edit", args=[application.pk]), pass_data
        )
        assert resp_pass.status_code == 302
        application.refresh_from_db()
        assert application.beneficiary_status == "pass"
        assert application.application_stage == ApplicationStage.PRIORITIZATION
        assert application.get_application_stage_display() == "Επιλογή και προτεραιοποίηση"
        assert application.plot_allocation_status == PlotAllocationStatus.PENDING
        assert application.get_plot_allocation_status_display() == "Εκκρεμεί"

        detail_html = staff_client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert "Επιλογή και προτεραιοποίηση" in detail_html
        assert 'data-stage-step="prioritization"' in detail_html

        # 5. Stage 4 after prioritization completes without plot (final RankingList as ALTERNATE)
        ranking_list = RankingList.objects.create(
            community=application.community,
            submission_cycle=cycle,
            list_type=RankingList.ListType.FINAL,
            finalized_at=timezone.now(),
        )
        entry = RankingEntry.objects.create(
            ranking_list=ranking_list,
            application=application,
            finalized_rank=5,
            status=RankingEntry.Status.ALTERNATE,
        )
        application.refresh_from_db()
        assert application.application_stage == ApplicationStage.COMPLETED
        assert application.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED
        assert application.get_plot_allocation_status_display() == "Δεν πήρε οικόπεδο"

        list_not_alloc = staff_client.get(
            reverse("plot_applications:list"),
            {"stage": ApplicationStage.COMPLETED, "plot_allocation": PlotAllocationStatus.NOT_ALLOCATED},
        )
        assert application in list_not_alloc.context["applications"]

        # 6. Stage 4 after receiving a plot (active Allocation -> Πήρε οικόπεδο)
        entry.status = RankingEntry.Status.ELIGIBLE
        entry.save()
        Allocation.objects.create(application=application, parcel=available_plot)
        application.refresh_from_db()
        assert application.application_stage == ApplicationStage.COMPLETED
        assert application.plot_allocation_status == PlotAllocationStatus.ALLOCATED
        assert application.get_plot_allocation_status_display() == "Πήρε οικόπεδο"

        list_alloc = staff_client.get(
            reverse("plot_applications:list"),
            {"stage": ApplicationStage.COMPLETED, "plot_allocation": PlotAllocationStatus.ALLOCATED},
        )
        assert application in list_alloc.context["applications"]
        list_html = list_alloc.content.decode()
        assert "<th>Στάδιο αίτησης</th>" in list_html
        assert "<th>Παραχώρηση οικοπέδου</th>" in list_html
        assert "Πήρε οικόπεδο" in list_html

        person_html = staff_client.get(
            reverse("persons:detail", args=[application.applicant_id])
        ).content.decode()
        assert "<th>Στάδιο αίτησης</th>" in person_html
        assert "<th>Παραχώρηση οικοπέδου</th>" in person_html
        assert "Πήρε οικόπεδο" in person_html









