from datetime import date
from decimal import Decimal

from applications.models import Application, EligibilityCheck


def age_at(reference_date: date, born_on: date) -> int:
    years = reference_date.year - born_on.year
    if (reference_date.month, reference_date.day) < (born_on.month, born_on.day):
        years -= 1
    return years


def _income_limit(family_members_count: int) -> Decimal:
    if family_members_count <= 2:
        return Decimal("45000")
    if family_members_count == 3:
        return Decimal("50000")
    if family_members_count == 4:
        return Decimal("55000")
    return Decimal("65000")


def evaluate_eligibility(application: Application):
    person2_exists = application.person2_id is not None
    p1_age = age_at(application.submitted_on, application.person.date_of_birth)
    p2_age = (
        age_at(application.submitted_on, application.person2.date_of_birth)
        if person2_exists and application.person2
        else None
    )

    results = {}
    # 10.4.1 Citizenship
    citizenship_pass = application.person.citizenship_cypriot or bool(
        person2_exists and application.person2 and application.person2.citizenship_cypriot
    )
    results[EligibilityCheck.Criterion.CITIZENSHIP] = (
        EligibilityCheck.Result.PASS if citizenship_pass else EligibilityCheck.Result.FAIL
    )
    # 10.4.2 Age
    age_pass = p1_age < 45 or bool(person2_exists and p2_age is not None and p2_age < 45)
    results[EligibilityCheck.Criterion.AGE] = (
        EligibilityCheck.Result.PASS if age_pass else EligibilityCheck.Result.FAIL
    )
    # 10.4.3 Residence (minimum data-driven pass/fail for M1)
    residence_pass = bool(application.residence_category.strip())
    results[EligibilityCheck.Criterion.RESIDENCE] = (
        EligibilityCheck.Result.PASS if residence_pass else EligibilityCheck.Result.PENDING
    )
    # 10.4.4 Property
    property_pass = not application.person1_has_property and not (
        person2_exists and application.person2_has_property
    )
    results[EligibilityCheck.Criterion.PROPERTY] = (
        EligibilityCheck.Result.PASS if property_pass else EligibilityCheck.Result.FAIL
    )
    # 10.4.5 Non alienation
    alienation_pass = application.person1_non_alienation_clear and (
        (not person2_exists) or application.person2_non_alienation_clear
    )
    results[EligibilityCheck.Criterion.NON_ALIENATION] = (
        EligibilityCheck.Result.PASS if alienation_pass else EligibilityCheck.Result.FAIL
    )
    # 10.4.6 Income
    income_total = (
        application.person1_income + application.person2_income + application.children_income
    )
    income_limit = _income_limit(application.family_members_count)
    income_pass = income_total <= income_limit
    results[EligibilityCheck.Criterion.INCOME] = (
        EligibilityCheck.Result.PASS if income_pass else EligibilityCheck.Result.FAIL
    )
    # 10.4.7 Previous aid
    aid_pass = application.person1_previous_aid_clear and (
        (not person2_exists) or application.person2_previous_aid_clear
    )
    results[EligibilityCheck.Criterion.PREVIOUS_AID] = (
        EligibilityCheck.Result.PASS if aid_pass else EligibilityCheck.Result.FAIL
    )

    pending_exists = any(value == EligibilityCheck.Result.PENDING for value in results.values())
    fail_exists = any(value == EligibilityCheck.Result.FAIL for value in results.values())
    if fail_exists:
        application.outcome_104 = Application.Outcome104.FAIL
    elif pending_exists:
        application.outcome_104 = Application.Outcome104.PENDING
    else:
        application.outcome_104 = Application.Outcome104.PASS

    return results, p1_age, p2_age, income_total, income_limit
