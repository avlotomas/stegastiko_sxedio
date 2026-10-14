"""Αυτόματος έλεγχος της Αίτησης Παραρτήματος 3 έναντι του Σχεδίου.

Κάθε κριτήριο αναφέρει την Ενότητα του Σχεδίου. Οι αριθμητικές παράμετροι διαβάζονται από
τις Ρυθμίσεις (SystemSetting), γιατί το ΥΠΕΣ μπορεί να τροποποιήσει το Σχέδιο (Ενότ. 19).
Το αποτέλεσμα είναι «κατ' αρχήν»: την τελική κρίση την κάνει η Επιτροπή Εξέτασης Αιτήσεων (Ενότ. 6).
"""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from applications.rules import age_at, income_limit_setting
from core.services import get_setting
from plot_applications.models import (
    ApplicationChild,
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
    ("plotApp.maxNeighbourKm", 15, "Ενότ. 10.Γ — μέγιστη απόσταση γειτονικής κοινότητας (km)"),
    ("plotApp.minorMaxAge", 18, "Ενότ. 10.Α — ανήλικα τέκνα (ηλικία μικρότερη από)"),
    ("plotApp.studentMaxAgeFemale", 23, "Ενότ. 10.Α — σπουδάζοντα τέκνα θήλυ μέχρι (ετών)"),
    ("plotApp.studentMaxAgeMale", 25, "Ενότ. 10.Α — σπουδάζοντα τέκνα άρρενα μέχρι (ετών)"),
    ("plotApp.repatriatedAbroadYears", 10, "Ενότ. 11.IV — ελάχιστα έτη παραμονής στο εξωτερικό"),
    ("plotApp.repatriatedResidenceYears", 3, "Ενότ. 11.IV — ελάχιστα έτη διαμονής στην Κοινότητα"),
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
    age: int
    recognized: bool | None  # None = δεν κρίνεται ακόμη (λείπει στοιχείο)
    note: str = ""


def years_between(start: date, end: date) -> int:
    return age_at(end, start)


def assess_child(child: ApplicationChild, on: date) -> ChildAssessment:
    """Αν το τέκνο εμπίπτει στον ορισμό «Τέκνα» της Ενότ. 10.Α κατά την υποβολή."""
    age = age_at(on, child.date_of_birth)
    status = child.status
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
    on = application.submitted_on
    if category == ResidenceCategory.DISPLACED:
        if not (applicant_party and applicant_party.refugee_identity_number):
            return PENDING, "Εκτοπισθείς χωρίς Αρ. Προσφυγικής Ταυτότητας."
        return PASS, ""
    if category == ResidenceCategory.INTERNAL_EMIGRANT:
        missing = []
        if not application.origin_parent_description.strip():
            missing.append("καταγωγή ως προς γονέα")
        if not (application.previous_residence_from and application.previous_residence_to):
            missing.append("περίοδος μόνιμης κατοίκησης")
        if missing:
            return PENDING, "Λείπουν: " + ", ".join(missing) + "."
        return PASS, ""
    if category == ResidenceCategory.REPATRIATED:
        if not (application.abroad_from and application.abroad_to and application.community_residence_since):
            return PENDING, "Λείπουν οι περίοδοι παραμονής στο εξωτερικό / διαμονής στην Κοινότητα."
        abroad_years = years_between(application.abroad_from, application.abroad_to)
        residence_years = years_between(application.community_residence_since, on)
        need_abroad = parameter("plotApp.repatriatedAbroadYears")
        need_residence = parameter("plotApp.repatriatedResidenceYears")
        problems = []
        if abroad_years < need_abroad:
            problems.append(f"παραμονή στο εξωτερικό {abroad_years} έτη (< {need_abroad})")
        if residence_years < need_residence:
            problems.append(f"διαμονή στην Κοινότητα {residence_years} έτη (< {need_residence})")
        if problems:
            return FAIL, "Επαναπατρισθείς: " + "; ".join(problems) + "."
        return PASS, ""
    return PASS, ""


def _residence_criterion(application: PlotApplication, applicant_party) -> CriterionResult:
    code, label, section = "residence", "Κριτήριο διαμονής", "10.Γ, 11"
    category = application.residence_category
    if not category:
        return CriterionResult(code, label, section, PENDING, "Δεν δηλώθηκε κατηγορία διαμονής.")
    if category == ResidenceCategory.NEIGHBOURING:
        max_km = parameter("plotApp.maxNeighbourKm")
        distance = application.neighbouring_distance_km
        if not application.residence_community.strip():
            return CriterionResult(code, label, section, PENDING, "Δεν δηλώθηκε η Γειτονική Κοινότητα.")
        if distance is None:
            return CriterionResult(
                code, label, section, PENDING, "Εκκρεμεί η απόσταση κατά τις μετρήσεις ΤΚΧ."
            )
        if distance > max_km:
            return CriterionResult(
                code, label, section, FAIL, f"Απόσταση {distance} km > {max_km} km — απορρίπτεται."
            )
        sub = application.neighbouring_subcategory
        if not sub:
            return CriterionResult(
                code, label, section, PENDING, "Δεν δηλώθηκε η ιδιότητα σε σχέση με τη Γειτονική Κοινότητα."
            )
        result, note = _residence_detail_check(sub, application, applicant_party)
        return CriterionResult(code, label, section, result, note)
    result, note = _residence_detail_check(category, application, applicant_party)
    return CriterionResult(code, label, section, result, note)


PRIMARY_ORDER = {
    ResidenceCategory.AUTOCHTHON: 1,
    ResidenceCategory.DISPLACED: 2,
    ResidenceCategory.INTERNAL_EMIGRANT: 3,
    ResidenceCategory.REPATRIATED: 4,
}


def priority(application: PlotApplication, recognized_children: int) -> tuple[int | None, int | None, str]:
    """Ενότ. 11: πρωτεύουσα σειρά κατά τόπο διαμονής, δευτερεύουσα κατά σύνθεση οικογένειας.

    Οι Κάτοικοι Γειτονικής Κοινότητας έπονται (5x), με την ίδια σειρά 1–4 κατ' αναλογία (51–54).
    """
    category = application.residence_category
    if not category:
        return None, None, ""
    labels = dict(ResidenceCategory.choices)
    if category == ResidenceCategory.NEIGHBOURING:
        sub = application.neighbouring_subcategory
        primary = 50 + PRIMARY_ORDER.get(sub, 9)
        primary_label = labels[category] + (f" — {labels[sub]}" if sub else "")
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
    criteria.append(
        CriterionResult(
            "citizenship", "Κυπριακή υπηκοότητα", "10", PASS if cypriot else FAIL,
            "" if cypriot else "Κανένα πρόσωπο δεν είναι Κύπριος πολίτης.",
        )
    )

    # Ενότ. 10.Α — Οικογενειακή κατάσταση και Τέκνα
    children = [assess_child(child, on) for child in application.children.all()]
    recognized = sum(1 for item in children if item.recognized)
    undecided = any(item.recognized is None for item in children)
    if application.is_couple:
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
    ages = [age_at(on, application.applicant.date_of_birth)]
    if has_spouse:
        ages.append(age_at(on, application.spouse.date_of_birth))
    age_ok = any(age < max_age for age in ages)
    criteria.append(
        CriterionResult(
            "age", "Ηλικία", "10.Β", PASS if age_ok else FAIL,
            "Ηλικίες κατά την υποβολή: " + ", ".join(str(a) for a in ages)
            + ("" if age_ok else f" — κανένα πρόσωπο κάτω των {max_age}."),
        )
    )

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
    members = 1 + (1 if has_spouse else 0) + recognized
    total = sum((income.total for income in application.incomes.all()), Decimal("0"))
    limit = _income_limit(members)
    income_ok = total <= limit
    criteria.append(
        CriterionResult(
            "income", "Οικογενειακό ακαθάριστο εισόδημα", "10.Στ", PASS if income_ok else FAIL,
            f"Σύνολο € {_money(total)} — όριο € {_money(limit)} για {members} μέλη.",
        )
    )

    # Ενότ. 20.3 — προηγούμενη κρατική στεγαστική ενίσχυση
    criteria.append(
        _yes_no_criterion("previous_aid", "Προηγούμενη κρατική στεγαστική ενίσχυση", "20.3",
                          application.previous_housing_aid,
                          "Δηλώθηκε προηγούμενη ενίσχυση (εξαιρούνται μόνο επιδότηση ενοικίου/επιτοκίου).",
                          "Δηλώθηκε «Όχι» (και στην Ένορκη Δήλωση).")
    )

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
