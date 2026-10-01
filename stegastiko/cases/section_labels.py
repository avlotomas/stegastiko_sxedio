"""Configurable display titles for Κ.Σ./Δ.Δ. case sections (sidebar, page heading, folder view)."""

from core.services import get_setting, set_setting

CASE_SECTION_LABEL_SETTING_PREFIX = "caseSectionLabel."

# Default labels match the built-in section actions (§Α.6).
DEFAULT_CASE_SECTION_LABELS = {
    "1": "Βασικά στοιχεία και προτεραιότητα",
    "2": "Έλεγχος πληρότητας",
    "3": "Στοιχεία τεμαχίων",
    "4": "Τεχνική αξιολόγηση",
    "5": "Διαβουλεύσεις καταλληλότητας",
    "6": "Απόφαση καταλληλότητας",
    "7": "Σύσταση προς Υπουργό",
    "8": "Διαχωρισμός (8.1–8.6)",
    "8-plots": "Οικόπεδα, αξία και τιμή (8.7–8.8)",
    "9": "Γνωστοποίηση έναρξης αιτήσεων",
}

CASE_SECTION_LABEL_KEYS = tuple(DEFAULT_CASE_SECTION_LABELS.keys())


def case_section_label_setting_key(section_key: str) -> str:
    return f"{CASE_SECTION_LABEL_SETTING_PREFIX}{section_key}"


def get_case_section_label(section_key: str) -> str:
    return get_setting(
        case_section_label_setting_key(section_key),
        DEFAULT_CASE_SECTION_LABELS.get(section_key, section_key),
    )


def case_section_number(section_key: str) -> str:
    """Specification number of a section key (e.g. 8-plots → 8)."""
    return section_key.split("-", 1)[0]


def case_section_heading(section_key: str) -> str:
    """Numbered heading of a section on the read-only case folder (e.g. «2. Έλεγχος πληρότητας»)."""
    return f"{case_section_number(section_key)}. {get_case_section_label(section_key)}"


def save_case_section_label(section_key: str, label: str) -> None:
    description = (
        f"Τίτλος εμφάνισης Ενότητας {section_key} "
        "(πλοήγηση, κεφαλίδα οθόνης και προβολή φακέλου)"
    )
    set_setting(case_section_label_setting_key(section_key), label.strip(), description)


def form_field_name_for_section_label(section_key: str) -> str:
    """Safe HTML form field name for a section key (e.g. 8-plots → section_label_8__plots)."""
    return "section_label_" + section_key.replace("-", "__")


def section_key_from_label_form_field(field_name: str) -> str:
    if not field_name.startswith("section_label_"):
        raise ValueError(field_name)
    return field_name.removeprefix("section_label_").replace("__", "-")
