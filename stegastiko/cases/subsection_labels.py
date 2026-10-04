"""Configurable display titles for Κ.Σ./Δ.Δ. case subsections (edit screens and folder view)."""

from core.services import get_setting, set_setting

CASE_SUBSECTION_LABEL_SETTING_PREFIX = "caseSubsectionLabel."

# Display number when the setting key is not the same as the visible reference (e.g. two 8.7 blocks).
SUBSECTION_HEADING_NUMBERS: dict[str, str] = {
    "7.8-parcels": "7.8",
    "7.8-7.9-mapping": "7.8 / 7.9",
}

DEFAULT_CASE_SUBSECTION_LABELS: dict[str, str] = {
    "1.1": "Βασικά στοιχεία",
    "1.2": "Χαρακτηριστικά Κοινότητας για σκοπούς προτεραιότητας νέου διαχωρισμού",
    "1.3": "Σχόλια / Παρατηρήσεις Ενότητας 1",
    "2.1": "Έλεγχοι πληρότητας",
    "2.2": "Ελλείψεις και επικοινωνία",
    "2.3": "Σχόλια / Παρατηρήσεις",
    "3.1": "Πίνακας τεμαχίων",
    "3.2": "Έλεγχος επάρκειας κρατικής γης",
    "3.3": "Σχόλια / Παρατηρήσεις Ενότητας 3",
    "4.1": "Τεχνική αξιολόγηση ανά τεμάχιο",
    "4.2": "Υπηρεσίες κοινής ωφέλειας",
    "4.3": "Πρόσβαση",
    "4.4": "Επισυναπτόμενα αρχεία",
    "4.5": "Σχόλια / Παρατηρήσεις Ενότητας 4",
    "4.6": "Στοιχεία επίσκεψης μηχανικού",
    "5": "Διαβουλεύσεις",
    "6.1": "Συνοπτική εικόνα προτεραιότητας Κοινότητας",
    "6.2": "Τεχνική αξιολόγηση ανά τεμάχιο",
    "6.3": "Συνοπτικός πίνακας υπηρεσιών κοινής ωφέλειας",
    "6.4": "Συνοπτικός πίνακας διαβουλεύσεων",
    "6.5": "Έλεγχος επάρκειας κρατικής γης",
    "6.6": "Απόφαση καταλληλότητας ανά τεμάχιο",
    "6.7": "Λήψη απόφασης από υπουργό",
    "7.1": "Ανάθεση μελέτης",
    "7.2": "Σχεδιασμός διαχωρισμού",
    "7.3": "Στοιχεία αίτησης για έγκριση σχεδιασμού",
    "7.4": "Κατασκευαστικά Σχέδια και Διαβουλεύσεις",
    "7.6": "Έλεγχος υποδομών",
    "7.7": "Διαγωνισμός, ανάθεση και πορεία εργασιών",
    "7.8": "Αίτηση στο ΤΚΧ",
    "7.8-parcels": "Χωράφια",
    "7.8-7.9-mapping": "Πίνακας αντιστοίχισης οικοπέδων",
    "7.9.1": "Παραπομπές προς ΤΚΧ",
    "7.9.2": "Έλεγχος ολοκλήρωσης (αυτόματο)",
    "8.1": "Βασικά στοιχεία",
    "8.4": "Έλεγχος ετοιμότητας (αυτόματο)",
}

CASE_SUBSECTION_LABEL_KEYS = tuple(DEFAULT_CASE_SUBSECTION_LABELS.keys())


def case_subsection_label_setting_key(subsection_key: str) -> str:
    return f"{CASE_SUBSECTION_LABEL_SETTING_PREFIX}{subsection_key}"


def get_case_subsection_label(subsection_key: str) -> str:
    return get_setting(
        case_subsection_label_setting_key(subsection_key),
        DEFAULT_CASE_SUBSECTION_LABELS.get(subsection_key, subsection_key),
    )


def case_subsection_heading(subsection_key: str) -> str:
    """Numbered heading (e.g. «3.2 Έλεγχος επάρκειας κρατικής γης»)."""
    number = SUBSECTION_HEADING_NUMBERS.get(subsection_key, subsection_key)
    return f"{number} {get_case_subsection_label(subsection_key)}"


def save_case_subsection_label(subsection_key: str, label: str) -> None:
    description = (
        f"Τίτλος εμφάνισης υποενότητας {subsection_key} "
        "(οθόνες επεξεργασίας και προβολή φακέλου)"
    )
    set_setting(case_subsection_label_setting_key(subsection_key), label.strip(), description)


def form_field_name_for_subsection_label(subsection_key: str) -> str:
    """Safe HTML form field name (e.g. 3.2 → subsection_label_3__2)."""
    return "subsection_label_" + subsection_key.replace(".", "__")


def subsection_key_from_label_form_field(field_name: str) -> str:
    if not field_name.startswith("subsection_label_"):
        raise ValueError(field_name)
    return field_name.removeprefix("subsection_label_").replace("__", ".")
