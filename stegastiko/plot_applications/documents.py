"""Κατάλογος Απαιτούμενων Δικαιολογητικών Εγγράφων του Παραρτήματος 3.

Η αίτηση ΔΕΝ θεωρείται πλήρης αν δεν επισυναφθούν τα έγγραφα που εφαρμόζονται (Ενότ. 5, 20.2).
"""

from dataclasses import dataclass, field

DOCUMENT_GROUPS = (
    (
        "Α. Κυπριακή ή άλλη Υπηκοότητα και Ηλικία",
        (
            ("A1", "Αντίγραφο δελτίου πολιτικής ταυτότητας Κυπριακής Δημοκρατίας (αιτητή/τριας ή και των δύο)"),
            ("A2", "Αντίγραφο προσφυγικής ταυτότητας"),
            ("A4", "Αντίγραφο διαβατηρίου ή δελτίου ταυτότητας (σύζυγος/συμβίος)"),
        ),
    ),
    (
        "Β. Οικογενειακή Κατάσταση",
        (
            ("B1", "Αντίγραφο πιστοποιητικού γάμου"),
            ("B2", "Σύμφωνο συμβίωσης"),
            ("B3", "Διακανονισμός φύλαξης τέκνων ή έντυπο υπογεγραμμένο από τους δύο γονείς"),
            ("B4", "Αναγνώριση εξώγαμου τέκνου / βεβαίωση αρχών / διάταγμα γονικής μέριμνας ή διατροφής / πιστοποιητικό γέννησης"),
            ("B5", "Αντίγραφο διαζυγίου και διάταγμα γονικής μέριμνας ή διατροφής ή κοινή ένορκη δήλωση"),
            ("B6", "Βεβαίωση Διευθυντή Φυλακών"),
            ("B7", "Πιστοποιητικό θανάτου"),
            ("B8", "Απόφαση δικαστηρίου ότι κηρύχθηκε σε αφάνεια"),
            ("B9", "Αντίγραφο πολυτεκνικής ταυτότητας"),
            ("B10", "Ευρωπαϊκή κάρτα αναπηρίας ή βεβαίωση ΤΚΕΑΑ (αιτητής/σύζυγος)"),
            ("B11", "Πιστά αντίγραφα πιστοποιητικών γέννησης τέκνων"),
            ("B12", "Βεβαίωση φοίτησης"),
            ("B13", "Βεβαίωση Εθνικής Φρουράς"),
            ("B14", "Ευρωπαϊκή κάρτα αναπηρίας ή βεβαίωση ΤΚΕΑΑ (ενήλικο τέκνο)"),
        ),
    ),
    (
        "Γ. Τόπος Διαμονής",
        (
            ("C1", "Λογαριασμός ΑΗΚ στο όνομα αιτητή (ή ενός εκ του ζεύγους) για διεύθυνση στην Κοινότητα"),
            ("C2", "Βεβαίωση Κοινότητας ότι ο αιτητής διαβιεί σε διεύθυνση εντός της Κοινότητας"),
            ("C3", "Βεβαίωση Εθνικής Φρουράς"),
            ("C4", "Βεβαίωση φοίτησης"),
            ("C5", "Ιατρική βεβαίωση νοσηλείας"),
            ("C6", "Βεβαίωση Κοινότητας για την περίοδο μόνιμης κατοίκησης"),
            ("C7", "Βεβαιώσεις δεκαετούς παραμονής στο εξωτερικό"),
            ("C8", "Βεβαίωση Κοινότητας για διαμονή τουλάχιστον 3 ετών"),
            ("C9", "Λογαριασμός ΑΗΚ για διεύθυνση στη Γειτονική Κοινότητα"),
            ("C10", "Βεβαίωση της Γειτονικής Κοινότητας για διαμονή"),
        ),
    ),
    (
        "Δ. Ακίνητη ιδιοκτησία (ΤΚΧ — DLS Portal, Παγκύπρια)",
        (
            ("D1", "Πιστοποιητικό έρευνας ακίνητης ιδιοκτησίας συγκεκριμένου ιδιοκτήτη — αιτητής και σύζυγος"),
            ("D2", "Πιστοποιητικό έρευνας για πωλητήρια έγγραφα συγκεκριμένου αγοραστή — αιτητής και σύζυγος"),
            ("D3", "Πιστοποιητικό έρευνας ακίνητης ιδιοκτησίας — γονείς αιτητή και συζύγου, τέκνα ζεύγους"),
            ("D4", "Πιστοποιητικό αποξενωθέντων ακινήτων τελευταίων 3 ετών — αιτητής και σύζυγος"),
            ("D5", "Πιστοποιητικό αποξενωθέντων ακινήτων τελευταίων 3 ετών — γονείς αιτητή και συζύγου"),
        ),
    ),
    (
        "Ε. Εισοδήματα (έτος που προηγείται της αίτησης)",
        (
            ("E1", "Πιστοποιητικό αποδοχών, κατάσταση ασφαλιστέων αποδοχών, φορολογική δήλωση TAXISNET + status (Αιτητής/τρια)"),
            ("E2", "Φορολογική δήλωση TAXISNET + status (Αιτητής/τρια)"),
            ("E3", "Άλλα πιστοποιητικά για κάθε άλλο είδος εισοδήματος (Αιτητής/τρια)"),
            ("E4", "Πιστοποιητικό αποδοχών, κατάσταση ασφαλιστέων αποδοχών, φορολογική δήλωση TAXISNET + status (Σύζυγος/Συμβίος)"),
            ("E5", "Φορολογική δήλωση TAXISNET + status (Σύζυγος/Συμβίος)"),
            ("E6", "Άλλα πιστοποιητικά για κάθε άλλο είδος εισοδήματος (Σύζυγος/Συμβίος)"),
            ("E7", "Πιστοποιητικό αποδοχών, κατάσταση ασφαλιστέων αποδοχών, φορολογική δήλωση + status (Άλλο μέλος)"),
            ("E8", "Φορολογική δήλωση TAXISNET + status (Άλλο μέλος)"),
            ("E9", "Άλλα πιστοποιητικά για κάθε άλλο είδος εισοδήματος (Άλλο μέλος)"),
        ),
    ),
)

DOCUMENT_CHOICES = tuple(item for _, items in DOCUMENT_GROUPS for item in items)
DOCUMENT_LABELS = dict(DOCUMENT_CHOICES)


@dataclass
class DocumentContext:
    family_status: str = ""
    single_parent_status: str = ""
    residence_category: str = ""
    applicant_citizenship: str = ""
    applicant_refugee_id: str = ""
    applicant_is_employee: bool = False
    applicant_is_self_employed: bool = False
    applicant_has_disability: bool = False
    spouse_citizenship: str = ""
    spouse_refugee_id: str = ""
    spouse_alien_number: str = ""
    spouse_is_employee: bool = False
    spouse_is_self_employed: bool = False
    spouse_has_disability: bool = False
    children_count: int = 0
    child_statuses: set[str] = field(default_factory=set)
    large_family_children: int = 4
    has_dwelling: bool | None = None
    has_residential_land: bool | None = None
    has_alienated_property: bool | None = None
    income_pairs: set[tuple[str, str]] = field(default_factory=set)


def applicable_codes_from_context(ctx: DocumentContext) -> set[str]:
    """Κωδικοί δικαιολογητικών που έχουν νόημα να εμφανίζονται βάσει των δηλωθέντων στοιχείων."""
    codes: set[str] = set()
    is_couple = ctx.family_status in ("couple_with_children", "couple_without_children")
    is_single_parent = ctx.family_status == "single_parent"

    # Α. Κυπριακή ή άλλη Υπηκοότητα και Ηλικία
    if ctx.applicant_citizenship == "cypriot" or (is_couple and ctx.spouse_citizenship == "cypriot"):
        codes.add("A1")
    if (
        ctx.residence_category == "displaced"
        or bool((ctx.applicant_refugee_id or "").strip())
        or (is_couple and bool((ctx.spouse_refugee_id or "").strip()))
    ):
        codes.add("A2")
    if is_couple and (
        ctx.spouse_citizenship == "other" or bool((ctx.spouse_alien_number or "").strip())
    ):
        codes.add("A4")

    # Β. Οικογενειακή Κατάσταση
    if is_couple:
        codes.update(("B1", "B2"))
    if is_single_parent:
        codes.add("B3")
        if ctx.single_parent_status == "unmarried":
            codes.add("B4")
        elif ctx.single_parent_status == "divorced":
            codes.add("B5")
        elif ctx.single_parent_status == "widowed":
            codes.add("B7")
        elif ctx.single_parent_status == "other":
            codes.update(("B6", "B7", "B8"))
    if ctx.children_count >= ctx.large_family_children:
        codes.add("B9")
    if ctx.applicant_has_disability or (is_couple and ctx.spouse_has_disability):
        codes.add("B10")
    if ctx.children_count > 0 or ctx.family_status in ("couple_with_children", "single_parent"):
        codes.add("B11")
    if "student" in ctx.child_statuses:
        codes.add("B12")
    if "national_guard" in ctx.child_statuses:
        codes.add("B13")
    if "adult_disability" in ctx.child_statuses:
        codes.add("B14")

    # Γ. Τόπος Διαμονής
    if ctx.residence_category in ("autochthon", "displaced", "internal_emigrant", "repatriated"):
        codes.update(("C1", "C2"))
    if ctx.residence_category in ("autochthon", "displaced"):
        codes.update(("C3", "C4", "C5"))
    if ctx.residence_category == "internal_emigrant":
        codes.add("C6")
    if ctx.residence_category == "repatriated":
        codes.update(("C7", "C8"))
    if ctx.residence_category == "neighbouring":
        codes.update(("C9", "C10"))

    # Δ. Ακίνητη ιδιοκτησία (ΤΚΧ — DLS Portal, Παγκύπρια)
    if ctx.has_dwelling is not True or ctx.has_residential_land is not True:
        codes.update(("D1", "D2"))
    if ctx.has_residential_land is not True:
        codes.add("D3")
    if ctx.has_alienated_property is not True:
        codes.update(("D4", "D5"))

    # Ε. Εισοδήματα (έτος που προηγείται της αίτησης)
    if ctx.applicant_is_employee or ("applicant", "employee") in ctx.income_pairs:
        codes.add("E1")
    if ctx.applicant_is_self_employed or ("applicant", "self_employed") in ctx.income_pairs:
        codes.add("E2")
    if ("applicant", "other") in ctx.income_pairs:
        codes.add("E3")
    if is_couple:
        if ctx.spouse_is_employee or ("spouse", "employee") in ctx.income_pairs:
            codes.add("E4")
        if ctx.spouse_is_self_employed or ("spouse", "self_employed") in ctx.income_pairs:
            codes.add("E5")
        if ("spouse", "other") in ctx.income_pairs:
            codes.add("E6")
    if ("other_member", "employee") in ctx.income_pairs:
        codes.add("E7")
    if ("other_member", "self_employed") in ctx.income_pairs:
        codes.add("E8")
    if ("other_member", "other") in ctx.income_pairs:
        codes.add("E9")

    return codes


def applicable_documents(application, large_family_children: int = 4) -> set[str]:
    """Κωδικοί δικαιολογητικών που εφαρμόζονται σε αποθηκευμένη PlotApplication."""
    ap = application.applicant_party
    sp = application.spouse_party if application.is_couple else None
    children = list(application.children.all()) if application.pk else []
    income_pairs: set[tuple[str, str]] = set()
    if application.pk:
        for inc in application.incomes.all():
            if not inc.employment_type:
                continue
            if inc.member == "applicant":
                norm_member = "applicant"
            elif inc.member == "spouse":
                norm_member = "spouse"
            else:
                norm_member = "other_member"
            income_pairs.add((norm_member, inc.employment_type))

    ctx = DocumentContext(
        family_status=application.family_status or "",
        single_parent_status=application.single_parent_status or "",
        residence_category=application.residence_category or "",
        applicant_citizenship=ap.citizenship if ap else "",
        applicant_refugee_id=ap.refugee_identity_number if ap else "",
        applicant_is_employee=bool(ap and ap.is_employee),
        applicant_is_self_employed=bool(ap and ap.is_self_employed),
        applicant_has_disability=bool(ap and ap.has_disability),
        spouse_citizenship=sp.citizenship if sp else "",
        spouse_refugee_id=sp.refugee_identity_number if sp else "",
        spouse_alien_number=sp.alien_registration_number if sp else "",
        spouse_is_employee=bool(sp and sp.is_employee),
        spouse_is_self_employed=bool(sp and sp.is_self_employed),
        spouse_has_disability=bool(sp and sp.has_disability),
        children_count=len(children),
        child_statuses={c.status for c in children if c.status},
        large_family_children=large_family_children,
        has_dwelling=application.has_dwelling,
        has_residential_land=application.has_residential_land,
        has_alienated_property=application.has_alienated_property,
        income_pairs=income_pairs,
    )
    return applicable_codes_from_context(ctx)


def _bool_or_none(value) -> bool | None:
    if value in (True, "True"):
        return True
    if value in (False, "False"):
        return False
    return None


def _checkbox_bool(value) -> bool:
    return bool(value and value not in ("False", "0"))


def applicable_documents_for_forms(forms, large_family_children: int = 4) -> set[str]:
    """Κωδικοί δικαιολογητικών που εμφανίζονται στη φόρμα (bound ή unbound)."""
    main = forms.main
    ap = forms.applicant_party
    sp = forms.spouse_party

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

    income_pairs: set[tuple[str, str]] = set()
    for inc_form in forms.incomes.forms:
        if "DELETE" in inc_form.fields and _checkbox_bool(inc_form["DELETE"].value()):
            continue
        member = str(inc_form["member"].value() or "").strip()
        emp_type = str(inc_form["employment_type"].value() or "").strip()
        if not emp_type:
            continue
        if not member or member == "applicant":
            norm_member = "applicant"
        elif member == "spouse":
            norm_member = "spouse"
        else:
            norm_member = "other_member"
        income_pairs.add((norm_member, emp_type))

    ctx = DocumentContext(
        family_status=str(main["family_status"].value() or "").strip(),
        single_parent_status=str(main["single_parent_status"].value() or "").strip(),
        residence_category=str(main["residence_category"].value() or "").strip(),
        applicant_citizenship=str(ap["citizenship"].value() or "").strip(),
        applicant_refugee_id=str(ap["refugee_identity_number"].value() or "").strip(),
        applicant_is_employee=_checkbox_bool(ap["is_employee"].value()),
        applicant_is_self_employed=_checkbox_bool(ap["is_self_employed"].value()),
        applicant_has_disability=_checkbox_bool(ap["has_disability"].value()),
        spouse_citizenship=str(sp["citizenship"].value() or "").strip(),
        spouse_refugee_id=str(sp["refugee_identity_number"].value() or "").strip(),
        spouse_alien_number=str(sp["alien_registration_number"].value() or "").strip(),
        spouse_is_employee=_checkbox_bool(sp["is_employee"].value()),
        spouse_is_self_employed=_checkbox_bool(sp["is_self_employed"].value()),
        spouse_has_disability=_checkbox_bool(sp["has_disability"].value()),
        children_count=children_count,
        child_statuses=child_statuses,
        large_family_children=large_family_children,
        has_dwelling=_bool_or_none(main["has_dwelling"].value()),
        has_residential_land=_bool_or_none(main["has_residential_land"].value()),
        has_alienated_property=_bool_or_none(main["has_alienated_property"].value()),
        income_pairs=income_pairs,
    )
    return applicable_codes_from_context(ctx)


