from django.core.exceptions import ValidationError
from django.db import transaction
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


@transaction.atomic
def generate_folder_number(submission_cycle) -> str:
    community = submission_cycle.community
    community = community.__class__.objects.select_for_update().get(pk=community.pk)
    if not community.community_folder_code:
        raise ValidationError("Η κοινότητα δεν έχει communityFolderCode.")

    prefix = get_setting("applicationFolderPrefix", "12")
    digits = int(get_setting("folderSequenceDigits", "3"))
    existing_count = Application.objects.select_for_update().filter(
        submission_cycle__community=community
    ).count()
    sequence = str(existing_count + 1).zfill(digits)
    return f"{prefix}{community.community_folder_code}{sequence}"


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
