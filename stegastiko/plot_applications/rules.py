"""Αυτόματος έλεγχος της Αίτησης Παραρτήματος 3 έναντι του Σχεδίου.

Κάθε αίτηση ελέγχεται σε δύο ανεξάρτητες ομάδες κριτηρίων:
1. Κριτήρια πληρότητας της αίτησης (υποχρεωτικά πεδία, υπογραφές, δικαιολογητικά με δυνατότητα
   χειροκίνητου χαρακτηρισμού ως ολοκληρωμένης + αιτιολογία — Ενότ. 5, 20.2).
2. Κριτήρια επιλεξιμότητας δικαιούχων (υπηκοότητα, οικογενειακή κατάσταση, ηλικία, διαμονή,
   κατοικία, οικόπεδο, μη αποξένωση, εισόδημα, προηγούμενη κρατική στεγαστική ενίσχυση —
   Ενότ. 10, 11, 20.3), τα οποία είναι ανεξάρτητα από την πληρότητα της αίτησης.

Κάθε κριτήριο αναφέρει την Ενότητα του Σχεδίου. Οι αριθμητικές παράμετροι διαβάζονται από
τις Ρυθμίσεις (SystemSetting), γιατί το ΥΠΕΣ μπορεί να τροποποιήσει το Σχέδιο (Ενότ. 19).
Το αποτέλεσμα είναι «κατ' αρχήν»: την τελική κρίση την κάνει η Επιτροπή Εξέτασης Αιτήσεων (Ενότ. 6).
"""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from core.services import get_setting
from plot_applications.documents import DOCUMENT_GROUPS, DOCUMENT_LABELS, applicable_documents
from plot_applications.models import (
    ApplicationChild,
    ApplicationCompleteness,
    ApplicationParty,
    ApplicationStage,
    DocumentsCompleteness,
    EligibilityOverride,
    EligibilityResult,
    IncomeDeclaration,
    PlotAllocationStatus,
    PlotApplication,
    ResidenceCategory,
)
from plot_applications.parameters import age_at, income_limit_setting
from plot_applications.stage_labels import get_application_stage_label

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
    code,
    label,
    section,
    answer,
    fail_note,
    pass_note="Δηλώθηκε «Όχι» — ελέγχεται με τα πιστοποιητικά ΤΚΧ.",
    details: str = "",
) -> CriterionResult:
    if answer is None:
        return CriterionResult(code, label, section, PENDING, "Δεν δόθηκε απάντηση Ναι/Όχι.")
    if answer:
        extra = (details or "").strip()
        note = f"{fail_note} ({extra})" if extra else fail_note
        return CriterionResult(code, label, section, FAIL, note)
    return CriterionResult(code, label, section, PASS, pass_note)


def _residence_detail_check(category, application: PlotApplication, applicant_party) -> tuple[str, str]:
    """Έλεγχος στοιχείων κατηγορίας διαμονής (Ενότ. 11) — κοινός για (Α)–(Γ) και (Δ) κατ' αναλογία."""
    cat_display = application.get_residence_category_display()
    if category == ResidenceCategory.DISPLACED:
        if not (applicant_party and applicant_party.refugee_identity_number):
            return PENDING, "Εκτοπισθείς χωρίς Αρ. Προσφυγικής Ταυτότητας."
        return PASS, f"{cat_display} (Αρ. Προσφυγικής Ταυτότητας: {applicant_party.refugee_identity_number})."
    if category == ResidenceCategory.INTERNAL_EMIGRANT:
        missing = []
        if not application.origin_parent_description.strip():
            missing.append("καταγωγή ως προς γονέα")
        if not application.resides_in_controlled_areas:
            missing.append("διαμονή σε ελεγχόμενες από την Κυπριακή Δημοκρατία περιοχές")
        if missing:
            return PENDING, "Λείπουν: " + ", ".join(missing) + "."
        return PASS, f"{cat_display} — δηλώθηκε καταγωγή γονέα και διαμονή σε ελεγχόμενες περιοχές."
    return PASS, f"{cat_display}."


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
    # Ενότ. 10.Γ — λογαριασμός ΑΗΚ (και για γειτονική κοινότητα βεβαίωση της Γειτονικής Κοινότητας)
    if category == ResidenceCategory.NEIGHBOURING:
        need("C9")
        need("C10")
    else:
        need("C1")
    if category == ResidenceCategory.INTERNAL_EMIGRANT:
        need("C6")
    if category == ResidenceCategory.REPATRIATED:
        required.append((("C7", "A3"), DOCUMENT_LABELS["C7"]))
        need("C8")
    # Ενότ. 10.Δ, 10.Ε — πιστοποιητικά ΤΚΧ
    need("D1")
    need("D2")
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


def required_documents_for_forms(forms) -> list[tuple[tuple[str, ...], str]]:
    """Δικαιολογητικά που απαιτούνται βάσει των τρεχουσών τιμών της φόρμας (bound ή unbound)."""
    from plot_applications.documents import _bool_or_none, _checkbox_bool

    required: list[tuple[tuple[str, ...], str]] = []

    def need(*codes: str):
        required.append((codes, DOCUMENT_LABELS[codes[0]]))

    main = forms.main
    ap = forms.applicant_party
    sp = forms.spouse_party

    family_status = str(main["family_status"].value() or "").strip()
    is_couple = family_status in ("couple_with_children", "couple_without_children")
    category = str(main["residence_category"].value() or "").strip()
    applicant_refugee = str(ap["refugee_identity_number"].value() or "").strip()

    need("A1")
    if category == ResidenceCategory.DISPLACED or bool(applicant_refugee):
        need("A2")
    if is_couple:
        required.append((("B1", "B2"), DOCUMENT_LABELS["B1"]))

    children_count = 0
    child_statuses: set[str] = set()
    for child_form in forms.children.forms:
        if "DELETE" in child_form.fields and _checkbox_bool(child_form["DELETE"].value()):
            continue
        values = [
            str(child_form[name].value() or "").strip()
            for name in ("first_name", "last_name", "date_of_birth", "identity_number", "status")
            if name in child_form.fields
        ]
        if not any(values):
            continue
        children_count += 1
        status = str(child_form["status"].value() or "").strip()
        if status:
            child_statuses.add(status)

    if children_count > 0:
        need("B11")
    if ApplicationChild.Status.STUDENT in child_statuses:
        need("B12")
    if ApplicationChild.Status.NATIONAL_GUARD in child_statuses:
        need("B13")
    if ApplicationChild.Status.ADULT_DISABILITY in child_statuses:
        need("B14")

    applicant_disability = _checkbox_bool(ap["has_disability"].value())
    spouse_disability = _checkbox_bool(sp["has_disability"].value()) if is_couple else False
    if applicant_disability or spouse_disability:
        need("B10")

    if category == ResidenceCategory.NEIGHBOURING:
        need("C9")
        need("C10")
    else:
        need("C1")
    if category == ResidenceCategory.INTERNAL_EMIGRANT:
        need("C6")
    if category == ResidenceCategory.REPATRIATED:
        required.append((("C7", "A3"), DOCUMENT_LABELS["C7"]))
        need("C8")

    has_alienated_property = _bool_or_none(main["has_alienated_property"].value())
    need("D1")
    need("D2")
    need("D3")
    if has_alienated_property is not True:
        need("D4")
        need("D5")

    spouse_id_val = str(forms.spouse["identity_number"].value() or "").strip() if is_couple else ""
    has_spouse = is_couple and bool(spouse_id_val)
    income_codes = {
        IncomeDeclaration.Member.APPLICANT: ("E1", "E2", "E3"),
        IncomeDeclaration.Member.SPOUSE: ("E4", "E5", "E6"),
        IncomeDeclaration.Member.CHILD: ("E7", "E8", "E9"),
        IncomeDeclaration.Member.OTHER: ("E7", "E8", "E9"),
    }
    needed_income_codes: set[str] = set()
    for inc_form in forms.incomes.forms:
        if "DELETE" in inc_form.fields and _checkbox_bool(inc_form["DELETE"].value()):
            continue
        raw_member = str(inc_form["member"].value() or "").strip()
        emp_type = str(inc_form["employment_type"].value() or "").strip()
        if not emp_type:
            continue
        if not raw_member or raw_member == IncomeDeclaration.Member.APPLICANT:
            norm_member = IncomeDeclaration.Member.APPLICANT
        elif raw_member == IncomeDeclaration.Member.SPOUSE:
            norm_member = IncomeDeclaration.Member.SPOUSE
        elif raw_member.startswith("child:") or raw_member == IncomeDeclaration.Member.CHILD:
            norm_member = IncomeDeclaration.Member.CHILD
        else:
            norm_member = IncomeDeclaration.Member.OTHER
        if norm_member == IncomeDeclaration.Member.SPOUSE and not has_spouse:
            continue
        employee, self_employed, other = income_codes.get(norm_member, ("E7", "E8", "E9"))
        code_to_need = None
        if emp_type == IncomeDeclaration.EmploymentType.EMPLOYEE:
            code_to_need = employee
        elif emp_type == IncomeDeclaration.EmploymentType.SELF_EMPLOYED:
            code_to_need = self_employed
        elif emp_type == IncomeDeclaration.EmploymentType.OTHER_SOURCE:
            code_to_need = other
        if code_to_need and code_to_need not in needed_income_codes:
            needed_income_codes.add(code_to_need)
            need(code_to_need)
    return required


def missing_required_field_labels(application: PlotApplication) -> list[str]:
    """Υποχρεωτικά πεδία της αίτησης που λείπουν ώστε η αίτηση να θεωρείται πλήρης (Ενότ. 5)."""
    missing: list[str] = []
    if not application.community_id:
        missing.append("Κοινότητα")
    if not application.submitted_on:
        missing.append("Ημερομηνία υποβολής")

    applicant = application.applicant if application.applicant_id else None
    applicant_party = application.applicant_party
    person_fields = (
        ("identity_number", "Αρ. Δελτίου Ταυτότητας"),
        ("first_name", "Όνομα"),
        ("last_name", "Επίθετο"),
        ("date_of_birth", "Ημερομηνία Γέννησης"),
        ("birth_place", "Τόπος Γέννησης"),
        ("birth_country", "Χώρα Γέννησης"),
        ("parents_birth_place", "Τόπος γέννησης γονέων"),
        ("parents_birth_country", "Χώρα Γέννησης Γονέων"),
    )
    if applicant is None:
        missing.append("Στοιχεία αιτητή/τριας")
    else:
        for attr, label in person_fields:
            val = getattr(applicant, attr, None)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(f"Αιτητής/τρια: {label}")

    if not applicant_party or not (applicant_party.citizenship or "").strip():
        missing.append("Αιτητής/τρια: Υπηκοότητα / Ιδιότητα")
    elif (
        applicant_party.citizenship == ApplicationParty.Citizenship.OTHER
        and not (applicant_party.citizenship_other or "").strip()
    ):
        missing.append("Αιτητής/τρια: Άλλο (περιγραφή υπηκοότητας)")
    if not applicant_party or not (applicant_party.mobile_phone or "").strip():
        missing.append("Αιτητής/τρια: Τηλέφωνο Κινητό")
    if not (application.email or "").strip():
        missing.append("Ηλεκτρονική Διεύθυνση")

    category = (application.residence_category or "").strip()
    if not category:
        missing.append("Τόπος διαμονής: Κατηγορία")
    elif not (application.residence_community or "").strip():
        if category == ResidenceCategory.NEIGHBOURING:
            missing.append("Τόπος διαμονής: Γειτονική Κοινότητα")
        else:
            missing.append("Τόπος διαμονής: Κοινότητα / Δ.Δ. διαμονής")

    family_status = (application.family_status or "").strip()
    if not family_status:
        missing.append("Οικογενειακή κατάσταση")
    elif family_status == PlotApplication.FamilyStatus.SINGLE_PARENT:
        single_status = (application.single_parent_status or "").strip()
        if not single_status:
            missing.append("Μονογονιός (περίπτωση)")
        elif (
            single_status == PlotApplication.SingleParentStatus.OTHER
            and not (application.single_parent_other or "").strip()
        ):
            missing.append("Μονογονιός: Άλλο (περιγραφή)")

    if application.is_couple:
        spouse = application.spouse if application.spouse_id else None
        spouse_party = application.spouse_party
        if spouse is None:
            missing.append("Στοιχεία συζύγου/συμβίου")
        else:
            for attr, label in person_fields:
                val = getattr(spouse, attr, None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    missing.append(f"Σύζυγος/Συμβίος: {label}")
        if not spouse_party or not (spouse_party.citizenship or "").strip():
            missing.append("Σύζυγος/Συμβίος: Υπηκοότητα / Ιδιότητα")
        elif (
            spouse_party.citizenship == ApplicationParty.Citizenship.OTHER
            and not (spouse_party.citizenship_other or "").strip()
        ):
            missing.append("Σύζυγος/Συμβίος: Άλλο (περιγραφή υπηκοότητας)")
        if not spouse_party or not (spouse_party.mobile_phone or "").strip():
            missing.append("Σύζυγος/Συμβίος: Τηλέφωνο Κινητό")

    if application.has_dwelling is None:
        missing.append("Εγγεγραμμένη κατοικία (Ναι/Όχι)")
    if application.has_residential_land is None:
        missing.append("Οικόπεδο/τεμάχιο σε Οικιστική Ζώνη (Ναι/Όχι)")
    if application.has_alienated_property is None:
        missing.append("Αποξένωση εντός 3 ετών (Ναι/Όχι)")
    if application.previous_housing_aid is None:
        missing.append("Προηγούμενη κρατική στεγαστική ενίσχυση (Ναι/Όχι)")

    return missing


def _required_fields_criterion(application: PlotApplication) -> tuple[CriterionResult, list[str]]:
    missing = missing_required_field_labels(application)
    if missing:
        return (
            CriterionResult(
                "required_fields",
                "Υποχρεωτικά πεδία αίτησης",
                "5, 20.2",
                FAIL,
                "Λείπουν υποχρεωτικά πεδία: " + "; ".join(missing),
            ),
            missing,
        )
    return (
        CriterionResult(
            "required_fields",
            "Υποχρεωτικά πεδία αίτησης",
            "5, 20.2",
            PASS,
            "Όλα τα υποχρεωτικά πεδία της αίτησης είναι συμπληρωμένα.",
        ),
        [],
    )


def _signatures_criterion(application: PlotApplication) -> CriterionResult:
    if application.is_couple:
        signed = bool(application.applicant_signed and application.spouse_signed)
        note = (
            "Η αίτηση είναι υπογεγραμμένη και από τα δύο πρόσωπα του ζεύγους."
            if signed
            else "Ζεύγος: η αίτηση πρέπει να υπογράφεται και από τα δύο πρόσωπα — απορρίπτεται."
        )
    else:
        signed = bool(application.applicant_signed)
        note = (
            "Η αίτηση είναι υπογεγραμμένη από τον/την αιτητή/τρια."
            if signed
            else "Η αίτηση δεν υπογράφηκε."
        )
    return CriterionResult("signatures", "Υπογραφές", "5", PASS if signed else FAIL, note)


def _documents_assessment(
    application: PlotApplication,
) -> tuple[CriterionResult, str, list[str]]:
    attached = set(application.attached_documents or [])
    missing_required = [
        label for codes, label in required_documents(application) if not attached.intersection(codes)
    ]
    applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren"))
    missing_applicable = [
        label
        for _, items in DOCUMENT_GROUPS
        for code, label in items
        if code in applicable and code not in attached
    ]
    missing = missing_required or missing_applicable
    override = bool(application.documents_complete_override)
    reason = (application.documents_complete_reason or "").strip()
    if not missing_required:
        note = (
            f"Ολοκληρωμένη ({reason})"
            if override and reason
            else "Ολοκληρωμένη όσον αφορά τα απαιτούμενα δικαιολογητικά."
        )
        return (
            CriterionResult("documents", "Δικαιολογητικά", "5, 20.2", PASS, note),
            DocumentsCompleteness.COMPLETE,
            missing,
        )
    if override:
        missing_str = "; ".join(missing_required)
        if reason:
            note = f"Χαρακτηρίστηκε ολοκληρωμένη: {reason} (Ελλείποντα: {missing_str})"
        else:
            note = f"Χαρακτηρίστηκε ολοκληρωμένη (Ελλείποντα: {missing_str})"
        return (
            CriterionResult("documents", "Δικαιολογητικά", "5, 20.2", PASS, note),
            DocumentsCompleteness.COMPLETE,
            missing,
        )
    return (
        CriterionResult(
            "documents",
            "Δικαιολογητικά",
            "5, 20.2",
            FAIL,
            "Ελλιπής — λείπουν δικαιολογητικά (η αίτηση που χρειάζεται συμπλήρωση απορρίπτεται): "
            + "; ".join(missing_required),
        ),
        DocumentsCompleteness.INCOMPLETE,
        missing,
    )


def _documents_criterion(application: PlotApplication) -> CriterionResult:
    criterion, _, _ = _documents_assessment(application)
    return criterion


NEIGHBOURING_PRIORITY = 5
PRIMARY_ORDER = {
    ResidenceCategory.AUTOCHTHON: 1,
    ResidenceCategory.DISPLACED: 2,
    ResidenceCategory.INTERNAL_EMIGRANT: 3,
    ResidenceCategory.REPATRIATED: 4,
}
SECONDARY_LABELS = {
    1: "Πολύτεκνη οικογένεια",
    2: "Οικογένεια μη πολύτεκνη",
    3: "Μονογονεϊκή οικογένεια",
    4: "Ζεύγος χωρίς τέκνα",
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
        secondary = 1
    elif application.is_couple and recognized_children > 0:
        secondary = 2
    elif application.family_status == PlotApplication.FamilyStatus.SINGLE_PARENT:
        secondary = 3
    else:
        secondary = 4
    return primary, secondary, f"{primary_label} · {SECONDARY_LABELS[secondary]}"


def _prioritization_outcome(application: PlotApplication) -> str | None:
    """Αν έχει ολοκληρωθεί η διαδικασία επιλογής/προτεραιοποίησης και κατανομής για δικαιούχο αίτηση,
    επιστρέφει PlotAllocationStatus.ALLOCATED ή PlotAllocationStatus.NOT_ALLOCATED, αλλιώς None.
    """
    if not application.pk:
        return None
    if any(alloc.status == "active" for alloc in application.allocations.all()):
        return PlotAllocationStatus.ALLOCATED
    finalized_entries = [
        entry
        for entry in application.ranking_entries.select_related("ranking_list").all()
        if entry.ranking_list_id
        and (
            entry.ranking_list.finalized_at is not None
            or entry.ranking_list.list_type == "final"
        )
    ]
    if finalized_entries:
        if any(entry.status == "eligible" for entry in finalized_entries):
            return PlotAllocationStatus.ALLOCATED
        return PlotAllocationStatus.NOT_ALLOCATED
    if (
        application.application_stage == ApplicationStage.COMPLETED
        and application.eligibility_result == EligibilityResult.PASS
        and application.plot_allocation_status
        in (PlotAllocationStatus.ALLOCATED, PlotAllocationStatus.NOT_ALLOCATED)
    ):
        return application.plot_allocation_status
    return None


def _assess_stage_and_allocation(
    application: PlotApplication,
    completeness_overall: str,
    documents_completeness: str,
    eligibility_overall: str,
) -> tuple[str, str]:
    """Υπολογίζει το στάδιο της αίτησης (`ApplicationStage`) και την κατάσταση παραχώρησης οικοπέδου (`PlotAllocationStatus`).

    Στάδια:
    1. `collection`: Συλλογή πληροφοριών και πιστοποιητικών μέχρι η αίτηση να είναι πλήρης· η
       ελλιπής αίτηση εκκρεμεί εδώ μέχρι να συμπληρωθεί ή να απορριφθεί από τον λειτουργό.
    2. `examination`: Εξέταση επιλεξιμότητας — το λογισμικό δεν έχει ακόμη κρίνει κατά πόσο είναι
       δικαιούχος (εκκρεμεί κριτήριο) και ο λειτουργός δεν έχει αλλάξει χειροκίνητα το αποτέλεσμα.
    3. `prioritization`: Επιλογή και προτεραιοποίηση — η πλήρης αίτηση έχει κριθεί δικαιούχος ή μη
       δικαιούχος (από το λογισμικό ή χειροκίνητα) και εμφανίζεται στον κατάλογο προτεραιοποίησης
       της Κοινότητας μέχρι να οριστικοποιηθεί ο κατάλογος / η κατανομή.
    4. `completed`: Ολοκλήρωση, όταν η αίτηση περιληφθεί σε οριστικοποιημένο κατάλογο ή λάβει
       οικόπεδο (μη δικαιούχος → «Δεν πήρε οικόπεδο»), ή όταν απορριφθεί λόγω ελλείψεων (Ενότ. 5(β)).
    """
    if completeness_overall == ApplicationCompleteness.REJECTED:
        return ApplicationStage.COMPLETED, PlotAllocationStatus.NOT_ALLOCATED
    is_complete = (
        completeness_overall == ApplicationCompleteness.COMPLETE
        and documents_completeness == DocumentsCompleteness.COMPLETE
    )
    if not is_complete:
        return ApplicationStage.COLLECTION, PlotAllocationStatus.PENDING
    if eligibility_overall == PENDING:
        return ApplicationStage.EXAMINATION, PlotAllocationStatus.PENDING
    outcome = _prioritization_outcome(application)
    if outcome is not None:
        if eligibility_overall == FAIL:
            return ApplicationStage.COMPLETED, PlotAllocationStatus.NOT_ALLOCATED
        return ApplicationStage.COMPLETED, outcome
    return ApplicationStage.PRIORITIZATION, PlotAllocationStatus.PENDING


def evaluate(application: PlotApplication) -> dict:
    """Υπολογίζει τα 2 σύνολα κριτηρίων της αίτησης (χωρίς αποθήκευση):
    1. Κριτήρια πληρότητας της αίτησης (`completeness_criteria`, `completeness_overall`).
    2. Κριτήρια επιλεξιμότητας δικαιούχου (`eligibility_criteria`, `eligibility_overall`), ανεξάρτητα
       από την πληρότητα της αίτησης.
    """
    on = application.submitted_on
    applicant_party = application.applicant_party
    spouse_party = application.spouse_party if application.is_couple else None
    has_spouse = application.is_couple and application.spouse_id is not None

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Κριτήρια πληρότητας αίτησης (Ενότ. 5, 20.2)
    # ─────────────────────────────────────────────────────────────────────────
    completeness_criteria: list[CriterionResult] = []
    required_fields_criterion, missing_fields = _required_fields_criterion(application)
    completeness_criteria.append(required_fields_criterion)
    signatures_criterion = _signatures_criterion(application)
    completeness_criteria.append(signatures_criterion)
    documents_criterion, documents_completeness, missing_documents = _documents_assessment(application)
    completeness_criteria.append(documents_criterion)

    completeness_all_pass = all(item.result == PASS for item in completeness_criteria)
    # Ενότ. 5(β): η απορριφθείσα αίτηση δεν διορθώνεται — ο αιτητής υποβάλλει νέα αίτηση.
    is_rejected = bool(application.incomplete_rejected)
    if is_rejected:
        completeness_overall = ApplicationCompleteness.REJECTED
    elif completeness_all_pass:
        completeness_overall = ApplicationCompleteness.COMPLETE
    else:
        completeness_overall = ApplicationCompleteness.INCOMPLETE
    completeness_badge = {
        ApplicationCompleteness.COMPLETE: PASS,
        ApplicationCompleteness.INCOMPLETE: PENDING,
        ApplicationCompleteness.REJECTED: FAIL,
    }[completeness_overall]

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Κριτήρια επιλεξιμότητας δικαιούχου (Ενότ. 10, 11, 20.3)
    #    (ανεξάρτητα από την πληρότητα της αίτησης)
    # ─────────────────────────────────────────────────────────────────────────
    eligibility_criteria: list[CriterionResult] = []

    # Ενότ. 10 — Κύπριοι πολίτες (τουλάχιστον ένα πρόσωπο του Ζεύγους)
    cypriot = bool(applicant_party and applicant_party.is_cypriot) or bool(spouse_party and spouse_party.is_cypriot)
    has_declared_citizenship = bool(applicant_party and applicant_party.citizenship) or bool(
        spouse_party and spouse_party.citizenship
    )
    if cypriot:
        cypriot_roles = []
        if applicant_party and applicant_party.is_cypriot:
            cypriot_roles.append("αιτητής/τρια")
        if spouse_party and spouse_party.is_cypriot:
            cypriot_roles.append("σύζυγος/συμβίος")
        cit_result = PASS
        cit_note = f"Κύπριος πολίτης ({', '.join(cypriot_roles)})."
    elif not has_declared_citizenship:
        cit_result, cit_note = PENDING, "Δεν δηλώθηκε υπηκοότητα."
    else:
        cit_result, cit_note = FAIL, "Κανένα πρόσωπο δεν είναι Κύπριος πολίτης."
    eligibility_criteria.append(
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
            status_display = application.get_family_status_display()
            if children:
                base_note = f"{status_display} ({recognized} από {len(children)} τέκνα κατά την Ενότ. 10.Α)."
            else:
                base_note = f"{status_display}."
            family = (PASS, base_note)
        else:
            family = (FAIL, "Ζεύγος χωρίς στοιχεία συζύγου/συμβίου.")
    elif application.family_status == PlotApplication.FamilyStatus.SINGLE_PARENT:
        if recognized > 0:
            status_display = application.get_family_status_display()
            family = (
                PASS,
                f"{status_display} ({recognized} από {len(children)} τέκνα κατά την Ενότ. 10.Α).",
            )
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
    eligibility_criteria.append(
        CriterionResult("family", "Οικογενειακή κατάσταση", "10.Α", family[0], family_note)
    )

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
    eligibility_criteria.append(CriterionResult("age", "Ηλικία", "10.Β", age_result, age_note))

    # Ενότ. 10.Γ / 11 — διαμονή
    eligibility_criteria.append(_residence_criterion(application, applicant_party))

    # Ενότ. 10.Δ — άλλη ακίνητη ιδιοκτησία (κάθε πρόσωπο χωριστά)
    eligibility_criteria.append(
        _yes_no_criterion(
            "dwelling",
            "Εγγεγραμμένη κατοικία",
            "10.Δ",
            application.has_dwelling,
            "Δηλώθηκε εγγεγραμμένη κατοικία.",
            details=application.has_dwelling_details,
        )
    )
    eligibility_criteria.append(
        _yes_no_criterion(
            "land",
            "Οικόπεδο/τεμάχιο σε Οικιστική Ζώνη",
            "10.Δ",
            application.has_residential_land,
            "Δηλώθηκε οικόπεδο/τεμάχιο σε περιοχή όπου επιτρέπεται κατοικία.",
            details=application.has_residential_land_details,
        )
    )
    # Ενότ. 10.Ε — μη αποξένωση
    eligibility_criteria.append(
        _yes_no_criterion(
            "alienation",
            "Μη αποξένωση (3 έτη)",
            "10.Ε",
            application.has_alienated_property,
            "Δηλώθηκε αποξένωση ακινήτου εντός 3 ετών.",
            details=application.has_alienated_property_details,
        )
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
    eligibility_criteria.append(income_criterion)

    # Ενότ. 20.3 — προηγούμενη κρατική στεγαστική ενίσχυση
    eligibility_criteria.append(
        _yes_no_criterion(
            "previous_aid",
            "Προηγούμενη κρατική στεγαστική ενίσχυση",
            "20.3",
            application.previous_housing_aid,
            "Δηλώθηκε προηγούμενη ενίσχυση (εξαιρούνται μόνο επιδότηση ενοικίου/επιτοκίου).",
            "Δηλώθηκε «Όχι» (και στην Ένορκη Δήλωση).",
            details=application.previous_housing_aid_details,
        )
    )

    eligibility_results = {item.result for item in eligibility_criteria}
    eligibility_auto_overall = (
        FAIL
        if FAIL in eligibility_results
        else PENDING
        if PENDING in eligibility_results
        else PASS
    )
    # Ενότ. 6 — ο λειτουργός μπορεί να αλλάξει χειροκίνητα το αποτέλεσμα του λογισμικού, με αιτιολογία.
    eligibility_overridden = application.is_eligibility_overridden
    eligibility_overall = (
        application.eligibility_override if eligibility_overridden else eligibility_auto_overall
    )

    all_criteria = [*completeness_criteria, *eligibility_criteria]
    if eligibility_overall == FAIL or is_rejected:
        beneficiary_status = FAIL
        beneficiary_label = "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"
    elif (
        completeness_overall == ApplicationCompleteness.COMPLETE
        and documents_completeness == DocumentsCompleteness.COMPLETE
        and eligibility_overall == PASS
    ):
        beneficiary_status = PASS
        beneficiary_label = "ΔΙΚΑΙΟΥΧΟΣ"
    else:
        beneficiary_status = PENDING
        beneficiary_label = "ΕΚΚΡΕΜΕΙ"
    is_beneficiary = beneficiary_status == PASS
    application_stage, plot_allocation_status = _assess_stage_and_allocation(
        application,
        completeness_overall,
        documents_completeness,
        eligibility_overall,
    )
    application_stage_badge = (
        "pass" if application_stage == ApplicationStage.COMPLETED else "pending"
    )
    if plot_allocation_status == PlotAllocationStatus.ALLOCATED:
        plot_allocation_badge = "pass"
    elif plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED:
        plot_allocation_badge = "fail"
    else:
        plot_allocation_badge = "pending"
    primary, secondary, priority_label = priority(application, recognized)
    return {
        "completeness_criteria": completeness_criteria,
        "completeness_overall": completeness_overall,
        "completeness_label": ApplicationCompleteness(completeness_overall).label,
        "completeness_badge": completeness_badge,
        "is_rejected_incomplete": is_rejected,
        "required_fields_criterion": required_fields_criterion,
        "missing_required_fields": missing_fields,
        "signatures_criterion": signatures_criterion,
        "documents_criterion": documents_criterion,
        "documents_completeness": documents_completeness,
        "documents_completeness_label": DocumentsCompleteness(documents_completeness).label,
        "missing_documents": missing_documents,
        "eligibility_criteria": eligibility_criteria,
        "eligibility_overall": eligibility_overall,
        "eligibility_label": EligibilityResult(eligibility_overall).label,
        "eligibility_auto_overall": eligibility_auto_overall,
        "eligibility_auto_label": EligibilityResult(eligibility_auto_overall).label,
        "eligibility_overridden": eligibility_overridden,
        "eligibility_override_label": (
            EligibilityOverride(application.eligibility_override).label if eligibility_overridden else ""
        ),
        "eligibility_override_reason": application.eligibility_override_reason if eligibility_overridden else "",
        "beneficiary_status": beneficiary_status,
        "is_beneficiary": is_beneficiary,
        "beneficiary_label": beneficiary_label,
        "application_stage": application_stage,
        "application_stage_label": get_application_stage_label(application_stage),
        "application_stage_badge": application_stage_badge,
        "plot_allocation_status": plot_allocation_status,
        "plot_allocation_label": PlotAllocationStatus(plot_allocation_status).label,
        "plot_allocation_badge": plot_allocation_badge,
        "criteria": all_criteria,
        "children": children,
        "overall": eligibility_overall,
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
    """Υπολογίζει και αποθηκεύει τα παράγωγα πεδία πληρότητας, επιλεξιμότητας, σταδίου και παραχώρησης οικοπέδου της αίτησης."""
    outcome = evaluate(application)
    if application.pk and application.is_beneficiary != outcome["is_beneficiary"]:
        # Η χειροκίνητη θέση ισχύει μόνο εντός της ομάδας (δικαιούχοι / μη δικαιούχοι) του καταλόγου.
        application.priority_rank = None
    application.children_count = outcome["children_count"]
    application.recognized_children_count = outcome["recognized_children_count"]
    application.family_members_count = outcome["family_members_count"]
    application.family_income_total = outcome["family_income_total"]
    application.documents_completeness = outcome["documents_completeness"]
    application.completeness_result = outcome["completeness_overall"]
    application.completeness_details = [asdict(item) for item in outcome["completeness_criteria"]]
    application.eligibility_result = outcome["eligibility_overall"]
    application.eligibility_auto_result = outcome["eligibility_auto_overall"]
    application.eligibility_details = [asdict(item) for item in outcome["eligibility_criteria"]]
    application.application_stage = outcome["application_stage"]
    application.plot_allocation_status = outcome["plot_allocation_status"]
    application.priority_primary = outcome["priority_primary"]
    application.priority_secondary = outcome["priority_secondary"]
    application.priority_label = outcome["priority_label"]
    application.save()
    return outcome
