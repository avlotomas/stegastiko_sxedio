"""Configurable labels of the main menu (§Α.9.1)."""

from core.services import get_setting, set_setting

MENU_LABEL_SETTING_PREFIX = "menuLabel."

# Order matches the menu: top-level entries followed by their sub-entries.
MENU_LABEL_FIELDS = (
    ("home", "Αρχική", "Αρχική"),
    ("applications", "Αιτήσεις", "Αιτήσεις (ομάδα μενού)"),
    ("applications_division", "Διαχωρισμού", "Αιτήσεις → αιτήσεις Κ.Σ. / Δ.Δ. για διαχωρισμό"),
    ("applications_plot", "Απόκτησης οικοπέδου", "Αιτήσεις → αιτήσεις πολιτών για οικόπεδο"),
    (
        "applications_plot_appendix3",
        "Παραχώρησης οικοπέδου (Παρ. 3)",
        "Αιτήσεις → νέα αίτηση παραχώρησης οικοπέδου (έντυπο Παραρτήματος 3)",
    ),
    ("persons", "Άτομα", "Άτομα (καταχωρημένα πρόσωπα αιτήσεων)"),
    ("plots", "Οικόπεδα", "Οικόπεδα (ολοκληρωμένα οικόπεδα)"),
    ("announcements", "Γνωστοποιήσεις", "Γνωστοποιήσεις έναρξης αιτήσεων"),
    ("reminders", "Υπενθυμίσεις", "Υπενθυμίσεις"),
    ("settings", "Ρυθμίσεις", "Ρυθμίσεις (ομάδα μενού)"),
    ("settings_basic", "Βασικές", "Ρυθμίσεις → βασικές ρυθμίσεις εφαρμογής"),
    ("settings_system", "Συστήματος", "Ρυθμίσεις → τεχνική διαχείριση συστήματος"),
)

DEFAULT_MENU_LABELS = {key: default for key, default, _ in MENU_LABEL_FIELDS}


def menu_label_setting_key(key: str) -> str:
    return f"{MENU_LABEL_SETTING_PREFIX}{key}"


def get_menu_labels() -> dict[str, str]:
    labels = {}
    for key, default in DEFAULT_MENU_LABELS.items():
        value = get_setting(menu_label_setting_key(key), "").strip()
        labels[key] = value or default
    return labels


def save_menu_label(key: str, label: str, description: str) -> None:
    set_setting(menu_label_setting_key(key), label.strip(), f"Όνομα μενού: {description}")
