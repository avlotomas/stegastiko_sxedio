from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from cases.models import CommunicationStatus
from core.models import ActionHistory, Communication, Community
from core.services import get_setting, require_smtp_configured, send_email
from plot_applications.documents import DOCUMENT_GROUPS, applicable_documents
from plot_applications.models import PlotApplication
from plot_applications.rules import parameter

PROTOCOL_NUMBER_MAX_ATTEMPTS = 5
PLOT_APPLICATION_EMAIL_SUBJECT_KEY = "plotApplicationEmailSubject"
PLOT_APPLICATION_EMAIL_SUBJECT_DEFAULT = (
    "Αίτηση παραχώρησης οικοπέδου {protocol_number} — Κοινότητα {community}"
)
EMAIL_DEDUPE_SECONDS = 120
REF_PLOT_APPLICATION_EMAIL = "plot_application_email"
MISSING_DOCUMENTS_HEADING = "Ελλείποντα δικαιολογητικά έγγραφα:"


def _protocol_base(community) -> str:
    if not community.community_folder_code:
        raise ValidationError("Η κοινότητα δεν έχει communityFolderCode.")
    prefix = get_setting("plotApplicationProtocolPrefix", "Π3-")
    return f"{prefix}{community.community_folder_code}-"


def generate_protocol_number(community, offset: int = 0) -> str:
    """Αρ. Πρωτοκόλλου («Για Επίσημη Χρήση»): πρόθεμα + κωδικός Κοινότητας + αύξων αριθμός.

    Χρησιμοποιείται στους Καταλόγους Δικαιούχων (Ενότ. 6, 7). Ο αύξων συνεχίζει από τον
    μεγαλύτερο ήδη εκδοθέντα, ώστε διαγραμμένες αιτήσεις να μην επαναχρησιμοποιούν αριθμό.
    """
    community = Community.objects.select_for_update().get(pk=community.pk)
    base = _protocol_base(community)
    highest = 0
    for number in PlotApplication.objects.filter(protocol_number__startswith=base).values_list(
        "protocol_number", flat=True
    ):
        suffix = number[len(base):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    digits = int(get_setting("folderSequenceDigits", "3"))
    return f"{base}{str(highest + 1 + offset).zfill(digits)}"


def save_with_new_protocol_number(application: PlotApplication) -> PlotApplication:
    for attempt in range(PROTOCOL_NUMBER_MAX_ATTEMPTS):
        application.protocol_number = generate_protocol_number(application.community, attempt)
        try:
            with transaction.atomic():
                application.save()
        except IntegrityError as exc:
            if "protocol_number" not in str(exc):
                raise
            application.pk = None
            application._state.adding = True
            continue
        return application
    raise ValidationError("Δεν ήταν δυνατή η απόδοση μοναδικού Αρ. Πρωτοκόλλου. Δοκιμάστε ξανά.")


def plot_application_email_subject(application: PlotApplication) -> str:
    """Προκαθορισμένο θέμα email για αίτηση παραχώρησης οικοπέδου."""
    template = get_setting(
        PLOT_APPLICATION_EMAIL_SUBJECT_KEY, PLOT_APPLICATION_EMAIL_SUBJECT_DEFAULT
    )
    community_name = application.community.name if application.community_id else ""
    return template.replace("{protocol_number}", application.protocol_number or "").replace(
        "{community}", community_name
    )


def format_document_email_line(label: str, note: str = "") -> str:
    """Γραμμή πιστοποιητικού στο email· αν υπάρχει σημείωση, εμφανίζεται δίπλα ως italic/bold."""
    clean_note = (note or "").strip()
    if clean_note:
        return f"- {label} ***{clean_note}***"
    return f"- {label}"


def missing_documents_for_application(application: PlotApplication) -> list[tuple[str, str]]:
    """Εφαρμοζόμενα δικαιολογητικά από τον Κατάλογο που δεν έχουν επιλεγεί (unchecked checkboxes)."""
    applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren"))
    attached = set(application.attached_documents or [])
    return [
        (code, label)
        for _, items in DOCUMENT_GROUPS
        for code, label in items
        if code in applicable and code not in attached
    ]


def missing_documents_email_text(application: PlotApplication) -> str:
    """Κείμενο με τα ελλείποντα δικαιολογητικά έγγραφα (και τυχόν σημειώσεις) για προσθήκη στο σώμα του email."""
    applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren"))
    attached = set(application.attached_documents or [])
    raw_notes = application.document_notes if isinstance(application.document_notes, dict) else {}
    lines_items = []
    for _, items in DOCUMENT_GROUPS:
        for code, label in items:
            note = str(raw_notes.get(code) or "").strip()
            if (code in applicable and code not in attached) or note:
                lines_items.append(format_document_email_line(label, note))
    if not lines_items:
        return ""
    return "\n".join([MISSING_DOCUMENTS_HEADING, *lines_items])


def send_plot_application_email(
    application: PlotApplication,
    subject: str,
    body: str,
    recipient: str | None = None,
    *,
    user=None,
) -> Communication:
    """Αποστολή email προς το άτομο/αιτητή της αίτησης και καταγραφή στο ιστορικό (Communication)."""
    target_email = (recipient if recipient is not None else (application.email or "")).strip()
    if not target_email:
        raise ValidationError("Η αίτηση δεν έχει ηλεκτρονική διεύθυνση επικοινωνίας.")
    subject = (subject or "").strip()
    if not subject:
        raise ValidationError("Το θέμα του email είναι κενό.")
    body = (body or "").strip()
    if not body:
        raise ValidationError("Το κείμενο του email είναι κενό.")
    require_smtp_configured()

    section_ref = REF_PLOT_APPLICATION_EMAIL
    if application.announcement_id and getattr(application.announcement, "stage", None):
        from cases.models import SubmissionCycle

        ann_stage = application.announcement.stage
        if ann_stage == SubmissionCycle.Stage.DETAILS:
            ann_stage = SubmissionCycle.Stage.SUBMISSION
        elif ann_stage == SubmissionCycle.Stage.CLOSED:
            ann_stage = SubmissionCycle.Stage.AGREEMENTS
        section_ref = f"announcement_stage:{ann_stage}"

    owner_type = ContentType.objects.get_for_model(PlotApplication)
    with transaction.atomic():
        PlotApplication.objects.select_for_update().filter(pk=application.pk).exists()
        since = timezone.now() - timedelta(seconds=EMAIL_DEDUPE_SECONDS)
        duplicate = Communication.objects.filter(
            content_type=owner_type,
            object_id=application.pk,
            recipient=target_email,
            subject=subject,
            body=body,
            status__in=(CommunicationStatus.SENDING, CommunicationStatus.SENT),
            created_at__gte=since,
        ).exists()
        if duplicate:
            raise ValidationError(
                "Το ίδιο email έχει ήδη σταλεί για αυτή την αίτηση πριν από λίγο."
            )
        communication = Communication(
            content_type=owner_type,
            object_id=application.pk,
            recipient=target_email,
            subject=subject,
            body=body,
            status=CommunicationStatus.SENDING,
            created_by_id=user.pk if (user is not None and getattr(user, "pk", None)) else None,
        )
        communication._section_ref = section_ref
        communication.save()

    communication._section_ref = section_ref
    try:
        send_email(target_email, subject, body)
    except Exception:
        communication.status = CommunicationStatus.FAILED
        communication.save()
        raise
    communication.status = CommunicationStatus.SENT
    communication.sent_at = timezone.now()
    communication.save()
    return communication


def plot_application_communications(application: PlotApplication):
    """Ιστορικό απεσταλμένων email μιας αίτησης παραχώρησης οικοπέδου."""
    if not application or not application.pk:
        return Communication.objects.none()
    return (
        Communication.objects.filter(
            content_type=ContentType.objects.get_for_model(PlotApplication),
            object_id=application.pk,
        )
        .prefetch_related("content_object")
        .order_by("-created_at", "-id")
    )


def person_communications(person):
    """Ιστορικό απεσταλμένων email για όλες τις αιτήσεις παραχώρησης οικοπέδου του ατόμου."""
    if not person or not person.pk:
        return Communication.objects.none()
    app_ids = PlotApplication.objects.filter(
        Q(applicant=person) | Q(spouse=person)
    ).values("pk")
    return (
        Communication.objects.filter(
            content_type=ContentType.objects.get_for_model(PlotApplication),
            object_id__in=app_ids,
        )
        .prefetch_related("content_object")
        .order_by("-created_at", "-id")
    )


def plot_application_history(application: PlotApplication):
    """§Β.1.3 Συγκεντρωτικό ιστορικό αλλαγών της αίτησης παραχώρησης οικοπέδου και των παιδιών της."""
    if not application or not application.pk:
        return ActionHistory.objects.none()
    return ActionHistory.objects.filter(
        Q(entity_type="PlotApplication", entity_id=str(application.pk))
        | Q(application_id=application.pk)
    ).order_by("-timestamp", "-id")


