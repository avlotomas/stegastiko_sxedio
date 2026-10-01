from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cases.models import Case, CompletenessCheck, SubmissionCycle, SubmissionCyclePublication
from core.models import ActionHistory, Communication
from core.services import get_setting, send_email

DEFICIENCY_EMAIL_SUBJECT_KEY = "deficiencyEmailSubject"
DEFICIENCY_EMAIL_SUBJECT_DEFAULT = "Ελλείψεις αίτησης Κ.Σ./Δ.Δ. — υπόθεση {case_number}"


@transaction.atomic
def generate_case_number(community, start_date=None) -> str:
    """1.1 Automatic case number, tied to district (through the community) and community."""
    community = community.__class__.objects.select_for_update().get(pk=community.pk)
    if not community.community_folder_code:
        raise ValidationError("Η Κοινότητα δεν έχει αριθμό φακέλου (communityFolderCode).")

    prefix = get_setting("caseNumberPrefix", "CASE")
    digits = int(get_setting("caseSequenceDigits", "2"))
    year = (start_date or timezone.localdate()).year
    existing_count = (
        Case.objects.select_for_update()
        .filter(community=community, start_date__year=year)
        .count()
    )
    sequence = str(existing_count + 1).zfill(digits)
    return f"{prefix}-{community.community_folder_code}-{year}-{sequence}"


def deficiency_email_subject(case: Case) -> str:
    """2.2 Predefined subject from the Settings; supports {case_number} and {community}."""
    template = get_setting(DEFICIENCY_EMAIL_SUBJECT_KEY, DEFICIENCY_EMAIL_SUBJECT_DEFAULT)
    return template.replace("{case_number}", case.case_number).replace(
        "{community}", case.community.name
    )


def send_deficiency_email(check: CompletenessCheck, subject: str, body: str) -> Communication:
    """2.2 Send the deficiencies to the 1.1 contact address and record the sending."""
    case = check.case
    if not case.contact_email:
        raise ValidationError("Η υπόθεση δεν έχει ηλεκτρονική διεύθυνση επικοινωνίας (1.1).")
    if not subject.strip():
        raise ValidationError("Το θέμα του email είναι κενό.")

    send_email(case.contact_email, subject, body)
    communication = Communication(
        content_type=ContentType.objects.get_for_model(CompletenessCheck),
        object_id=check.pk,
        recipient=case.contact_email,
        subject=subject,
        body=body,
        status="sent",
        sent_at=timezone.now(),
    )
    communication._section_ref = "2.2"
    communication.save()
    return communication


def case_communications(case: Case):
    case_type = ContentType.objects.get_for_model(Case)
    check_type = ContentType.objects.get_for_model(CompletenessCheck)
    return Communication.objects.filter(
        Q(content_type=case_type, object_id=case.pk)
        | Q(content_type=check_type, object_id__in=case.completeness_checks.values("pk"))
    ).order_by("-created_at", "-id")


def case_history(case: Case):
    """§Β.1.3 Aggregate history of the case folder, including its announcements.

    Announcements are shared between cases of the same community, so they carry no
    single case id and have to be pulled in by entity instead.
    """
    cycles = list(case.submission_cycles.values_list("pk", flat=True))
    queryset = ActionHistory.objects.filter(case_id=case.pk)
    if cycles:
        publications = SubmissionCyclePublication.objects.filter(
            submission_cycle_id__in=cycles
        ).values_list("pk", flat=True)
        queryset = queryset | ActionHistory.objects.filter(
            entity_type="SubmissionCycle", entity_id__in=[str(pk) for pk in cycles]
        )
        queryset = queryset | ActionHistory.objects.filter(
            entity_type="SubmissionCyclePublication",
            entity_id__in=[str(pk) for pk in publications],
        )
    return queryset.distinct().order_by("-timestamp", "-id")


def suitability_summary(case: Case) -> dict:
    """6.1-6.5 read-only summaries pulled from sections 1, 3, 4 and 5."""
    return {
        "priority_characteristics": case.priority_characteristics,
        "priority_documentation": case.priority_documentation,
        "land_plots": list(case.land_plots.all()),
        "utility_services": list(case.utility_services.select_related("service_type")),
        "consultations": list(
            case.consultations.filter(stage=case.consultations.model.Stage.SUITABILITY)
        ),
        "access_technical_evaluation": case.access_technical_evaluation,
        "state_land_remains_sufficient": case.get_state_land_remains_sufficient_display(),
        "state_land_comments": case.state_land_comments,
    }


def section8_completion(case: Case) -> dict:
    """8.8.2 Automatic completion check over the plots of the case."""
    parcels = list(case.parcels.all())
    all_valued = bool(parcels) and all(parcel.valuation_amount is not None for parcel in parcels)
    all_priced = bool(parcels) and all(parcel.disposal_price is not None for parcel in parcels)
    surveying_done = not case.is_new_division or bool(case.dls_response_date)
    return {
        "parcels_count": len(parcels),
        "all_valued": all_valued,
        "all_priced": all_priced,
        "surveying_done": surveying_done,
        "is_complete": all_valued and all_priced and surveying_done,
    }


def announcement_readiness(case: Case) -> dict:
    """9.4 Automatic readiness check that gates the announcement of Ενότητα 9."""
    completion = section8_completion(case)
    parcels = list(case.parcels.all())
    if case.is_new_division:
        latest_check = case.latest_infrastructure_check
        works_ready = bool(latest_check and latest_check.is_ready_for_submission_cycle)
        final_areas = bool(parcels) and all(
            parcel.final_area_sqm is not None for parcel in parcels
        )
    else:
        # §Α.3.3 An unallocated-plots case has no 8.1-8.7, so only 8.8 is checked.
        works_ready = True
        final_areas = bool(parcels)
    rows = [
        ("Απαιτούμενο στάδιο εργασιών (8.6)", works_ready),
        ("Τελική χωρομετρική εργασία (8.7)", completion["surveying_done"]),
        ("Τελικά εμβαδά (8.7)", final_areas),
        ("Καθορισμένη αξία / τιμή (8.8)", completion["all_valued"] and completion["all_priced"]),
    ]
    return {"rows": rows, "can_start": all(ready for _, ready in rows)}


def build_announcement_text(cycle: SubmissionCycle) -> str:
    """9.3 Automatic draft from the case data and the submission period.

    The exact approved wording is still pending (Ε-68), so this is a working draft
    that the operator previews and edits before finalising.
    """
    community = cycle.community
    case_numbers = ", ".join(case.case_number for case in cycle.cases.all()) or "—"
    return (
        "ΑΝΑΚΟΙΝΩΣΗ\n"
        "Στεγαστικό Σχέδιο Διάθεσης Οικοπέδων\n\n"
        f"Επαρχία: {community.district}\n"
        f"Κοινότητα / Δ.Δ.: {community.name}\n"
        f"Αρ. Φακέλου/ων υπόθεσης: {case_numbers}\n"
        f"Αριθμός διαθέσιμων οικοπέδων: {cycle.available_plots_count}\n\n"
        f"Ημερομηνία γνωστοποίησης: {cycle.announcement_date}\n"
        f"Έναρξη υποβολής αιτήσεων: {cycle.submission_start_date}\n"
        f"Λήξη υποβολής αιτήσεων: {cycle.submission_end_date}\n\n"
        "Καλούνται οι ενδιαφερόμενες οικογένειες να υποβάλουν αίτηση (Παράρτημα 3) "
        "εντός της ανωτέρω προθεσμίας, μαζί με τα απαιτούμενα δικαιολογητικά.\n"
    )


def publish_announcement(cycle: SubmissionCycle) -> SubmissionCycle:
    """9.3 Finalise and issue the announcement, gated by the 9.4 readiness check."""
    if cycle.is_published:
        raise ValidationError("Η ανακοίνωση έχει ήδη οριστικοποιηθεί.")
    if not cycle.announcement_text.strip():
        raise ValidationError("Δεν υπάρχει κείμενο ανακοίνωσης (9.3).")
    cases = list(cycle.cases.all())
    if not cases:
        raise ValidationError("Η γνωστοποίηση δεν έχει συνδεδεμένη υπόθεση (9.1).")
    blocked = [case.case_number for case in cases if not announcement_readiness(case)["can_start"]]
    if blocked:
        raise ValidationError(
            "Δεν πληρούται ο έλεγχος ετοιμότητας (9.4) για: " + ", ".join(blocked)
        )
    cycle.published_at = timezone.now()
    cycle.save()
    return cycle
