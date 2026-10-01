"""Fixed Person fields (10.3.1) and comparison for import / manual entry."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from applications.models import Person

# field_name -> Greek label (UI / import errors)
PERSON_FIELD_LABELS: dict[str, str] = {
    "first_name": "Όνομα",
    "last_name": "Επίθετο",
    "identity_number": "Αρ. Δελτίου Ταυτότητας",
    "refugee_identity_number": "Αρ. Προσφυγικής Ταυτότητας",
    "citizenship_cypriot": "Υπηκοότητα — Κύπριος Πολίτης",
    "citizenship_repatriated": "Υπηκοότητα — Επαναπατρισθείς/είσα Κύπριος/α",
    "citizenship_eu": "Υπηκοότητα — Πολίτης κράτους μέλους ΕΕ",
    "citizenship_other": "Υπηκοότητα — Άλλη",
    "date_of_birth": "Ημερομηνία γέννησης",
    "birth_place": "Τόπος γέννησης",
    "birth_country": "Χώρα γέννησης",
    "parents_birth_place": "Τόπος γέννησης γονέων",
    "parents_birth_country": "Χώρα γέννησης γονέων",
}

PERSON_FIXED_FIELD_NAMES: tuple[str, ...] = tuple(PERSON_FIELD_LABELS.keys())


def _normalize_value(field_name: str, value: Any) -> Any:
    if field_name in ("citizenship_cypriot", "citizenship_repatriated", "citizenship_eu"):
        return bool(value)
    if field_name == "date_of_birth" and isinstance(value, str) and value:
        return date.fromisoformat(value)
    if field_name in ("refugee_identity_number", "citizenship_other"):
        return (value or "").strip()
    return value


def person_payload_from_form_prefix(form, prefix: str) -> dict:
    """Build Person fixed-field payload from ApplicationForm (person1 / person2)."""
    return {
        "first_name": form.cleaned_data[f"{prefix}_first_name"],
        "last_name": form.cleaned_data[f"{prefix}_last_name"],
        "identity_number": (form.cleaned_data[f"{prefix}_identity_number"] or "").strip(),
        "refugee_identity_number": (form.cleaned_data.get(f"{prefix}_refugee_identity_number") or "").strip(),
        "citizenship_cypriot": form.cleaned_data.get(f"{prefix}_citizenship_cypriot", False),
        "citizenship_repatriated": form.cleaned_data.get(f"{prefix}_citizenship_repatriated", False),
        "citizenship_eu": form.cleaned_data.get(f"{prefix}_citizenship_eu", False),
        "citizenship_other": (form.cleaned_data.get(f"{prefix}_citizenship_other") or "").strip(),
        "date_of_birth": form.cleaned_data[f"{prefix}_date_of_birth"],
        "birth_place": form.cleaned_data[f"{prefix}_birth_place"],
        "birth_country": form.cleaned_data[f"{prefix}_birth_country"],
        "parents_birth_place": form.cleaned_data[f"{prefix}_parents_birth_place"],
        "parents_birth_country": form.cleaned_data[f"{prefix}_parents_birth_country"],
    }


def person_payload_from_mapping(data: dict, prefix: str) -> dict:
    """Build payload from Excel/import keys (p1_*, p2_*)."""
    return {
        "first_name": data.get(f"{prefix}_first_name", ""),
        "last_name": data.get(f"{prefix}_last_name", ""),
        "identity_number": (data.get(f"{prefix}_identity_number") or "").strip(),
        "refugee_identity_number": (data.get(f"{prefix}_refugee_id") or "").strip(),
        "citizenship_cypriot": _parse_yes_no(data.get(f"{prefix}_citizenship_cypriot")),
        "citizenship_repatriated": _parse_yes_no(data.get(f"{prefix}_citizenship_repatriated")),
        "citizenship_eu": _parse_yes_no(data.get(f"{prefix}_citizenship_eu")),
        "citizenship_other": (data.get(f"{prefix}_citizenship_other") or "").strip(),
        "date_of_birth": data.get(f"{prefix}_date_of_birth"),
        "birth_place": data.get(f"{prefix}_birth_place", ""),
        "birth_country": data.get(f"{prefix}_birth_country", ""),
        "parents_birth_place": data.get(f"{prefix}_parents_birth_place", ""),
        "parents_birth_country": data.get(f"{prefix}_parents_birth_country", ""),
    }


def _parse_yes_no(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("ναι", "yes", "true", "1")


def _display_value(field_name: str, value: Any) -> str:
    if value is None:
        return ""
    if field_name in ("citizenship_cypriot", "citizenship_repatriated", "citizenship_eu"):
        return "Ναι" if value else "Όχι"
    if field_name == "date_of_birth" and isinstance(value, date):
        return value.isoformat()
    return str(value)


@dataclass
class PersonFieldDifference:
    field: str
    label: str
    stored_value: str
    incoming_value: str


@dataclass
class PersonCompareResult:
    exists: bool
    person_id: int | None
    identity_number: str
    differences: list[PersonFieldDifference]

    @property
    def has_differences(self) -> bool:
        return bool(self.differences)


def compare_person_with_payload(identity_number: str, payload: dict) -> PersonCompareResult:
    identity_number = (identity_number or "").strip()
    person = Person.objects.filter(identity_number=identity_number).first()
    if not person:
        return PersonCompareResult(
            exists=False,
            person_id=None,
            identity_number=identity_number,
            differences=[],
        )

    differences: list[PersonFieldDifference] = []
    for field_name in PERSON_FIXED_FIELD_NAMES:
        if field_name == "identity_number":
            incoming = identity_number
        else:
            incoming = _normalize_value(field_name, payload.get(field_name))
        stored = getattr(person, field_name)
        if field_name == "date_of_birth" and isinstance(incoming, str) and incoming:
            incoming = date.fromisoformat(incoming)
        if stored != incoming:
            differences.append(
                PersonFieldDifference(
                    field=field_name,
                    label=PERSON_FIELD_LABELS[field_name],
                    stored_value=_display_value(field_name, stored),
                    incoming_value=_display_value(field_name, incoming),
                )
            )

    return PersonCompareResult(
        exists=True,
        person_id=person.id,
        identity_number=identity_number,
        differences=differences,
    )


def format_person_conflict_message(result: PersonCompareResult) -> str:
    if not result.exists or not result.has_differences:
        return ""
    labels = ", ".join(d.label for d in result.differences)
    details = "; ".join(
        f"{d.label}: καταχωρημένο «{d.stored_value}», στο αρχείο «{d.incoming_value}»"
        for d in result.differences
    )
    return (
        f"Το ΑΔΤ {result.identity_number} αντιστοιχεί σε **υπάρχον άτομο** στο σύστημα. "
        f"Τα πεδία {labels} διαφέρουν. {details}"
    ).replace("**", "")
