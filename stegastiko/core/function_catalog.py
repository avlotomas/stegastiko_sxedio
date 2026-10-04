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


@dataclass(frozen=True)
class AppFunction:
    code: str
    label: str
    actions: tuple
    parent: str | None = None
    # Case section key (e.g. "7-plots") whose configurable title is shown instead of `label`.
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
        (VIEW, CREATE, EDIT, DELETE),
        "3.1 τεμάχια και αρχεία τους, 3.2, 3.3.",
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
        (VIEW, EDIT, EXPORT),
        "6.1–6.5 σύνοψη, 6.6 απόφαση ανά τεμάχιο, 6.7 λήψη απόφασης από υπουργό, PDF πινάκων αξιολόγησης (επιλογή υποενοτήτων 6.1–6.6).",
    ),
    _case_section("case_section_7", "7", "Ενότητα 7", (VIEW, EDIT), "7.1–7.6."),
    _case_section(
        "case_section_7_plots",
        "7-plots",
        "Ενότητα 7",
        (VIEW, EDIT),
        "7.8–7.9 χωράφια, οικόπεδα, αξία και τιμή.",
    ),
    _case_section(
        "case_section_8",
        "8",
        "Ενότητα 8",
        (VIEW, CREATE, EDIT, PUBLISH),
        "8.1 νέα γνωστοποίηση, 8.2–8.3 επεξεργασία, οριστικοποίηση και έκδοση ανακοίνωσης.",
    ),
    AppFunction(
        "applications",
        "Αιτήσεις Πολιτών",
        (VIEW, CREATE, EDIT),
        description="Κατάλογος και φάκελος αιτητή, νέα αίτηση, επεξεργασία (Ενότητα 10).",
    ),
    AppFunction(
        "application_import",
        "Εισαγωγή αίτησης από Excel",
        (IMPORT,),
        parent="applications",
        description="Αρχείο Παραρτήματος 3: προεπισκόπηση και αποθήκευση.",
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
    AppFunction("settings_workflow", "Αριθμοδότηση και υπενθυμίσεις", (VIEW, EDIT), parent="settings"),
    AppFunction(
        "settings_section_labels", "Τίτλοι ενοτήτων Κ.Σ. / Δ.Δ.", (VIEW, EDIT), parent="settings"
    ),
    AppFunction("settings_subsection_labels", "Τίτλοι υποενοτήτων", (VIEW, EDIT), parent="settings"),
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


def grant_label(key: str) -> str:
    code, _, action = key.partition(":")
    function = FUNCTIONS_BY_CODE.get(code)
    name = function_label(function) if function else code
    return f"{name}: {ACCESS_TYPE_LABELS.get(action, action)}"
