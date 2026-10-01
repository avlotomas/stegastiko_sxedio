"""Validate and persist application import (§9.5–9.6)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from applications.import_reader import ParsedImport, _parse_date, _parse_decimal
from applications.import_template import DEFAULT_SUBMISSION_CYCLE_ID
from applications.models import Application, DependentChild
from applications.person_identity import (
    compare_person_with_payload,
    format_person_conflict_message,
    person_payload_from_mapping,
    _parse_yes_no,
)
from applications.rules import evaluate_eligibility
from applications.services import ensure_person, generate_folder_number, upsert_eligibility_checks
from cases.models import SubmissionCycle

@dataclass
class ImportValidationResult:
    errors: list[str]
    warnings: list[str]
    person_conflicts: list[dict]


def _person_slot_checks(parsed: ParsedImport) -> list[dict]:
    conflicts = []
    for slot, prefix in (("Πρόσωπο 1", "p1"), ("Πρόσωπο 2", "p2")):
        identity = (parsed.fields.get(f"{prefix}_identity_number") or "").strip()
        if not identity:
            if prefix == "p1":
                conflicts.append({"slot": slot, "error": "Υποχρεωτικό ΑΔΤ Πρόσωπου 1."})
            continue
        payload = person_payload_from_mapping(parsed.fields, prefix)
        payload["date_of_birth"] = _parse_date(payload["date_of_birth"])
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


def validate_import(parsed: ParsedImport) -> ImportValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not (parsed.fields.get("p1_identity_number") or "").strip():
        errors.append("Λείπει ΑΔΤ Προσώπου 1.")
    if not parsed.fields.get("submitted_on"):
        errors.append("Λείπει ημερομηνία υποβολής.")
    if not parsed.fields.get("applicant_email"):
        errors.append("Λείπει email αιτητή.")
    if not parsed.fields.get("family_type"):
        errors.append("Λείπει τύπος οικογένειας.")

    cycle_id = int(parsed.metadata.get("submission_cycle_id") or DEFAULT_SUBMISSION_CYCLE_ID)
    cycle = SubmissionCycle.objects.filter(pk=cycle_id).select_related("community").first()
    if not cycle:
        errors.append(f"Δεν βρέθηκε κύκλος υποβολής id={cycle_id}.")
    else:
        code = (parsed.metadata.get("community_code") or "").strip()
        if code and cycle.community.community_folder_code != code:
            errors.append(
                f"Ο κωδικός κοινότητας «{code}» δεν ταιριάζει με τον κύκλο "
                f"({cycle.community.community_folder_code})."
            )
        if cycle.published_at is None:
            errors.append("Ο κύκλος υποβολής δεν είναι δημοσιευμένος.")

    person_conflicts = _person_slot_checks(parsed)
    for item in person_conflicts:
        if item.get("error"):
            errors.append(item["error"])
        elif item.get("message"):
            errors.append(item["message"])

    family_type = parsed.fields.get("family_type")
    if family_type == Application.FamilyType.SINGLE_PARENT.value and (
        parsed.fields.get("p2_identity_number") or ""
    ).strip():
        errors.append("Μονογονεϊκή οικογένεια: δεν πρέπει να δηλωθεί Πρόσωπο 2.")

    return ImportValidationResult(errors=errors, warnings=warnings, person_conflicts=person_conflicts)


def _income_totals(parsed: ParsedImport) -> tuple[Decimal, Decimal, Decimal]:
    p1 = p2 = children = Decimal("0")
    for row in parsed.income_rows:
        role = (row.get("income_role") or "").strip().lower()
        total = _parse_decimal(row.get("income_total_gross") or row.get("income_annual_gross"))
        if role == "applicant":
            p1 = total
        elif role == "spouse":
            p2 = total
        elif role == "other_family":
            children = total
    return p1, p2, children


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

    cycle_id = int(parsed.metadata.get("submission_cycle_id") or DEFAULT_SUBMISSION_CYCLE_ID)
    cycle = SubmissionCycle.objects.select_related("community").get(pk=cycle_id)

    p1_payload = person_payload_from_mapping(parsed.fields, "p1")
    p1_payload["date_of_birth"] = _parse_date(p1_payload["date_of_birth"])
    p1 = ensure_person((parsed.fields.get("p1_identity_number") or "").strip(), p1_payload)

    p2 = None
    p2_id = (parsed.fields.get("p2_identity_number") or "").strip()
    if p2_id:
        p2_payload = person_payload_from_mapping(parsed.fields, "p2")
        p2_payload["date_of_birth"] = _parse_date(p2_payload["date_of_birth"])
        p2 = ensure_person(p2_id, p2_payload)

    p1_income, p2_income, children_income = _income_totals(parsed)

    application = Application(
        submission_cycle=cycle,
        person=p1,
        person2=p2,
        folder_number="PENDING",
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
    )
    application.folder_number = generate_folder_number(cycle)
    application.save()

    for child in parsed.children:
        first = (child.get("child_first_name") or "").strip()
        last = (child.get("child_last_name") or "").strip()
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


def _optional_date(value) -> date | None:
    if not value or str(value).strip() == "":
        return None
    return _parse_date(value)


def _build_comments(parsed: ParsedImport) -> str:
    parts = []
    base = (parsed.fields.get("comments") or "").strip()
    if base:
        parts.append(base)
    protocol = (parsed.metadata.get("protocol_number") or "").strip()
    if protocol:
        parts.append(f"Αρ. πρωτοκόλλησης: {protocol}")
    received = parsed.metadata.get("received_on")
    if received:
        parts.append(f"Ημ. παραλαβής: {received}")
    return "\n".join(parts)
