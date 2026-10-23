"""Αυτόματος έλεγχος της Αίτησης Παραρτήματος 3 έναντι του Σχεδίου.

Κάθε κριτήριο αναφέρει την Ενότητα του Σχεδίου. Οι αριθμητικές παράμετροι διαβάζονται από
τις Ρυθμίσεις (SystemSetting), γιατί το ΥΠΕΣ μπορεί να τροποποιήσει το Σχέδιο (Ενότ. 19).
Το αποτέλεσμα είναι «κατ' αρχήν»: την τελική κρίση την κάνει η Επιτροπή Εξέτασης Αιτήσεων (Ενότ. 6).
"""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from plot_applications.parameters import age_at, income_limit_setting
from core.services import get_setting
from plot_applications.documents import DOCUMENT_LABELS
from plot_applications.models import (
    ApplicationChild,
    ApplicationParty,
    IncomeDeclaration,
    EligibilityResult,
    PlotApplication,
    ResidenceCategory,
)

PASS = EligibilityResult.PASS
FAIL = EligibilityResult.FAIL
PENDING = EligibilityResult.PENDING

# (setting key, default, description) — όλα επεξεργάσιμα από Ρυθμίσεις (Ενότ. 19).
PARAMETER_SETTINGS: tuple[tuple[str, int, str], ...] = (
    ("plotApp.maxAge", 45, "Ενότ. 10.Β — ηλικία που δεν πρέπει να έχει συμπληρωθεί"),
    ("plotApp.minorMaxAge", 18, "Ενότ. 10.Α — ανήλικα τέκνα (ηλικία μικρότερη από)"),
    ("plotApp.studentMaxAgeFemale", 23, "Ενότ. 10.Α — σπουδάζοντα τέκνα θήλυ μέχρι (ετών)"),
    ("plotApp.studentMaxAgeMale", 25, "Ενότ. 10.Α — σπουδάζοντα τέκνα άρρενα μέχρι (ετών)"),
    ("plotApp.largeFamilyChildren", 4, "Ενότ. 11 — ελάχιστος αριθμός τέκνων πολύτεκνης"),
)
PARAMETER_DEFAULTS = {key: default for key, default, _ in PARAMETER_SETTINGS}


def parameter(key: str) -> int:
    default = PARAMETER_DEFAULTS[key]
    try:
        value = int(str(get_setting(key, str(default))).strip())
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass
class CriterionResult:
    code: str
    label: str
    section: str
    result: str
    note: str = ""


@dataclass
class ChildAssessment:
    child: ApplicationChild
    age: int | None
    recognized: bool | None  # None = δεν κρίνεται ακόμη (λείπει στοιχείο)
    note: str = ""


def assess_child(child: ApplicationChild, on: date | None) -> ChildAssessment:
    """Αν το τέκνο εμπίπτει στον ορισμό «Τέκνα» της Ενότ. 10.Α κατά την υποβολή."""
    status = child.status
    if on is None or child.date_of_birth is None:
        if status == ApplicationChild.Status.NATIONAL_GUARD:
            return ChildAssessment(child, None, True)
        return ChildAssessment(child, None, None, "Δεν δηλώθηκε ημερομηνία υποβολής ή γέννησης.")
    age = age_at(on, child.date_of_birth)
    if status == ApplicationChild.Status.MINOR:
        limit = parameter("plotApp.minorMaxAge")
        if age < limit:
            return ChildAssessment(child, age, True)
        return ChildAssessment(child, age, False, f"Ηλικία {age}: δεν είναι ανήλικο.")
    if status == ApplicationChild.Status.STUDENT:
        if not child.sex:
            return ChildAssessment(child, age, None, "Δεν δηλώθηκε φύλο (όριο 23 θήλυ / 25 άρρεν).")
        key = "plotApp.studentMaxAgeFemale" if child.sex == "F" else "plotApp.studentMaxAgeMale"
        limit = parameter(key)
        if age <= limit:
            return ChildAssessment(child, age, True)
        return ChildAssessment(child, age, False, f"Ηλικία {age}: υπερβαίνει το όριο {limit} για φοιτητές.")
    if status == ApplicationChild.Status.ADULT_DISABILITY:
        if age < parameter("plotApp.minorMaxAge"):
            return ChildAssessment(child, age, True, "Ανήλικο — λογίζεται ως ανήλικο τέκνο.")
        return ChildAssessment(child, age, True)
    return ChildAssessment(child, age, True)  # Εθνοφρουρός


def _income_limit(members: int) -> Decimal:
    if members <= 2:
        key = "incomeLimitUpTo2Members"
    elif members == 3:
        key = "incomeLimit3Members"
    elif members == 4:
        key = "incomeLimit4Members"
    else:
        key = "incomeLimit5PlusMembers"
    return income_limit_setting(key)


def income_tier_label(members: int) -> str:
    if members <= 2:
        return "Ζεύγος και Μονογονεϊκή οικογένεια (έως 2 μέλη)"
    if members == 3:
        return "Οικογένεια 3 ατόμων"
    if members == 4:
        return "Οικογένεια 4 ατόμων"
    return f"Οικογένεια 5+ ατόμων ({members} μέλη)"


def income_evaluation_parameters() -> dict:
    return {
        "limits": {
            "2": str(_income_limit(2)),
            "3": str(_income_limit(3)),
            "4": str(_income_limit(4)),
            "5": str(_income_limit(5)),
        },
        "minor_max_age": parameter("plotApp.minorMaxAge"),
        "student_max_age_female": parameter("plotApp.studentMaxAgeFemale"),
        "student_max_age_male": parameter("plotApp.studentMaxAgeMale"),
        "large_family_children": parameter("plotApp.largeFamilyChildren"),
    }


def _money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _yes_no_criterion(
    code, label, section, answer, fail_note, pass_note="Δηλώθηκε «Όχι» — ελέγχεται με τα πιστοποιητικά ΤΚΧ."
) -> CriterionResult:
    if answer is None:
        return CriterionResult(code, label, section, PENDING, "Δεν δόθηκε απάντηση Ναι/Όχι.")
    if answer:
        return CriterionResult(code, label, section, FAIL, fail_note)
    return CriterionResult(code, label, section, PASS, pass_note)


def _residence_detail_check(category, application: PlotApplication, applicant_party) -> tuple[str, str]:
    """Έλεγχος στοιχείων κατηγορίας διαμονής (Ενότ. 11) — κοινός για (Α)–(Γ) και (Δ) κατ' αναλογία."""
    if category == ResidenceCategory.DISPLACED:
        if not (applicant_party and applicant_party.refugee_identity_number):
            return PENDING, "Εκτοπισθείς χωρίς Αρ. Προσφυγικής Ταυτότητας."
        return PASS, ""
    if category == ResidenceCategory.INTERNAL_EMIGRANT:
        if not application.origin_parent_description.strip():
            return PENDING, "Λείπουν: καταγωγή ως προς γονέα."
        return PASS, ""
    return PASS, ""


def _residence_criterion(application: PlotApplication, applicant_party) -> CriterionResult:
    code, label, section = "residence", "Κριτήριο διαμονής", "10.Γ, 11"
    category = application.residence_category
    if not category:
        return CriterionResult(code, label, section, PENDING, "Δεν δηλώθηκε κατηγορία διαμονής.")
    if category == ResidenceCategory.NEIGHBOURING:
        # Δεν γίνεται έλεγχος απόστασης (15 km)· η Γειτονική Κοινότητα δηλώνεται ως ελεύθερο κείμενο.
        if not application.residence_community.strip():
            return CriterionResult(code, label, section, PENDING, "Δεν δηλώθηκε η Γειτονική Κοινότητα.")
        return CriterionResult(
            code, label, section, PASS, "Κάτοικος Γειτονικής Κοινότητας — δεν ελέγχεται η απόσταση."
        )
    result, note = _residence_detail_check(category, application, applicant_party)
    return CriterionResult(code, label, section, result, note)


def required_documents(application: PlotApplication) -> list[tuple[tuple[str, ...], str]]:
    """Δικαιολογητικά που απαιτούνται για την αίτηση (Ενότ. 5, 10, 20.2).

    Κάθε στοιχείο είναι (κωδικοί που ικανοποιούν την απαίτηση — αρκεί ένας, περιγραφή).
    """
    required: list[tuple[tuple[str, ...], str]] = []

    def need(*codes: str):
        required.append((codes, DOCUMENT_LABELS[codes[0]]))

    category = application.residence_category
    applicant_party = application.applicant_party
    has_spouse = application.is_couple and application.spouse_id is not None
    need("A1")
    if category == ResidenceCategory.DISPLACED or (applicant_party and applicant_party.refugee_identity_number):
        need("A2")
    if application.is_couple:
        required.append((("B1", "B2"), DOCUMENT_LABELS["B1"]))
    children = list(application.children.all())
    if children:
        need("B11")
    statuses = {child.status for child in children}
    if ApplicationChild.Status.STUDENT in statuses:
        need("B12")
    if ApplicationChild.Status.NATIONAL_GUARD in statuses:
        need("B13")
    if ApplicationChild.Status.ADULT_DISABILITY in statuses:
        need("B14")
    if any(party.has_disability for party in application.parties.all()):
        need("B10")
    # Ενότ. 10.Γ — λογαριασμός ΑΗΚ και βεβαίωση Κοινότητας ταυτόχρονα με την αίτηση
    if category == ResidenceCategory.NEIGHBOURING:
        need("C9")
        need("C10")
    else:
        need("C1")
        need("C2")
    if category == ResidenceCategory.INTERNAL_EMIGRANT:
        need("C6")
    if category == ResidenceCategory.REPATRIATED:
        required.append((("C7", "A3"), DOCUMENT_LABELS["C7"]))
        need("C8")
    # Ενότ. 10.Δ, 10.Ε — πιστοποιητικά ΤΚΧ (όταν δεν δηλώθηκε «Ναι»)
    if application.has_dwelling is not True or application.has_residential_land is not True:
        need("D1")
        need("D2")
    if application.has_residential_land is not True:
        need("D3")
    if application.has_alienated_property is not True:
        need("D4")
        need("D5")
    # Ενότ. 10.Στ — αποδεικτικά εισοδήματος ανά μέλος που δηλώνει εισόδημα
    income_codes = {
        IncomeDeclaration.Member.APPLICANT: ("E1", "E2", "E3"),
        IncomeDeclaration.Member.SPOUSE: ("E4", "E5", "E6"),
        IncomeDeclaration.Member.CHILD: ("E7", "E8", "E9"),
        IncomeDeclaration.Member.OTHER: ("E7", "E8", "E9"),
    }
    needed_income_codes: set[str] = set()
    for income in application.incomes.all():
        employee, self_employed, other = income_codes.get(
            income.member, ("E7", "E8", "E9")
        )
        if income.member == IncomeDeclaration.Member.SPOUSE and not has_spouse:
            continue
        code_to_need = None
        if income.employment_type == IncomeDeclaration.EmploymentType.EMPLOYEE:
            code_to_need = employee
        elif income.employment_type == IncomeDeclaration.EmploymentType.SELF_EMPLOYED:
            code_to_need = self_employed
        elif income.employment_type == IncomeDeclaration.EmploymentType.OTHER_SOURCE:
            code_to_need = other
        if code_to_need and code_to_need not in needed_income_codes:
            needed_income_codes.add(code_to_need)
            need(code_to_need)
    return required


def _documents_criterion(application: PlotApplication) -> CriterionResult:
    attached = set(application.attached_documents or [])
    missing = [label for codes, label in required_documents(application) if not attached.intersection(codes)]
    if missing:
        return CriterionResult(
            "documents", "Δικαιολογητικά", "5, 20.2", FAIL,
            "Λείπουν δικαιολογητικά (η αίτηση που χρειάζεται συμπλήρωση απορρίπτεται): "
            + "; ".join(missing),
        )
    return CriterionResult("documents", "Δικαιολογητικά", "5, 20.2", PASS)


NEIGHBOURING_PRIORITY = 5
PRIMARY_ORDER = {
    ResidenceCategory.AUTOCHTHON: 1,
    ResidenceCategory.DISPLACED: 2,
    ResidenceCategory.INTERNAL_EMIGRANT: 3,
    ResidenceCategory.REPATRIATED: 4,
}


def priority(application: PlotApplication, recognized_children: int) -> tuple[int | None, int | None, str]:
    """Ενότ. 11: πρωτεύουσα σειρά κατά τόπο διαμονής, δευτερεύουσα κατά σύνθεση οικογένειας.

    Οι Κάτοικοι Γειτονικής Κοινότητας έπονται όλοι μαζί (5), χωρίς υποδιαίρεση ανά ιδιότητα.
    """
    category = application.residence_category
    if not category:
        return None, None, ""
    labels = dict(ResidenceCategory.choices)
    if category == ResidenceCategory.NEIGHBOURING:
        primary = NEIGHBOURING_PRIORITY
        primary_label = labels[category]
    else:
        primary = PRIMARY_ORDER[category]
        primary_label = labels[category]

    if recognized_children >= parameter("plotApp.largeFamilyChildren"):
        secondary, secondary_label = 1, "Πολύτεκνη οικογένεια"
    elif application.is_couple and recognized_children > 0:
        secondary, secondary_label = 2, "Οικογένεια μη πολύτεκνη"
    elif application.family_status == PlotApplication.FamilyStatus.SINGLE_PARENT:
        secondary, secondary_label = 3, "Μονογονεϊκή οικογένεια"
    else:
        secondary, secondary_label = 4, "Ζεύγος χωρίς τέκνα"
    return primary, secondary, f"{primary_label} · {secondary_label}"


def evaluate(application: PlotApplication) -> dict:
    """Υπολογίζει τα κριτήρια και τα παράγωγα πεδία της αίτησης (χωρίς αποθήκευση)."""
    on = application.submitted_on
    applicant_party = application.applicant_party
    spouse_party = application.spouse_party if application.is_couple else None
    has_spouse = application.is_couple and application.spouse_id is not None
    criteria: list[CriterionResult] = []

    # Ενότ. 5 — υπογραφή και από τα δύο πρόσωπα του Ζεύγους
    if application.is_couple:
        signed = application.applicant_signed and application.spouse_signed
        note = "" if signed else "Ζεύγος: η αίτηση πρέπει να υπογράφεται και από τα δύο πρόσωπα — απορρίπτεται."
    else:
        signed = application.applicant_signed
        note = "" if signed else "Η αίτηση δεν υπογράφηκε."
    criteria.append(CriterionResult("signatures", "Υπογραφές", "5", PASS if signed else FAIL, note))

    # Ενότ. 10 — Κύπριοι πολίτες (τουλάχιστον ένα πρόσωπο του Ζεύγους)
    cypriot = bool(applicant_party and applicant_party.is_cypriot) or bool(spouse_party and spouse_party.is_cypriot)
    has_declared_citizenship = bool(applicant_party and applicant_party.citizenship) or bool(
        spouse_party and spouse_party.citizenship
    )
    if cypriot:
        cit_result, cit_note = PASS, ""
    elif not has_declared_citizenship:
        cit_result, cit_note = PENDING, "Δεν δηλώθηκε υπηκοότητα."
    else:
        cit_result, cit_note = FAIL, "Κανένα πρόσωπο δεν είναι Κύπριος πολίτης."
    criteria.append(
        CriterionResult("citizenship", "Κυπριακή υπηκοότητα", "10", cit_result, cit_note)
    )

    # Ενότ. 10.Α — Οικογενειακή κατάσταση και Τέκνα
    children = [assess_child(child, on) for child in application.children.all()]
    recognized = sum(1 for item in children if item.recognized)
    undecided = any(item.recognized is None for item in children)
    if not application.family_status:
        family = (PENDING, "Δεν δηλώθηκε οικογενειακή κατάσταση.")
    elif application.is_couple:
        if has_spouse:
            family = (PASS, "")
        else:
            family = (FAIL, "Ζεύγος χωρίς στοιχεία συζύγου/συμβίου.")
    elif application.family_status == PlotApplication.FamilyStatus.SINGLE_PARENT:
        if recognized > 0:
            family = (PASS, "")
        elif undecided:
            family = (PENDING, "Δεν κρίνεται ακόμη αν υπάρχει τέκνο κατά την Ενότ. 10.Α.")
        else:
            family = (FAIL, "Μονογονεϊκή χωρίς τέκνο κατά την Ενότ. 10.Α — μονήρη άτομα δεν είναι δικαιούχοι.")
    else:
        family = (FAIL, "Μονήρη άτομα δεν είναι δικαιούχοι.")
    child_notes = [
        f"{item.child.first_name}: {item.note}" for item in children if item.note
    ]
    family_note = " ".join(filter(None, [family[1], *child_notes]))
    if family[0] == PASS and undecided:
        family = (PENDING, family[1])
    criteria.append(CriterionResult("family", "Οικογενειακή κατάσταση", "10.Α", family[0], family_note))

    # Ενότ. 10.Β — ηλικία (τουλάχιστον ένα πρόσωπο)
    max_age = parameter("plotApp.maxAge")
    persons_for_age = [application.applicant] + ([application.spouse] if has_spouse else [])
    ages = [
        age_at(on, person.date_of_birth)
        for person in persons_for_age
        if on is not None and person is not None and person.date_of_birth is not None
    ]
    missing_age_data = on is None or len(ages) < len(persons_for_age)
    age_ok = any(age < max_age for age in ages)
    if age_ok:
        age_result = PASS
        age_note = "Ηλικίες κατά την υποβολή: " + ", ".join(str(a) for a in ages)
    elif missing_age_data:
        age_result = PENDING
        age_note = "Δεν δηλώθηκε ημερομηνία υποβολής ή γέννησης."
    else:
        age_result = FAIL
        age_note = (
            "Ηλικίες κατά την υποβολή: "
            + ", ".join(str(a) for a in ages)
            + f" — κανένα πρόσωπο κάτω των {max_age}."
        )
    criteria.append(CriterionResult("age", "Ηλικία", "10.Β", age_result, age_note))

    # Ενότ. 10.Γ / 11 — διαμονή
    criteria.append(_residence_criterion(application, applicant_party))

    # Ενότ. 10.Δ — άλλη ακίνητη ιδιοκτησία (κάθε πρόσωπο χωριστά)
    criteria.append(
        _yes_no_criterion("dwelling", "Εγγεγραμμένη κατοικία", "10.Δ", application.has_dwelling,
                          "Δηλώθηκε εγγεγραμμένη κατοικία.")
    )
    criteria.append(
        _yes_no_criterion("land", "Οικόπεδο/τεμάχιο σε Οικιστική Ζώνη", "10.Δ", application.has_residential_land,
                          "Δηλώθηκε οικόπεδο/τεμάχιο σε περιοχή όπου επιτρέπεται κατοικία.")
    )
    # Ενότ. 10.Ε — μη αποξένωση
    criteria.append(
        _yes_no_criterion("alienation", "Μη αποξένωση (3 έτη)", "10.Ε", application.has_alienated_property,
                          "Δηλώθηκε αποξένωση ακινήτου εντός 3 ετών.")
    )

    # Ενότ. 10.Στ — εισόδημα
    adults = 2 if application.is_couple else 1
    members = adults + recognized
    total = sum((income.total for income in application.incomes.all()), Decimal("0"))
    limit = _income_limit(members)
    tier_label = income_tier_label(members)
    if not application.family_status:
        income_criterion = CriterionResult(
            "income",
            "Οικογενειακό ακαθάριστο εισόδημα",
            "10.Στ",
            PENDING,
            f"Σύνολο € {_money(total)} — δεν δηλώθηκε οικογενειακή κατάσταση για τον καθορισμό του ορίου εισοδήματος.",
        )
    else:
        income_ok = total <= limit
        income_criterion = CriterionResult(
            "income",
            "Οικογενειακό ακαθάριστο εισόδημα",
            "10.Στ",
            PASS if income_ok else FAIL,
            f"Σύνολο € {_money(total)} — όριο € {_money(limit)} για {members} μέλη ({tier_label}).",
        )
    criteria.append(income_criterion)

    # Ενότ. 20.3 — προηγούμενη κρατική στεγαστική ενίσχυση
    criteria.append(
        _yes_no_criterion("previous_aid", "Προηγούμενη κρατική στεγαστική ενίσχυση", "20.3",
                          application.previous_housing_aid,
                          "Δηλώθηκε προηγούμενη ενίσχυση (εξαιρούνται μόνο επιδότηση ενοικίου/επιτοκίου).",
                          "Δηλώθηκε «Όχι» (και στην Ένορκη Δήλωση).")
    )

    # Ενότ. 5, 20.2 — όλα τα δικαιολογητικά κατά την υποβολή
    criteria.append(_documents_criterion(application))

    results = {item.result for item in criteria}
    overall = FAIL if FAIL in results else PENDING if PENDING in results else PASS
    primary, secondary, priority_label = priority(application, recognized)
    return {
        "criteria": criteria,
        "children": children,
        "overall": overall,
        "children_count": len(children),
        "recognized_children_count": recognized,
        "family_members_count": members,
        "family_income_total": total,
        "income_limit": limit,
        "income_tier_label": tier_label,
        "income_criterion": income_criterion,
        "priority_primary": primary,
        "priority_secondary": secondary,
        "priority_label": priority_label,
    }


def apply_evaluation(application: PlotApplication) -> dict:
    """Υπολογίζει και αποθηκεύει τα παράγωγα πεδία της αίτησης."""
    outcome = evaluate(application)
    application.children_count = outcome["children_count"]
    application.recognized_children_count = outcome["recognized_children_count"]
    application.family_members_count = outcome["family_members_count"]
    application.family_income_total = outcome["family_income_total"]
    application.eligibility_result = outcome["overall"]
    application.eligibility_details = [asdict(item) for item in outcome["criteria"]]
    application.priority_primary = outcome["priority_primary"]
    application.priority_secondary = outcome["priority_secondary"]
    application.priority_label = outcome["priority_label"]
    application.save()
    return outcome
