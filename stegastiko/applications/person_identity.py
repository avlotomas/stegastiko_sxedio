"""Fixed Person fields (10.3.1) and comparison for import / manual entry."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from applications.models import Person

# Fields that never change over time and therefore live on Person (10.3.1).
# field_name -> Greek label (UI / import errors)
PERSON_FIELD_LABELS: dict[str, str] = {
    "first_name": "Όνομα",
    "last_name": "Επίθετο",
    "identity_number": "Αρ. Δελτίου Ταυτότητας",
    "date_of_birth": "Ημερομηνία γέννησης",
    "birth_place": "Τόπος γέννησης",
    "birth_country": "Χώρα γέννησης",
    "parents_birth_place": "Τόπος γέννησης γονέων",
    "parents_birth_country": "Χώρα γέννησης γονέων",
}

PERSON_FIXED_FIELD_NAMES: tuple[str, ...] = tuple(PERSON_FIELD_LABELS.keys())

# Per-person fields declared on each application (Παράρτημα 3); stored as
# Application.person1_<name> / person2_<name>.
APPLICATION_PERSON_FIELD_NAMES: tuple[str, ...] = (
    "refugee_identity_number",
    "citizenship_cypriot",
    "citizenship_repatriated",
    "citizenship_eu",
    "citizenship_other",
)


def _normalize_value(field_name: str, value: Any) -> Any:
    if field_name == "date_of_birth" and isinstance(value, str) and value:
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            # Unparsable incoming date: keep the text so it is reported as a difference.
            return value
    if isinstance(value, str):
        return value.strip()
    return value


def person_payload_from_form_prefix(form, prefix: str) -> dict:
    """Build Person fixed-field payload from ApplicationForm (person1 / person2)."""
    return {
        "first_name": form.cleaned_data[f"{prefix}_first_name"],
        "last_name": form.cleaned_data[f"{prefix}_last_name"],
        "identity_number": (form.cleaned_data[f"{prefix}_identity_number"] or "").strip(),
        "date_of_birth": form.cleaned_data[f"{prefix}_date_of_birth"],
        "birth_place": form.cleaned_data[f"{prefix}_birth_place"],
        "birth_country": form.cleaned_data[f"{prefix}_birth_country"],
        "parents_birth_place": form.cleaned_data[f"{prefix}_parents_birth_place"],
        "parents_birth_country": form.cleaned_data[f"{prefix}_parents_birth_country"],
    }


def person_payload_from_mapping(data: dict, prefix: str) -> dict:
    """Build payload from Excel/import keys (p1_*, p2_*)."""

    def text(key: str) -> str:
        value = data.get(f"{prefix}_{key}")
        return "" if value is None else str(value).strip()

    return {
        "first_name": text("first_name"),
        "last_name": text("last_name"),
        "identity_number": text("identity_number"),
        "date_of_birth": data.get(f"{prefix}_date_of_birth"),
        "birth_place": text("birth_place"),
        "birth_country": text("birth_country"),
        "parents_birth_place": text("parents_birth_place"),
        "parents_birth_country": text("parents_birth_country"),
    }


def application_person_fields_from_mapping(data: dict, prefix: str, slot: str) -> dict:
    """Excel/import keys (p1_*, p2_*) -> Application.person1_* / person2_* kwargs."""

    def text(key: str) -> str:
        value = data.get(f"{prefix}_{key}")
        return "" if value is None else str(value).strip()

    return {
        f"{slot}_refugee_identity_number": text("refugee_id"),
        f"{slot}_citizenship_cypriot": _parse_yes_no(data.get(f"{prefix}_citizenship_cypriot")),
        f"{slot}_citizenship_repatriated": _parse_yes_no(data.get(f"{prefix}_citizenship_repatriated")),
        f"{slot}_citizenship_eu": _parse_yes_no(data.get(f"{prefix}_citizenship_eu")),
        f"{slot}_citizenship_other": text("citizenship_other"),
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
