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
        submission_cycle__community=community, folder_number__startswith=base
    ).values_list("folder_number", flat=True)
    for number in numbers:
        suffix = number[len(base):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest


@transaction.atomic
def generate_folder_number(submission_cycle, offset: int = 0) -> str:
    """Next folder number (10.1.1): prefix + communityFolderCode + per-community sequence.

    The sequence continues from the highest number already issued (not the row count),
    so deleted applications never cause a number to be reused.
    """
    community = submission_cycle.community
    community = community.__class__.objects.select_for_update().get(pk=community.pk)
    base = _folder_number_base(community)
    digits = int(get_setting("folderSequenceDigits", "3"))
    sequence = _highest_folder_sequence(community, base) + 1 + offset
    return f"{base}{str(sequence).zfill(digits)}"


def _is_folder_number_conflict(exc: IntegrityError) -> bool:
    return "folder_number" in str(exc)


def save_with_new_folder_number(application: Application, submission_cycle) -> Application:
    """Assign a fresh folder number and insert; retry on a concurrent unique-number clash."""
    for attempt in range(FOLDER_NUMBER_MAX_ATTEMPTS):
        application.folder_number = generate_folder_number(submission_cycle, offset=attempt)
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
    applications = Application.objects.filter(Q(person=person) | Q(person2=person)).order_by(
        "-submitted_on", "-id"
    )
    return person, list(applications)


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
        f"{prefix}_refugee_identity_number": person.refugee_identity_number,
        f"{prefix}_citizenship_cypriot": person.citizenship_cypriot,
        f"{prefix}_citizenship_repatriated": person.citizenship_repatriated,
        f"{prefix}_citizenship_eu": person.citizenship_eu,
        f"{prefix}_citizenship_other": person.citizenship_other,
    }


def application_form_initial(application: Application) -> dict:
    initial = person_to_form_initial(application.person, "person1")
    if application.person2_id:
        initial.update(person_to_form_initial(application.person2, "person2"))
    return initial
