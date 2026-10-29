"""Ρυθμίσεις εμφάνισης του πίνακα αιτήσεων παραχώρησης οικοπέδου (ορατές στήλες και κλειδωμένες στήλες)."""

from core.services import get_setting, set_setting

PLOT_APPLICATION_GRID_COLUMNS_SETTING_KEY = "plotApplicationGrid.columns"
PLOT_APPLICATION_GRID_LOCKED_SETTING_KEY = "plotApplicationGrid.lockedColumns"

PLOT_APPLICATION_GRID_COLUMNS: tuple[tuple[str, str], ...] = (
    ("protocol_number", "Αρ. Πρωτοκόλλου"),
    ("submitted_on", "Ημ. υποβολής"),
    ("community", "Κοινότητα"),
    ("applicant", "Αιτητής/τρια"),
    ("spouse", "Σύζυγος/Συμβίος"),
    ("family_status", "Οικογ. κατάσταση"),
    ("children", "Τέκνα"),
    ("stage", "Στάδιο αίτησης"),
    ("completeness", "Πληρότητα αίτησης"),
    ("documents_completeness", "Δικαιολογητικά"),
    ("eligibility", "Επιλεξιμότητα"),
    ("beneficiary", "Δικαιούχος"),
    ("plot_allocation", "Παραχώρηση οικοπέδου"),
)

PLOT_APPLICATION_GRID_COLUMN_CODES: tuple[str, ...] = tuple(
    code for code, _ in PLOT_APPLICATION_GRID_COLUMNS
)
PLOT_APPLICATION_GRID_COLUMN_LABELS: dict[str, str] = dict(PLOT_APPLICATION_GRID_COLUMNS)

DEFAULT_PLOT_APPLICATION_GRID_COLUMNS: list[str] = list(PLOT_APPLICATION_GRID_COLUMN_CODES)
DEFAULT_PLOT_APPLICATION_GRID_LOCKED_COLUMNS: int = 0


def get_plot_application_grid_columns() -> list[str]:
    raw = (get_setting(PLOT_APPLICATION_GRID_COLUMNS_SETTING_KEY, "") or "").strip()
    if not raw:
        return list(DEFAULT_PLOT_APPLICATION_GRID_COLUMNS)
    selected = {part.strip() for part in raw.split(",") if part.strip()}
    ordered = [code for code in PLOT_APPLICATION_GRID_COLUMN_CODES if code in selected]
    return ordered or list(DEFAULT_PLOT_APPLICATION_GRID_COLUMNS)


def save_plot_application_grid_columns(columns: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    selected = {str(code).strip() for code in (columns or ()) if str(code).strip()}
    ordered = [code for code in PLOT_APPLICATION_GRID_COLUMN_CODES if code in selected]
    if not ordered:
        ordered = list(DEFAULT_PLOT_APPLICATION_GRID_COLUMNS)
    set_setting(
        PLOT_APPLICATION_GRID_COLUMNS_SETTING_KEY,
        ",".join(ordered),
        "Ορατές στήλες πίνακα αιτήσεων παραχώρησης οικοπέδου",
    )
    return ordered


def get_plot_application_grid_locked_columns() -> int:
    raw = (
        get_setting(
            PLOT_APPLICATION_GRID_LOCKED_SETTING_KEY,
            str(DEFAULT_PLOT_APPLICATION_GRID_LOCKED_COLUMNS),
        )
        or ""
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PLOT_APPLICATION_GRID_LOCKED_COLUMNS
    return max(0, min(value, len(PLOT_APPLICATION_GRID_COLUMN_CODES)))


def save_plot_application_grid_locked_columns(count: int) -> int:
    try:
        value = int(count)
    except (TypeError, ValueError):
        value = DEFAULT_PLOT_APPLICATION_GRID_LOCKED_COLUMNS
    clamped = max(0, min(value, len(PLOT_APPLICATION_GRID_COLUMN_CODES)))
    set_setting(
        PLOT_APPLICATION_GRID_LOCKED_SETTING_KEY,
        str(clamped),
        "Κλειδωμένες στήλες από την αρχή στον πίνακα αιτήσεων παραχώρησης οικοπέδου",
    )
    return clamped
