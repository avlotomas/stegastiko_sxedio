"""Catalog of application functions and sub-functions that roles grant access to (§Β.3).

Each function lists only the access types that make sense for it. A sub-function is
reachable only when the same role set also grants «Προβολή» on its parent function.
Grants are stored on `Role.grants` as "function_code:access_type" strings.
"""

from dataclasses import dataclass

VIEW = "view"
CREATE = "create"
EDIT = "edit"
DELETE = "delete"
EXPORT = "export"
SEND = "send"
PUBLISH = "publish"
IMPORT = "import"

ACCESS_TYPES = (
    (VIEW, "Προβολή"),
    (CREATE, "Δημιουργία"),
    (EDIT, "Τροποποίηση"),
    (DELETE, "Διαγραφή"),
    (EXPORT, "Εξαγωγή PDF"),
    (SEND, "Αποστολή email"),
    (PUBLISH, "Οριστικοποίηση / Έκδοση"),
    (IMPORT, "Εισαγωγή αρχείου"),
)
ACCESS_TYPE_LABELS = dict(ACCESS_TYPES)

PLOT_APPLICATION_ACTION_LABELS = (
    (CREATE, "Δημιουργία"),
    (DELETE, "Διαγραφή"),
    (VIEW, "Εμφάνιση"),
    (EDIT, "Επεξεργασία"),
    (SEND, "Αποστολή emails"),
)
PLOT_APPLICATION_ACTION_LABEL_MAP = dict(PLOT_APPLICATION_ACTION_LABELS)

PLOT_APPLICATION_SUBSECTIONS = (
    ("basic", "Στοιχεία αίτησης (Κοινότητα, Ημερομηνία υποβολής)"),
    ("section_1", "1. Προσωπικά στοιχεία αιτητή/αιτήτριας"),
    ("section_2", "2. Τόπος διαμονής αιτητή/αιτήτριας"),
    ("section_3", "3. Οικογενειακή κατάσταση"),
    ("section_4", "4. Επαγγελματική και άλλη κατάσταση αιτητή/αιτήτριας"),
    ("section_5", "5. Προσωπικά στοιχεία συζύγου / συμβίου"),
    ("section_6", "6. Επαγγελματική και άλλη κατάσταση συζύγου / συμβίου"),
    ("section_7", "7. Τέκνα αιτητή/τριας που ζουν στην ίδια κατοικία"),
    ("section_8", "8. Εισοδήματα"),
    ("section_9", "9. Άλλη ακίνητη ιδιοκτησία"),
    ("section_10", "10. Αποξένωση ακίνητης ιδιοκτησίας"),
    ("section_11", "11. Παραχώρηση άλλης κρατικής στεγαστικής βοήθειας"),
    ("section_12", "12. Υπεύθυνη δήλωση για τη δηλωθείσα ηλεκτρονική διεύθυνση"),
    ("sworn_declaration", "Ένορκη δήλωση"),
    ("documents", "Κατάλογος απαιτούμενων δικαιολογητικών εγγράφων"),
    ("eligibility", "Κατ' αρχήν έλεγχος κριτηρίων"),
    ("other_applications", "Άλλες αιτήσεις των ίδιων προσώπων"),
    ("email_history", "Ιστορικό απεσταλμένων email"),
    ("change_history", "Ιστορικό αλλαγών αίτησης"),
)
PLOT_APPLICATION_SUBSECTION_LABELS = dict(PLOT_APPLICATION_SUBSECTIONS)
PLOT_APPLICATION_SUBSECTION_CODES = tuple(code for code, _ in PLOT_APPLICATION_SUBSECTIONS)

CONFIGURABLE_FUNCTION_CODES = ("plot_applications",)


def plot_app_subsection_code(sub_code: str) -> str:
    return f"plot_app_{sub_code}"


PLOT_APPLICATION_SUBFUNCTION_CODES = tuple(
    plot_app_subsection_code(code) for code in PLOT_APPLICATION_SUBSECTION_CODES
)


@dataclass(frozen=True)
class AppFunction:
    code: str
    label: str
    actions: tuple
    parent: str | None = None
    # Case section key whose configurable title is shown instead of `label`.
    case_section: str | None = None
    description: str = ""


def _case_section(code, key, label, actions, description):
    return AppFunction(
        code=code,
        label=label,
        actions=actions,
        parent="cases",
        case_section=key,
        description=description,
    )


FUNCTIONS = (
    AppFunction(
        "reminders",
        "Υπενθυμίσεις",
        (VIEW,),
        description="Πίνακας υπενθυμίσεων στην αρχική και σελίδα υπενθυμίσεων (§Α.9.2).",
    ),
    AppFunction(
        "cases",
        "Αιτήσεις Κ.Σ. / Δ.Δ.",
        (VIEW, CREATE),
        description="Κατάλογος υποθέσεων, προβολή φακέλου και καταχώριση νέας υπόθεσης.",
    ),
    AppFunction(
        "case_history",
        "Ιστορικό ενεργειών υπόθεσης",
        (VIEW,),
        parent="cases",
        description="Συγκεντρωτικό ιστορικό του φακέλου (§Β.1.3).",
    ),
    _case_section("case_section_1", "1", "Ενότητα 1", (VIEW, EDIT), "1.1–1.3"),
    _case_section(
        "case_section_2",
        "2",
        "Ενότητα 2",
        (VIEW, CREATE, EDIT, DELETE, SEND),
        "2.1 έλεγχοι πληρότητας (γραμμές), 2.2 email ελλείψεων, 2.3 σχόλια.",
    ),
    _case_section(
        "case_section_3",
        "3",
        "Ενότητα 3",
        (VIEW, CREATE, EDIT, DELETE, SEND),
        "3.1 τεμάχια και αρχεία τους, email ανά τεμάχιο, 3.2, 3.3.",
    ),
    _case_section(
        "case_section_4",
        "4",
        "Ενότητα 4",
        (VIEW, CREATE, EDIT, DELETE, EXPORT),
        "4.1 αξιολόγηση ανά τεμάχιο, 4.2 υπηρεσίες (γραμμές), 4.3–4.6, PDF φόρμας πεδίου.",
    ),
    _case_section(
        "case_section_5",
        "5",
        "Ενότητα 5",
        (VIEW, CREATE, EDIT, DELETE),
        "Διαβουλεύσεις καταλληλότητας (γραμμές) και αρχεία τους.",
    ),
    _case_section(
        "case_section_6",
        "6",
        "Ενότητα 6",
        (VIEW, EDIT, DELETE, EXPORT),
        "6.1–6.5 σύνοψη, 6.6 απόφαση ανά τεμάχιο, 6.7 λήψη απόφασης από υπουργό, PDF πινάκων αξιολόγησης (επιλογή υποενοτήτων 6.1–6.6).",
    ),
    _case_section("case_section_7", "7", "Ενότητα 7", (VIEW, EDIT, DELETE), "7.1–7.7."),
    AppFunction(
        "case_completion",
        "Ολοκλήρωση αίτησης",
        (VIEW, EDIT),
        parent="cases",
        description="Έλεγχος ετοιμότητας και ολοκλήρωση αίτησης: δημιουργία οικοπέδων.",
    ),
    AppFunction(
        "plots",
        "Οικόπεδα",
        (VIEW, CREATE, EDIT, DELETE),
        description="Πίνακας ολοκληρωμένων οικοπέδων και χειροκίνητη καταχώριση.",
    ),
    AppFunction(
        "announcements",
        "Γνωστοποιήσεις",
        (VIEW, CREATE, EDIT, PUBLISH),
        description="9.1 νέα γνωστοποίηση, επεξεργασία, οριστικοποίηση και έκδοση ανακοίνωσης.",
    ),
    AppFunction(
        "plot_applications",
        "Αίτηση παραχώρησης οικοπέδου",
        (CREATE, DELETE, VIEW, EDIT, SEND),
        description="Νέα αίτηση πολίτη κατά το έντυπο Παραρτήματος 3 του Σχεδίου, με αυτόματο "
        "κατ' αρχήν έλεγχο κριτηρίων (Ενότ. 10, 20), προτεραιοποίηση (Ενότ. 11) και αποστολή email.",
    ),
    *(
        AppFunction(
            plot_app_subsection_code(sub_code),
            sub_label,
            (VIEW, EDIT),
            parent="plot_applications",
        )
        for sub_code, sub_label in PLOT_APPLICATION_SUBSECTIONS
    ),
    AppFunction(
        "plot_prioritization",
        "Προτεραιοποίηση αιτήσεων παραχώρησης οικοπέδου",
        (VIEW, EDIT, EXPORT),
        description="Κατάλογος προτεραιοποίησης των πλήρων αιτήσεων ανά Κοινότητα (Ενότ. 6, 11): "
        "αυτόματη κατάταξη, αλλαγή σειράς με drag and drop και εξαγωγή PDF.",
    ),
    AppFunction(
        "persons",
        "Άτομα",
        (VIEW, CREATE, EDIT, DELETE),
        description="Πίνακας καταχωρημένων ατόμων (10.3.1)· ο Αρ. Δελτίου Ταυτότητας δεν αλλάζει "
        "και άτομο με αιτήσεις δεν διαγράφεται.",
    ),
    AppFunction(
        "settings",
        "Ρυθμίσεις συστήματος",
        (VIEW,),
        description="Μενού Ρυθμίσεις και οθόνη επισκόπησης.",
    ),
    AppFunction("settings_catalogs", "Κατάλογος υπηρεσιών (4.2)", (VIEW, EDIT), parent="settings"),
    AppFunction("settings_branding", "Εμφάνιση εφαρμογής", (VIEW, EDIT), parent="settings"),
    AppFunction(
        "settings_menu_labels",
        "Ονόματα μενού",
        (VIEW, EDIT),
        parent="settings",
        description="Ονόματα των επιλογών του κύριου μενού (§Α.9.1).",
    ),
    AppFunction("settings_workflow", "Αριθμοδότηση, υπενθυμίσεις και όρια εισοδήματος", (VIEW, EDIT), parent="settings"),
    AppFunction(
        "settings_section_labels", "Τίτλοι ενοτήτων Κ.Σ. / Δ.Δ.", (VIEW, EDIT), parent="settings"
    ),
    AppFunction("settings_subsection_labels", "Τίτλοι υποενοτήτων", (VIEW, EDIT), parent="settings"),
    AppFunction(
        "settings_plot_application_labels",
        "Τίτλοι αίτησης παραχώρησης οικοπέδου",
        (VIEW, EDIT),
        parent="settings",
        description="Τίτλοι εμφάνισης των σταδίων της αίτησης παραχώρησης οικοπέδου (§Α.9.1).",
    ),
    AppFunction("settings_email", "Αποστολή email (SMTP)", (VIEW, EDIT), parent="settings"),
    AppFunction(
        "settings_users",
        "Χρήστες",
        (VIEW, CREATE, EDIT),
        parent="settings",
        description="Λογαριασμοί χρηστών και ανάθεση ρόλων.",
    ),
    AppFunction(
        "settings_roles",
        "Ρόλοι και δικαιώματα",
        (VIEW, CREATE, EDIT, DELETE),
        parent="settings",
        description="Ρόλοι και πρόσβαση ανά λειτουργία / υπολειτουργία.",
    ),
)

FUNCTIONS_BY_CODE = {function.code: function for function in FUNCTIONS}

CASE_SECTION_FUNCTIONS = {
    function.case_section: function.code for function in FUNCTIONS if function.case_section
}


def grant_key(code: str, action: str) -> str:
    return f"{code}:{action}"


def case_section_function(section_key: str) -> str:
    return CASE_SECTION_FUNCTIONS[section_key]


def function_label(function: AppFunction) -> str:
    """Catalog label; case sections add their configurable title (Ρυθμίσεις → Τίτλοι ενοτήτων)."""
    if not function.case_section:
        return function.label
    from cases.section_labels import get_case_section_label

    return f"{function.label} — {get_case_section_label(function.case_section)}"


def action_label_for(code: str, action: str) -> str:
    if code == "plot_applications" or code in PLOT_APPLICATION_SUBFUNCTION_CODES:
        return PLOT_APPLICATION_ACTION_LABEL_MAP.get(
            action, ACCESS_TYPE_LABELS.get(action, action)
        )
    return ACCESS_TYPE_LABELS.get(action, action)


def grant_label(key: str) -> str:
    code, _, action = key.partition(":")
    function = FUNCTIONS_BY_CODE.get(code)
    name = function_label(function) if function else code
    if function and function.parent == "plot_applications":
        parent = FUNCTIONS_BY_CODE["plot_applications"]
        name = f"{function_label(parent)} — {name}"
    return f"{name}: {action_label_for(code, action)}"
