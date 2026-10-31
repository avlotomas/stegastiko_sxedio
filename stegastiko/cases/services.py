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
)
from core.models import ActionHistory, Attachment, Communication
from core.services import get_setting, require_smtp_configured, send_email

DEFICIENCY_EMAIL_SUBJECT_KEY = "deficiencyEmailSubject"
DEFICIENCY_EMAIL_SUBJECT_DEFAULT = "Ελλείψεις αίτησης Κ.Σ./Δ.Δ. — υπόθεση {case_number}"
LAND_PLOT_EMAIL_SUBJECT_KEY = "landPlotEmailSubject"
LAND_PLOT_EMAIL_SUBJECT_DEFAULT = "Τεμάχιο {parcel_number} — υπόθεση {case_number}"
# An identical email for the same row within this window is a double submit.
EMAIL_DEDUPE_SECONDS = 120
CASE_NUMBER_ATTEMPTS = 5


CASE_NUMBER_PREFIX_KEY = "caseNumberPrefix"
CASE_NUMBER_PREFIX_DEFAULT = "CASE"


def _case_number_base(community) -> str:
    """1.1 `<prefix>.<communityFolderCode>.` — the prefix comes from the Settings."""
    prefix = get_setting(CASE_NUMBER_PREFIX_KEY, CASE_NUMBER_PREFIX_DEFAULT).strip()
    return f"{prefix}.{community.community_folder_code}."


def _sequence_suffix(case_number: str, code: str):
    """Sequence of a `<prefix>.<code>.<n>` number; None for any other format."""
    head, sep, suffix = case_number.rpartition(".")
    if not sep or not suffix.isdigit() or not head.endswith(f".{code}"):
        return None
    return int(suffix)


@transaction.atomic
def generate_case_number(community, start_date=None) -> str:
    """1.1 Automatic case number: `<prefix>.<communityFolderCode>.<sequence>`.

    The sequence counts the cases of the community (whatever prefix was in force when
    they were numbered) and continues after the highest existing number, not the row
    count, so deleted cases never cause a number to be reused.
    """
    community = community.__class__.objects.select_for_update().get(pk=community.pk)
    code = community.community_folder_code
    if not code:
        raise ValidationError("Η Κοινότητα δεν έχει αριθμό φακέλου (communityFolderCode).")

    existing = (
        Case.objects.select_for_update()
        .filter(community=community, case_number__contains=f".{code}.")
        .values_list("case_number", flat=True)
    )
    numbers = [n for n in (_sequence_suffix(number, code) for number in existing) if n is not None]
    return f"{_case_number_base(community)}{max(numbers, default=0) + 1}"


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


def land_plot_email_subject(plot: LandPlot, template: str | None = None) -> str:
    """3.1 Predefined subject from the Settings; supports {parcel_number}, {case_number}, {community}.

    Pass `template` when filling many rows so the setting is read once.
    """
    case = plot.case
    if template is None:
        template = get_setting(LAND_PLOT_EMAIL_SUBJECT_KEY, LAND_PLOT_EMAIL_SUBJECT_DEFAULT)
    return (
        template.replace("{parcel_number}", plot.parcel_number)
        .replace("{case_number}", case.case_number)
        .replace("{community}", case.community.name)
    )


def _record_email(owner, recipient, subject, body, section_ref, duplicate_message) -> Communication:
    """Create the email record before sending, refusing a duplicate (double submit)."""
    owner_type = ContentType.objects.get_for_model(owner)
    with transaction.atomic():
        # Serialises concurrent submits for the same row where the database can lock.
        type(owner).objects.select_for_update().filter(pk=owner.pk).exists()
        since = timezone.now() - timedelta(seconds=EMAIL_DEDUPE_SECONDS)
        duplicate = Communication.objects.filter(
            content_type=owner_type,
            object_id=owner.pk,
            recipient=recipient,
            subject=subject,
            body=body,
            status__in=(CommunicationStatus.SENDING, CommunicationStatus.SENT),
            created_at__gte=since,
        ).exists()
        if duplicate:
            raise ValidationError(duplicate_message)
        communication = Communication(
            content_type=owner_type,
            object_id=owner.pk,
            recipient=recipient,
            subject=subject,
            body=body,
            status=CommunicationStatus.SENDING,
        )
        communication._section_ref = section_ref
        communication.save()
    return communication


def _send_case_email(owner, subject, body, section_ref, duplicate_message) -> Communication:
    """Send an email about a case row to the 1.1 contact address and record the sending.

    The Communication is saved first (status «sending»), then the email is sent and the
    record is marked «sent» or «failed», so no email leaves without a trace.
    """
    case = owner.case
    if not case.contact_email:
        raise ValidationError("Η υπόθεση δεν έχει ηλεκτρονική διεύθυνση επικοινωνίας (1.1).")
    if not subject.strip():
        raise ValidationError("Το θέμα του email είναι κενό.")
    # Nothing is recorded when sending cannot even start.
    require_smtp_configured()

    communication = _record_email(
        owner, case.contact_email, subject, body, section_ref, duplicate_message
    )
    communication._section_ref = section_ref
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


def send_deficiency_email(check: CompletenessCheck, subject: str, body: str) -> Communication:
    """2.2 Send the deficiencies of a completeness check to the 1.1 contact address."""
    return _send_case_email(
        check,
        subject,
        body,
        refs.REF_DEFICIENCY_EMAIL,
        "Το ίδιο email ελλείψεων έχει ήδη σταλεί για αυτόν τον έλεγχο πριν από λίγο.",
    )


def send_land_plot_email(plot: LandPlot, subject: str, body: str) -> Communication:
    """3.1 Send an email about one land plot to the 1.1 contact address of the Κ.Σ./Δ.Δ."""
    return _send_case_email(
        plot,
        subject,
        body,
        refs.REF_LAND_PLOT_EMAIL,
        "Το ίδιο email έχει ήδη σταλεί για αυτό το τεμάχιο πριν από λίγο.",
    )


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
    """2.2 deficiency emails (and any email recorded on the case itself)."""
    case_type = ContentType.objects.get_for_model(Case)
    check_type = ContentType.objects.get_for_model(CompletenessCheck)
    return Communication.objects.filter(
        Q(content_type=case_type, object_id=case.pk)
        | Q(content_type=check_type, object_id__in=case.completeness_checks.values("pk"))
    ).order_by("-created_at", "-id")


def land_plot_communications(case: Case):
    """3.1 emails sent about the land plots of the case."""
    return Communication.objects.filter(
        content_type=ContentType.objects.get_for_model(LandPlot),
        object_id__in=case.land_plots.values("pk"),
    ).order_by("-created_at", "-id")


def communication_section(communication: Communication) -> str:
    """Section whose access opens a sent email of the case."""
    if communication.content_type.model_class() is LandPlot:
        return refs.SECTION_3
    return refs.SECTION_2


def case_history(case: Case):
    """§Β.1.3 Aggregate history of the case folder, including the plots it produced."""
    return ActionHistory.objects.filter(case_id=case.pk).order_by("-timestamp", "-id")


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
    surveying_done = bool(case.dls_response_date)
    return {
        "parcels_count": len(parcels),
        "all_valued": all_valued,
        "all_priced": all_priced,
        "surveying_done": surveying_done,
        "is_complete": all_valued and all_priced and surveying_done,
    }


def completion_readiness(case: Case) -> dict:
    """Automatic readiness check shown with «Ολοκλήρωση αίτησης» (formerly 9.4); advisory only."""
    completion = section8_completion(case)
    parcels = list(
        case.approved_design_plots.filter(
            plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT
        )
    )
    latest_check = case.latest_infrastructure_check
    works_ready = bool(latest_check and latest_check.is_ready_for_submission_cycle)
    final_areas = bool(parcels) and all(parcel.final_area_sqm is not None for parcel in parcels)
    # `target` is where the row is fixed: "plots" opens the 7.3 plots workspace, "#…" is an
    # element of the section 7 screen.
    rows = [
        {"label": "Υπό διαχωρισμό οικόπεδα (7.3)", "ready": bool(parcels), "target": "plots"},
        {
            "label": "Απαιτούμενο στάδιο εργασιών (7.6)",
            "ready": works_ready,
            "target": "#subsection-7-6",
        },
        {
            "label": "Αίτηση στο ΤΚΧ (7.7)",
            "ready": completion["surveying_done"],
            "target": "#id_dls_response_date",
        },
        {"label": "Τελικά εμβαδά", "ready": final_areas, "target": "plots"},
        {
            "label": "Καθορισμένη αξία / τιμή",
            "ready": completion["all_valued"] and completion["all_priced"],
            "target": "plots",
        },
    ]
    return {
        "rows": rows,
        "ready": all(row["ready"] for row in rows),
        "missing": [row["label"] for row in rows if not row["ready"]],
    }
