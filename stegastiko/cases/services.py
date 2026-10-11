from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from cases import section_refs as refs
from cases.models import (
    ApprovedDesignPlot,
    Case,
    CommunicationStatus,
    CompletenessCheck,
    Consultation,
    LandPlot,
    MinistryDecisionRound,
    SubmissionCycle,
    SubmissionCyclePublication,
)
from core.models import ActionHistory, Attachment, Communication
from core.services import get_setting, require_smtp_configured, send_email

DEFICIENCY_EMAIL_SUBJECT_KEY = "deficiencyEmailSubject"
DEFICIENCY_EMAIL_SUBJECT_DEFAULT = "Ελλείψεις αίτησης Κ.Σ./Δ.Δ. — υπόθεση {case_number}"
# 2.2 An identical email for the same check within this window is a double submit.
DEFICIENCY_EMAIL_DEDUPE_SECONDS = 120
CASE_NUMBER_ATTEMPTS = 5


def _case_number_base(community, year) -> str:
    prefix = get_setting("caseNumberPrefix", "CASE")
    return f"{prefix}-{community.community_folder_code}-{year}-"


def _sequence_suffix(case_number: str, base: str):
    suffix = case_number[len(base):]
    return int(suffix) if suffix.isdigit() else None


@transaction.atomic
def generate_case_number(community, start_date=None) -> str:
    """1.1 Automatic case number, tied to district (through the community) and community.

    The sequence continues after the highest existing number of the community and year
    (not the row count), so deleted cases never cause a number to be reused.
    """
    community = community.__class__.objects.select_for_update().get(pk=community.pk)
    if not community.community_folder_code:
        raise ValidationError("Η Κοινότητα δεν έχει αριθμό φακέλου (communityFolderCode).")

    digits = int(get_setting("caseSequenceDigits", "2"))
    year = (start_date or timezone.localdate()).year
    base = _case_number_base(community, year)
    existing = (
        Case.objects.select_for_update()
        .filter(case_number__startswith=base)
        .values_list("case_number", flat=True)
    )
    numbers = [n for n in (_sequence_suffix(number, base) for number in existing) if n is not None]
    sequence = str(max(numbers, default=0) + 1).zfill(digits)
    return f"{base}{sequence}"


def create_case(case: Case) -> Case:
    """1.1 Save a new case with its automatic number and start date.

    A concurrent create may take the same number between generating and saving it; the
    insert then fails on the unique constraint inside a savepoint and is retried with the
    next number. Exhausted retries surface as a ValidationError, never as a server error.
    """
    case.start_date = case.start_date or timezone.localdate()
    for _ in range(CASE_NUMBER_ATTEMPTS):
        try:
            with transaction.atomic():
                case.case_number = generate_case_number(case.community, case.start_date)
                case.save()
            return case
        except IntegrityError:
            case.pk = None
            case._state.adding = True
    raise ValidationError(
        "Δεν ήταν δυνατή η απόδοση αριθμού υπόθεσης λόγω ταυτόχρονης καταχώρισης. "
        "Δοκιμάστε ξανά."
    )


def deficiency_email_subject(case: Case) -> str:
    """2.2 Predefined subject from the Settings; supports {case_number} and {community}."""
    template = get_setting(DEFICIENCY_EMAIL_SUBJECT_KEY, DEFICIENCY_EMAIL_SUBJECT_DEFAULT)
    return template.replace("{case_number}", case.case_number).replace(
        "{community}", case.community.name
    )


def _record_deficiency_email(check: CompletenessCheck, subject: str, body: str) -> Communication:
    """Create the 2.2 record before sending, refusing a duplicate (double submit)."""
    case = check.case
    check_type = ContentType.objects.get_for_model(CompletenessCheck)
    with transaction.atomic():
        # Serialises concurrent submits for the same check where the database can lock.
        CompletenessCheck.objects.select_for_update().filter(pk=check.pk).exists()
        since = timezone.now() - timedelta(seconds=DEFICIENCY_EMAIL_DEDUPE_SECONDS)
        duplicate = Communication.objects.filter(
            content_type=check_type,
            object_id=check.pk,
            recipient=case.contact_email,
            subject=subject,
            body=body,
            status__in=(CommunicationStatus.SENDING, CommunicationStatus.SENT),
            created_at__gte=since,
        ).exists()
        if duplicate:
            raise ValidationError(
                "Το ίδιο email ελλείψεων έχει ήδη σταλεί για αυτόν τον έλεγχο πριν από λίγο."
            )
        communication = Communication(
            content_type=check_type,
            object_id=check.pk,
            recipient=case.contact_email,
            subject=subject,
            body=body,
            status=CommunicationStatus.SENDING,
        )
        communication._section_ref = refs.REF_DEFICIENCY_EMAIL
        communication.save()
    return communication


def send_deficiency_email(check: CompletenessCheck, subject: str, body: str) -> Communication:
    """2.2 Send the deficiencies to the 1.1 contact address and record the sending.

    The Communication is saved first (status «sending»), then the email is sent and the
    record is marked «sent» or «failed», so no email leaves without a trace.
    """
    case = check.case
    if not case.contact_email:
        raise ValidationError("Η υπόθεση δεν έχει ηλεκτρονική διεύθυνση επικοινωνίας (1.1).")
    if not subject.strip():
        raise ValidationError("Το θέμα του email είναι κενό.")
    # Nothing is recorded when sending cannot even start.
    require_smtp_configured()

    communication = _record_deficiency_email(check, subject, body)
    communication._section_ref = refs.REF_DEFICIENCY_EMAIL
    try:
        send_email(case.contact_email, subject, body)
    except Exception:
        communication.status = CommunicationStatus.FAILED
        communication.save()
        raise
    communication.status = CommunicationStatus.SENT
    communication.sent_at = timezone.now()
    communication.save()
    return communication


def delete_with_attachments(instance, section_ref: str) -> None:
    """Delete a case row together with all its files, each logged under `section_ref`."""
    instance._section_ref = section_ref
    with transaction.atomic():
        for attachment in instance.attachments.all():
            attachment._section_ref = section_ref
            attachment.delete()
        instance.delete()


def approved_design_plot_section(case: Case) -> str:
    """Section that owns the 7.3 plot rows of a case."""
    return refs.SECTION_7


def approved_design_plot_section_ref(section: str) -> str:
    return refs.REF_APPROVED_DESIGN_PLOTS


SECTION_FORMSET_REFS = {}


def save_case_section(section: str, form, formsets) -> None:
    """Save a section screen (main Case form plus inline formsets) in one transaction."""
    formset_refs = SECTION_FORMSET_REFS.get(section)
    with transaction.atomic():
        if form:
            form.save()
        for formset in formsets:
            if formset_refs:
                section_ref = formset_refs.get(formset.prefix, formset_refs[None])
                for child in formset.forms:
                    child.instance._section_ref = section_ref
            formset.save()


def case_attachments(case: Case):
    """Every file reachable from the case folder: 3.1 plots, case files, 5 / 7.4, 6.7."""
    owners = (
        (LandPlot, case.land_plots.values("pk")),
        (Consultation, case.consultations.values("pk")),
        (MinistryDecisionRound, case.ministry_decision_rounds.values("pk")),
    )
    condition = Q(content_type=ContentType.objects.get_for_model(Case), object_id=case.pk)
    for model, ids in owners:
        condition |= Q(content_type=ContentType.objects.get_for_model(model), object_id__in=ids)
    return Attachment.objects.filter(condition)


def attachment_owning_section(attachment) -> str:
    """Section whose «Προβολή» access opens a case file."""
    model = attachment.content_type.model_class()
    if model is LandPlot:
        return refs.SECTION_3
    if model is Consultation:
        return (
            refs.SECTION_7
            if attachment.section_ref == refs.REF_DIVISION_CONSULTATIONS
            else refs.SECTION_5
        )
    if model is MinistryDecisionRound:
        return refs.SECTION_6
    if attachment.section_ref in (
        refs.REF_DIVISION_DESIGN,
        refs.REF_TPO_APPLICATION,
        refs.REF_DLS_APPLICATION,
    ):
        return refs.SECTION_7
    return refs.SECTION_4


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
    """8.3 Automatic completion check over the allocatable plots of the case."""
    parcels = list(
        case.approved_design_plots.filter(
            plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT
        )
    )
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
    parcels = list(
        case.approved_design_plots.filter(
            plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT
        )
    )
    if case.is_new_division:
        latest_check = case.latest_infrastructure_check
        works_ready = bool(latest_check and latest_check.is_ready_for_submission_cycle)
        final_areas = bool(parcels) and all(
            parcel.final_area_sqm is not None for parcel in parcels
        )
    else:
        # §Α.3.3 An unallocated-plots case registers its plots directly in 8.2.
        works_ready = True
        final_areas = bool(parcels)
    rows = [
        ("Απαιτούμενο στάδιο εργασιών (7.6)", works_ready),
        ("Αίτηση στο ΤΚΧ (7.7)", completion["surveying_done"]),
        ("Τελικά εμβαδά", final_areas),
        ("Καθορισμένη αξία / τιμή", completion["all_valued"] and completion["all_priced"]),
    ]
    return {"rows": rows, "can_start": all(ready for _, ready in rows)}


def cases_not_ready_for_announcement(cases) -> list:
    """Case numbers whose 9.4 readiness check does not allow Ενότητα 9 to start."""
    return [case.case_number for case in cases if not announcement_readiness(case)["can_start"]]


def require_announcement_readiness(cases) -> None:
    """§Β.2 stage gate: Ενότητα 9 does not open unless 9.4 gives «Δυνατότητα έναρξης = ΝΑΙ»."""
    blocked = cases_not_ready_for_announcement(cases)
    if blocked:
        raise ValidationError(
            "Δεν πληρούται ο έλεγχος ετοιμότητας (9.4) για: " + ", ".join(blocked)
        )


def create_announcement(form, case: Case) -> SubmissionCycle:
    """9.1 Create the announcement of a valid SubmissionCycleForm, with its 9.3 draft.

    Gated by the 9.4 readiness check of every case it covers (including `case`).
    """
    cases = list(form.cleaned_data.get("cases") or [])
    if case not in cases:
        cases.append(case)
    require_announcement_readiness(cases)
    with transaction.atomic():
        cycle = form.save(commit=False)
        cycle.community = case.community
        cycle.save()
        form.save_m2m()
        cycle.cases.add(case)
        cycle.announcement_text = build_announcement_text(cycle)
        cycle.save()
    return cycle


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
    require_announcement_readiness(cases)
    cycle.published_at = timezone.now()
    cycle.save()
    return cycle
