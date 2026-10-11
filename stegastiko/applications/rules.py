from datetime import date
from decimal import Decimal, InvalidOperation

from applications.models import Application, EligibilityCheck
from core.services import get_setting


def age_at(reference_date: date, born_on: date) -> int:
    years = reference_date.year - born_on.year
    if (reference_date.month, reference_date.day) < (born_on.month, born_on.day):
        years -= 1
    return years


# 10.4.6 income limits (€) by family size; overridable via SystemSetting (Ρυθμίσεις).
INCOME_LIMIT_SETTINGS: tuple[tuple[str, Decimal, str], ...] = (
    ("incomeLimitUpTo2Members", Decimal("45000"), "Όριο εισοδήματος 10.4.6 — έως 2 μέλη (€)"),
    ("incomeLimit3Members", Decimal("50000"), "Όριο εισοδήματος 10.4.6 — 3 μέλη (€)"),
    ("incomeLimit4Members", Decimal("55000"), "Όριο εισοδήματος 10.4.6 — 4 μέλη (€)"),
    ("incomeLimit5PlusMembers", Decimal("65000"), "Όριο εισοδήματος 10.4.6 — 5 ή περισσότερα μέλη (€)"),
)
INCOME_LIMIT_DEFAULTS: dict[str, Decimal] = {key: default for key, default, _ in INCOME_LIMIT_SETTINGS}


def income_limit_setting(key: str) -> Decimal:
    """Configured limit for `key`; falls back to the default if unset or invalid."""
    default = INCOME_LIMIT_DEFAULTS[key]
    raw = get_setting(key, str(default))
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return default
    if not value.is_finite() or value <= 0:
        return default
    return value


def _income_limit(family_members_count: int) -> Decimal:
    if family_members_count <= 2:
        key = "incomeLimitUpTo2Members"
    elif family_members_count == 3:
        key = "incomeLimit3Members"
    elif family_members_count == 4:
        key = "incomeLimit4Members"
    else:
        key = "incomeLimit5PlusMembers"
    return income_limit_setting(key)


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
