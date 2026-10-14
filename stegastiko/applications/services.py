from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from applications.models import Application, EligibilityCheck, Person
from applications.person_identity import (
    PERSON_FIXED_FIELD_NAMES,
    compare_person_with_payload,
    format_person_conflict_message,
    person_payload_from_form_prefix,
)
from core.services import get_setting

# Re-export for views
__all__ = [
    "ensure_person",
    "generate_folder_number",
    "save_with_new_folder_number",
    "get_setting",
    "person_payload_from_form_prefix",
    "previous_applications_for_identity",
    "search_persons",
    "application_prefill",
]


def ensure_person(identity_number: str, payload: dict) -> Person:
    identity_number = (identity_number or "").strip()
    if not identity_number:
        raise ValidationError("Απαιτείται ΑΔΤ.")

    compare_payload = {**payload, "identity_number": identity_number}
    result = compare_person_with_payload(identity_number, compare_payload)
    if result.exists and result.has_differences:
        raise ValidationError(format_person_conflict_message(result))

    create_fields = {
        name: payload[name]
        for name in PERSON_FIXED_FIELD_NAMES
        if name != "identity_number"
    }
    person = Person.objects.filter(identity_number=identity_number).first()
    if person is None:
        return Person.objects.create(identity_number=identity_number, **create_fields)
    return person


FOLDER_NUMBER_MAX_ATTEMPTS = 5


def _folder_number_base(community) -> str:
    if not community.community_folder_code:
        raise ValidationError("Η κοινότητα δεν έχει communityFolderCode.")
    prefix = get_setting("applicationFolderPrefix", "12")
    return f"{prefix}{community.community_folder_code}"


def _highest_folder_sequence(community, base: str) -> int:
    """Largest numeric suffix already used by this community under `base` (0 if none)."""
    highest = 0
    numbers = Application.objects.filter(
        community=community, folder_number__startswith=base
    ).values_list("folder_number", flat=True)
    for number in numbers:
        suffix = number[len(base):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest


@transaction.atomic
def generate_folder_number(community, offset: int = 0) -> str:
    """Next folder number (10.1.1): prefix + communityFolderCode + per-community sequence.

    The sequence continues from the highest number already issued (not the row count),
    so deleted applications never cause a number to be reused.
    """
    community = community.__class__.objects.select_for_update().get(pk=community.pk)
    base = _folder_number_base(community)
    digits = int(get_setting("folderSequenceDigits", "3"))
    sequence = _highest_folder_sequence(community, base) + 1 + offset
    return f"{base}{str(sequence).zfill(digits)}"


def _is_folder_number_conflict(exc: IntegrityError) -> bool:
    return "folder_number" in str(exc)


def save_with_new_folder_number(application: Application, community) -> Application:
    """Assign a fresh folder number and insert; retry on a concurrent unique-number clash."""
    for attempt in range(FOLDER_NUMBER_MAX_ATTEMPTS):
        application.folder_number = generate_folder_number(community, offset=attempt)
        try:
            with transaction.atomic():
                application.save()
        except IntegrityError as exc:
            if not _is_folder_number_conflict(exc):
                raise
            application.pk = None
            application._state.adding = True
            continue
        return application
    raise ValidationError(
        "Δεν ήταν δυνατή η απόδοση μοναδικού Αρ. Φακέλου Αιτητή. Δοκιμάστε ξανά."
    )


def upsert_eligibility_checks(application: Application, results: dict) -> None:
    person2_exists = application.person2_id is not None
    for criterion, overall in results.items():
        check, _ = EligibilityCheck.objects.get_or_create(
            application=application,
            criterion=criterion,
            defaults={"overall_result": overall},
        )
        check.overall_result = overall
        check.person1_result = overall
        check.person2_result = overall if person2_exists else ""
        check.save()


def previous_applications_for_identity(identity_number: str):
    person = Person.objects.filter(identity_number=identity_number).first()
    if not person:
        return person, []
    applications = (
        Application.objects.filter(Q(person=person) | Q(person2=person))
        .select_related("community", "person", "person2")
        .order_by("-submitted_on", "-id")
    )
    return person, list(applications)


PERSON_SEARCH_MIN_LENGTH = 2
PERSON_SEARCH_LIMIT = 10


def search_persons(query: str):
    """ΑΔΤ prefix or surname/name match, used to pick an existing Person on the form."""
    query = (query or "").strip()
    if len(query) < PERSON_SEARCH_MIN_LENGTH:
        return []
    persons = Person.objects.filter(
        Q(identity_number__istartswith=query)
        | Q(last_name__icontains=query)
        | Q(first_name__icontains=query)
    ).order_by("identity_number")
    return list(persons[:PERSON_SEARCH_LIMIT])


# Application fields that describe one of the two persons (person1_* / person2_*).
APPLICATION_SLOT_FIELDS: tuple[str, ...] = (
    "refugee_identity_number",
    "citizenship_cypriot",
    "citizenship_repatriated",
    "citizenship_eu",
    "citizenship_other",
    "relationship",
    "residence_community",
    "residence_address",
    "residence_start",
    "has_property",
    "non_alienation_clear",
    "previous_aid_clear",
    "income",
)

# Application fields that describe the family as a whole.
APPLICATION_FAMILY_FIELDS: tuple[str, ...] = (
    "family_type",
    "family_type_other",
    "applicant_email",
    "residence_category",
    "children_income",
)


def _json_value(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    return str(value)


def application_prefill(source: Application, person: Person, target_prefix: str) -> dict:
    """Variable fields of `person` from a previous application, keyed for the new form.

    The person may have been Πρόσωπο 2 in `source` and be Πρόσωπο 1 now (or vice versa),
    so the slot fields are read from the slot the person actually held. Family-level
    fields and the partner are only suggested when filling Πρόσωπο 1.
    """
    source_prefix = "person1" if source.person_id == person.id else "person2"
    other_prefix = "person2" if source_prefix == "person1" else "person1"
    prefill = {
        f"{target_prefix}_{name}": _json_value(getattr(source, f"{source_prefix}_{name}"))
        for name in APPLICATION_SLOT_FIELDS
    }
    partner = None
    if target_prefix == "person1":
        prefill.update(
            {name: _json_value(getattr(source, name)) for name in APPLICATION_FAMILY_FIELDS}
        )
        partner = source.person2 if source_prefix == "person1" else source.person
        if partner is not None:
            prefill.update(
                {
                    f"person2_{name}": _json_value(getattr(source, f"{other_prefix}_{name}"))
                    for name in APPLICATION_SLOT_FIELDS
                }
            )
    return {
        "fields": prefill,
        "partner_identity_number": partner.identity_number if partner else "",
        "children": [
            {
                "full_name": child.full_name,
                "date_of_birth": child.date_of_birth.isoformat(),
                "category": child.category,
                "is_recognized_dependent": child.is_recognized_dependent,
            }
            for child in source.dependent_children.all()
        ]
        if target_prefix == "person1"
        else [],
    }


def person_to_form_initial(person: Person, prefix: str) -> dict:
    """Map stored Person fields onto ApplicationForm person1_/person2_ keys."""
    return {
        f"{prefix}_identity_number": person.identity_number,
        f"{prefix}_first_name": person.first_name,
        f"{prefix}_last_name": person.last_name,
        f"{prefix}_date_of_birth": person.date_of_birth,
        f"{prefix}_birth_place": person.birth_place,
        f"{prefix}_birth_country": person.birth_country,
        f"{prefix}_parents_birth_place": person.parents_birth_place,
        f"{prefix}_parents_birth_country": person.parents_birth_country,
    }


def application_form_initial(application: Application) -> dict:
    initial = person_to_form_initial(application.person, "person1")
    if application.person2_id:
        initial.update(person_to_form_initial(application.person2, "person2"))
    return initial
