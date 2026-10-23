"""Αριθμητικές παράμετροι του ελέγχου κριτηρίων που διαβάζονται από τις Ρυθμίσεις.

Το ΥΠΕΣ μπορεί να τροποποιήσει το Σχέδιο (Ενότ. 19), γι' αυτό τα όρια δεν είναι hard-coded.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from core.services import get_setting


def age_at(reference_date: date, born_on: date) -> int:
    years = reference_date.year - born_on.year
    if (reference_date.month, reference_date.day) < (born_on.month, born_on.day):
        years -= 1
    return years


# Ενότ. 10.Στ income limits (€) by family size; overridable via SystemSetting (Ρυθμίσεις).
INCOME_LIMIT_SETTINGS: tuple[tuple[str, Decimal, str], ...] = (
    ("incomeLimitUpTo2Members", Decimal("45000"), "Όριο εισοδήματος 10.Στ — έως 2 μέλη (€)"),
    ("incomeLimit3Members", Decimal("50000"), "Όριο εισοδήματος 10.Στ — 3 μέλη (€)"),
    ("incomeLimit4Members", Decimal("55000"), "Όριο εισοδήματος 10.Στ — 4 μέλη (€)"),
    ("incomeLimit5PlusMembers", Decimal("65000"), "Όριο εισοδήματος 10.Στ — 5 ή περισσότερα μέλη (€)"),
)
INCOME_LIMIT_DEFAULTS: dict[str, Decimal] = {key: default for key, default, _ in INCOME_LIMIT_SETTINGS}


def income_limit_setting(key: str) -> Decimal:
    """Configured limit for `key`; falls back to the default if unset or invalid."""
    default = INCOME_LIMIT_DEFAULTS[key]
    raw = get_setting(key, str(default))
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return default
    if not value.is_finite() or value <= 0:
        return default
    return value
