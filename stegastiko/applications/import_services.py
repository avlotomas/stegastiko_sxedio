"""Validate and persist application import (§9.5–9.6)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from applications.import_reader import ParsedImport, _parse_date, _parse_decimal
from applications.import_template import INCOME_COLUMNS
from applications.models import Application, DependentChild
from applications.person_identity import (
    application_person_fields_from_mapping,
    compare_person_with_payload,
    format_person_conflict_message,
    person_payload_from_mapping,
    _parse_yes_no,
)
from applications.rules import evaluate_eligibility
from applications.services import (
    ensure_person,
    save_with_new_folder_number,
    upsert_eligibility_checks,
)
from cases.models import SubmissionCycle
from core.models import Community

INCOME_ROLES = ("applicant", "spouse", "other_family")
INCOME_AMOUNT_KEYS = frozenset(
    {
        "income_annual_gross",
        "income_other_source_1",
        "income_other_source_2",
        "income_other_source_3",
        "income_total_gross",
    }
)

@dataclass
class ImportValidationResult:
    errors: list[str]
    warnings: list[str]
    person_conflicts: list[dict]


PERSON_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("first_name", "Όνομα"),
    ("last_name", "Επίθετο"),
    ("date_of_birth", "Ημερομηνία γέννησης"),
    ("birth_place", "Τόπος γέννησης"),
    ("birth_country", "Χώρα γέννησης"),
    ("parents_birth_place", "Τόπος γέννησης γονέων"),
    ("parents_birth_country", "Χώρα γέννησης γονέων"),
)


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _person_slot_checks(parsed: ParsedImport) -> list[dict]:
    conflicts = []
    for slot, prefix in (("Πρόσωπο 1", "p1"), ("Πρόσωπο 2", "p2")):
        identity = _text(parsed.fields.get(f"{prefix}_identity_number"))
        if not identity:
            if prefix == "p1":
                conflicts.append({"slot": slot, "error": "Υποχρεωτικό ΑΔΤ Πρόσωπου 1."})
            continue
        payload = person_payload_from_mapping(parsed.fields, prefix)
        missing = [
            label for name, label in PERSON_REQUIRED_FIELDS if not _text(payload.get(name))
        ]
        if missing:
            conflicts.append(
                {
                    "slot": slot,
                    "error": f"{slot} (ΑΔΤ {identity}): λείπουν υποχρεωτικά πεδία: "
                    + ", ".join(missing)
                    + ".",
                }
            )
            continue
        try:
            payload["date_of_birth"] = _parse_date(
                payload["date_of_birth"], f"{slot} — Ημερομηνία γέννησης"
            )
        except ValidationError as exc:
            conflicts.append({"slot": slot, "error": exc.messages[0]})
            continue
        result = compare_person_with_payload(identity, payload)
        if result.exists and result.has_differences:
            conflicts.append(
                {
                    "slot": slot,
                    "identity_number": identity,
                    "message": format_person_conflict_message(result),
                    "differences": [
                        {
                            "label": d.label,
                            "stored_value": d.stored_value,
                            "incoming_value": d.incoming_value,
                        }
                        for d in result.differences
                    ],
                }
            )
    return conflicts


def _community(parsed: ParsedImport) -> Community:
    """The community named by «community_code» in the metadata sheet."""
    code = _text(parsed.metadata.get("community_code"))
    if not code:
        raise ValidationError("Λείπει ο κωδικός Κοινότητας (community_code) στα μεταδεδομένα.")
    community = Community.objects.filter(community_folder_code=code).first()
    if community is None:
        raise ValidationError(f"Δεν βρέθηκε Κοινότητα με κωδικό «{code}».")
    return community


def _collect(errors: list[str], func, *args, **kwargs):
    """Run a parser; append its ValidationError message(s) instead of raising."""
    try:
        return func(*args, **kwargs)
    except ValidationError as exc:
        errors.extend(exc.messages)
        return None


def _validate_values(parsed: ParsedImport, errors: list[str]) -> None:
    fields = parsed.fields
    if _text(fields.get("submitted_on")):
        _collect(errors, _parse_date, fields.get("submitted_on"), "Ημερομηνία υποβολής")
    for key, label in (
        ("p1_residence_start", "Έναρξη διαμονής Π1"),
        ("p2_residence_start", "Έναρξη διαμονής Π2"),
    ):
        _collect(errors, _optional_date, fields.get(key), label)

    email = _text(fields.get("applicant_email"))
    if email:
        try:
            validate_email(email)
        except ValidationError:
            errors.append(f"Μη έγκυρο email αιτητή «{email}».")

    family_type = _text(fields.get("family_type"))
    if family_type and family_type not in Application.FamilyType.values:
        errors.append(f"Μη έγκυρος τύπος οικογένειας «{family_type}».")

    declared = _text(fields.get("declared_children_count"))
    if declared and not declared.isdigit():
        errors.append(f"Μη έγκυρος αριθμός τέκνων «{declared}» (αναμένεται ακέραιος).")

    for idx, child in enumerate(parsed.children, start=1):
        if not _text(child.get("child_first_name")) and not _text(child.get("child_last_name")):
            continue
        _collect(
            errors,
            _parse_date,
            child.get("child_date_of_birth"),
            f"Τέκνο {idx} — Ημερομηνία γέννησης",
        )
        status = _text(child.get("child_status"))
        if status and status not in DependentChild.ChildCategory.values:
            errors.append(f"Τέκνο {idx}: μη έγκυρη κατάσταση «{status}».")

    for idx, row in enumerate(parsed.income_rows, start=1):
        role = _text(row.get("income_role")).lower()
        if role not in INCOME_ROLES:
            errors.append(
                f"Εισοδήματα γραμμή {idx}: μη έγκυρος ρόλος «{_text(row.get('income_role'))}» "
                "(applicant | spouse | other_family)."
            )
        for key, label, _hint in INCOME_COLUMNS:
            if key in INCOME_AMOUNT_KEYS:
                _collect(errors, _parse_decimal, row.get(key), f"Εισοδήματα γραμμή {idx} — {label}")


def validate_import(parsed: ParsedImport) -> ImportValidationResult:
    """Collect every problem as a message; never raises for bad workbook content."""
    errors: list[str] = []
    warnings: list[str] = []

    if not _text(parsed.fields.get("p1_identity_number")):
        errors.append("Λείπει ΑΔΤ Προσώπου 1.")
    if not _text(parsed.fields.get("submitted_on")):
        errors.append("Λείπει ημερομηνία υποβολής.")
    if not _text(parsed.fields.get("applicant_email")):
        errors.append("Λείπει email αιτητή.")
    if not _text(parsed.fields.get("family_type")):
        errors.append("Λείπει τύπος οικογένειας.")

    community = _collect(errors, _community, parsed)
    if community and not SubmissionCycle.for_community(community).exists():
        errors.append("Δεν υπάρχει εκδοθείσα Γνωστοποίηση για την Κοινότητα (Ενότ. 4).")

    _validate_values(parsed, errors)

    person_conflicts = _person_slot_checks(parsed)
    for item in person_conflicts:
        if item.get("error"):
            errors.append(item["error"])
        elif item.get("message"):
            errors.append(item["message"])

    family_type = parsed.fields.get("family_type")
    if family_type == Application.FamilyType.SINGLE_PARENT.value and _text(
        parsed.fields.get("p2_identity_number")
    ):
        errors.append("Μονογονεϊκή οικογένεια: δεν πρέπει να δηλωθεί Πρόσωπο 2.")

    return ImportValidationResult(errors=errors, warnings=warnings, person_conflicts=person_conflicts)


def _income_totals(parsed: ParsedImport) -> tuple[Decimal, Decimal, Decimal]:
    """Sum income rows per role (several rows may exist for the same role)."""
    totals = {role: Decimal("0") for role in INCOME_ROLES}
    for row in parsed.income_rows:
        role = _text(row.get("income_role")).lower()
        if role not in totals:
            continue
        totals[role] += _parse_decimal(
            row.get("income_total_gross") or row.get("income_annual_gross")
        )
    return totals["applicant"], totals["spouse"], totals["other_family"]


def _residence_address(fields: dict) -> str:
    parts = [
        fields.get("p1_residence_street"),
        fields.get("p1_residence_number"),
        fields.get("p1_residence_apartment"),
    ]
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


@transaction.atomic
def save_import(parsed: ParsedImport) -> Application:
    validation = validate_import(parsed)
    if validation.errors:
        raise ValidationError(validation.errors)

    community = _community(parsed)

    p1_payload = person_payload_from_mapping(parsed.fields, "p1")
    p1_payload["date_of_birth"] = _parse_date(p1_payload["date_of_birth"])
    p1 = ensure_person(_text(parsed.fields.get("p1_identity_number")), p1_payload)

    p2 = None
    p2_id = _text(parsed.fields.get("p2_identity_number"))
    if p2_id:
        p2_payload = person_payload_from_mapping(parsed.fields, "p2")
        p2_payload["date_of_birth"] = _parse_date(p2_payload["date_of_birth"])
        p2 = ensure_person(p2_id, p2_payload)

    p1_income, p2_income, children_income = _income_totals(parsed)
    person_fields = application_person_fields_from_mapping(parsed.fields, "p1", "person1")
    if p2:
        person_fields.update(application_person_fields_from_mapping(parsed.fields, "p2", "person2"))

    application = Application(
        community=community,
        person=p1,
        person2=p2,
        submitted_on=_parse_date(parsed.fields.get("submitted_on")),
        family_type=parsed.fields.get("family_type"),
        family_type_other=str(parsed.fields.get("family_type_other") or ""),
        applicant_email=parsed.fields.get("applicant_email"),
        comments=_build_comments(parsed),
        declared_children_count=int(parsed.fields.get("declared_children_count") or 0),
        person1_residence_community=str(parsed.fields.get("p1_residence_community") or ""),
        person2_residence_community=str(parsed.fields.get("p2_residence_community") or ""),
        person1_residence_address=_residence_address(parsed.fields),
        person2_residence_address=str(parsed.fields.get("p2_residence_address") or ""),
        person1_residence_start=_optional_date(parsed.fields.get("p1_residence_start")),
        person2_residence_start=_optional_date(parsed.fields.get("p2_residence_start")),
        residence_category=str(parsed.fields.get("residence_category") or ""),
        person1_has_property=_parse_yes_no(parsed.fields.get("property_residence_yes")),
        person2_has_property=False,
        person1_non_alienation_clear=not _parse_yes_no(parsed.fields.get("property_alienation_yes")),
        person2_non_alienation_clear=True,
        person1_previous_aid_clear=not _parse_yes_no(parsed.fields.get("previous_housing_aid_yes")),
        person2_previous_aid_clear=True,
        person1_income=p1_income,
        person2_income=p2_income,
        children_income=children_income,
        completeness_updated_at=timezone.now(),
        **person_fields,
    )
    save_with_new_folder_number(application, community)

    for child in parsed.children:
        first = _text(child.get("child_first_name"))
        last = _text(child.get("child_last_name"))
        if not first and not last:
            continue
        DependentChild.objects.create(
            application=application,
            full_name=f"{first} {last}".strip(),
            date_of_birth=_parse_date(child.get("child_date_of_birth")),
            category=child.get("child_status") or DependentChild.ChildCategory.MINOR,
            is_recognized_dependent=_parse_yes_no(child.get("child_is_recognized_dependent")),
        )

    recognized = application.dependent_children.filter(is_recognized_dependent=True).count()
    application.recognized_dependent_children_count = recognized
    if not application.declared_children_count:
        application.declared_children_count = application.dependent_children.count()
    application.family_members_count = 1 + (1 if p2 else 0) + recognized
    results, *_ = evaluate_eligibility(application)
    application.save()

    upsert_eligibility_checks(application, results)
    return application


def _optional_date(value, label: str = "Ημερομηνία") -> date | None:
    if not value or str(value).strip() == "":
        return None
    return _parse_date(value, label)


def _build_comments(parsed: ParsedImport) -> str:
    parts = []
    base = _text(parsed.fields.get("comments"))
    if base:
        parts.append(base)
    protocol = _text(parsed.metadata.get("protocol_number"))
    if protocol:
        parts.append(f"Αρ. πρωτοκόλλησης: {protocol}")
    received = parsed.metadata.get("received_on")
    if received:
        parts.append(f"Ημ. παραλαβής: {received}")
    return "\n".join(parts)
