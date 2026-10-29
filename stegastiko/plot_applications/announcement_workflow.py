"""Ροή εργασιών Γνωστοποίησης (Στάδια 1–7, Ενότ. 4, 5, 6, 7, 8, 9, 12, 13, 15).

Στάδια Γνωστοποίησης (`SubmissionCycle.Stage`):
1. `details`: Στοιχεία γνωστοποίησης (9.1, επιλογή οικοπέδων, 9.2 τρόποι δημοσίευσης, 9.3 έκδοση)
2. `submission`: Υποβολή αιτήσεων (έως τη λήξη της προθεσμίας υποβολής)
3. `applications_committee`: Επιτροπή Εξέτασης Αιτήσεων — προτεραιοποίηση, Προκαταρκτικός Κατάλογος
   & αποστολή email (ό,τι κάνει η Επιτροπή αποθηκεύεται ως input για το Στάδιο 5)
4. `objections_committee`: Ενστάσεις — περίοδος 21 ημερών, καταχώριση και απόφαση
   ενστάσεων, εκκρεμότητες (pending)
5. `final_list`: Τελικός Κατάλογος Δικαιούχων — αλλαγές βάσει ενστάσεων, έκδοση & αποστολή email
   (ξεχωριστό σε δικαιούχους οικοπέδου και επιλαχόντες)
6. `lottery`: Στάδιο κλήρωσης οικοπέδων (φυσική κλήρωση, καταχώριση αποτελέσματος)
7. `agreements`: Υπογραφή Συμφωνίας (Παράρτημα 4, .docx) & Πληρωμή, ή έκπτωση και ανάθεση σε επιλαχόντα
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from allocation.models import (
    Agreement,
    Allocation,
    Lottery,
    Payment,
    RankingEntry,
    RankingList,
)
from cases.models import CommunicationStatus, SubmissionCycle
from core.models import Communication
from core.services import get_setting, send_email, smtp_is_configured
from plot_applications.beneficiary_lists import (
    BeneficiaryListError,
    _check_no_blockers,
    _check_no_open_objections_or_pending_items,
    community_lists,
    issue_final_list,
    issue_preliminary_list,
)
from plot_applications.models import (
    ApplicationStage,
    Objection,
    PendingRequirement,
    PlotApplication,
)
from plot_applications.rules import apply_evaluation, parameter
from plots.models import Plot


class AnnouncementWorkflowError(BeneficiaryListError):
    """Σφάλμα επιχειρησιακού κανόνα στη ροή των σταδίων της γνωστοποίησης."""


class ObjectionPeriodOpenError(AnnouncementWorkflowError):
    """Η περίοδος ενστάσεων δεν έληξε· η μετάβαση απαιτεί ρητή αποδοχή της προειδοποίησης."""


class SubmissionPeriodOpenError(AnnouncementWorkflowError):
    """Η προθεσμία υποβολής αιτήσεων δεν έληξε· η μετάβαση απαιτεί ρητή αποδοχή της προειδοποίησης."""


WORKFLOW_EMAIL_TEMPLATES: tuple[tuple[str, str, str, str], ...] = (
    (
        "preliminaryBeneficiaryEmailSubject",
        "Θέμα email Προκαταρκτικού Καταλόγου — Δικαιούχος (Ενότ. 6)",
        "Προκαταρκτικός Κατάλογος Δικαιούχων — Αίτηση {protocol_number} ({community})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {rank}, {objection_deadline}.",
    ),
    (
        "preliminaryBeneficiaryEmailBody",
        "Κείμενο email Προκαταρκτικού Καταλόγου — Δικαιούχος (Ενότ. 6)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας γνωστοποιούμε ότι η αίτησή σας ({protocol_number}) για την Κοινότητα {community} "
            "κρίθηκε ως ΔΙΚΑΙΟΥΧΟΣ στον Προκαταρκτικό Κατάλογο Δικαιούχων με σειρά προτεραιότητας {rank}.\n"
            "Έχετε δικαίωμα υποβολής ένστασης εντός 21 ημερών (έως {objection_deadline})."
        ),
        "Αποστέλλεται στους δικαιούχους του Προκαταρκτικού Καταλόγου (Ενότ. 6).",
    ),
    (
        "preliminaryRejectedEmailSubject",
        "Θέμα email Προκαταρκτικού Καταλόγου — Μη Δικαιούχος (Ενότ. 6)",
        "Προκαταρκτικός Κατάλογος — Απόρριψη Αίτησης {protocol_number} ({community})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {objection_deadline}.",
    ),
    (
        "preliminaryRejectedEmailBody",
        "Κείμενο email Προκαταρκτικού Καταλόγου — Μη Δικαιούχος (Ενότ. 6)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας γνωστοποιούμε ότι η αίτησή σας ({protocol_number}) για την Κοινότητα {community} "
            "κρίθηκε ως ΜΗ ΔΙΚΑΙΟΥΧΟΣ στον Προκαταρκτικό Κατάλογο.\n"
            "Έχετε δικαίωμα υποβολής ένστασης εντός 21 ημερών (έως {objection_deadline})."
        ),
        "Αποστέλλεται στους μη δικαιούχους του Προκαταρκτικού Καταλόγου (Ενότ. 6).",
    ),
    (
        "objectionUpheldEmailSubject",
        "Θέμα email Ένστασης — Ικανοποιήθηκε (Ενότ. 7)",
        "Απόφαση επί Ένστασης — Αίτηση {protocol_number} ({community})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {decision_notes}.",
    ),
    (
        "objectionUpheldEmailBody",
        "Κείμενο email Ένστασης — Ικανοποιήθηκε (Ενότ. 7)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Ικανοποιήθηκε η ένστασή σας για την αίτηση {protocol_number} στην Κοινότητα {community}.\n"
            "Σκεπτικό απόφασης: {decision_notes}"
        ),
        "Αποστέλλεται όταν η Επιτροπή Εξέτασης Ενστάσεων κάνει δεκτή την ένσταση (Ενότ. 7).",
    ),
    (
        "objectionDismissedEmailSubject",
        "Θέμα email Ένστασης — Δεν ικανοποιήθηκε (Ενότ. 7)",
        "Απόφαση επί Ένστασης — Αίτηση {protocol_number} ({community})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {decision_notes}.",
    ),
    (
        "objectionDismissedEmailBody",
        "Κείμενο email Ένστασης — Δεν ικανοποιήθηκε (Ενότ. 7)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Δεν ικανοποιήθηκε η ένστασή σας για την αίτηση {protocol_number} στην Κοινότητα {community}.\n"
            "Σκεπτικό απόφασης: {decision_notes}"
        ),
        "Αποστέλλεται όταν η Επιτροπή Εξέτασης Ενστάσεων απορρίψει την ένσταση (Ενότ. 7).",
    ),
    (
        "finalPlotBeneficiaryEmailSubject",
        "Θέμα email Τελικού Καταλόγου — Δικαιούχος Οικοπέδου (Ενότ. 7, 8)",
        "Τελικός Κατάλογος Δικαιούχων — Δικαιούχος Οικοπέδου ({protocol_number})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {rank}, {plots_count}.",
    ),
    (
        "finalPlotBeneficiaryEmailBody",
        "Κείμενο email Τελικού Καταλόγου — Δικαιούχος Οικοπέδου (Ενότ. 7, 8)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας ενημερώνουμε ότι στον Τελικό Κατάλογο Δικαιούχων της Κοινότητας {community} "
            "η αίτησή σας ({protocol_number}) κατατάχθηκε στη θέση {rank} (εντός των {plots_count} "
            "διαθέσιμων οικοπέδων) και είστε ΔΙΚΑΙΟΥΧΟΣ οικοπέδου."
        ),
        "Αποστέλλεται στους πρώτους N δικαιούχους του Τελικού Καταλόγου, όπου N = διαθέσιμα οικόπεδα (Ενότ. 8).",
    ),
    (
        "finalRunnerUpEmailSubject",
        "Θέμα email Τελικού Καταλόγου — Επιλαχών (Ενότ. 7, 8)",
        "Τελικός Κατάλογος Δικαιούχων — Επιλαχών ({protocol_number})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {rank}, {plots_count}.",
    ),
    (
        "finalRunnerUpEmailBody",
        "Κείμενο email Τελικού Καταλόγου — Επιλαχών (Ενότ. 7, 8)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας ενημερώνουμε ότι στον Τελικό Κατάλογο Δικαιούχων της Κοινότητας {community} "
            "η αίτησή σας ({protocol_number}) κατατάχθηκε στη θέση {rank} ως ΕΠΙΛΑΧΩΝ "
            "(διαθέσιμα οικόπεδα: {plots_count})."
        ),
        "Αποστέλλεται στους δικαιούχους με σειρά μεγαλύτερη του αριθμού των διαθέσιμων οικοπέδων (Ενότ. 8).",
    ),
    (
        "lotteryInvitationEmailSubject",
        "Θέμα email Πρόσκλησης σε Κλήρωση Οικοπέδων (Ενότ. 9)",
        "Πρόσκληση σε Κλήρωση Οικοπέδων — Κοινότητα {community} ({protocol_number})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {lottery_date}, {location}.",
    ),
    (
        "lotteryInvitationEmailBody",
        "Κείμενο email Πρόσκλησης σε Κλήρωση Οικοπέδων (Ενότ. 9)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας καλούμε στην κλήρωση κατανομής οικοπέδων της Κοινότητας {community} "
            "που θα πραγματοποιηθεί στις {lottery_date} στον χώρο: {location}."
        ),
        "Αποστέλλεται στους δικαιούχους πριν από την κλήρωση οικοπέδων (Ενότ. 9).",
    ),
    (
        "agreementInvitationEmailSubject",
        "Θέμα email Πρόσκλησης για Υπογραφή Συμφωνίας & Πληρωμή (Ενότ. 9, 12, 15)",
        "Πρόσκληση για Υπογραφή Συμφωνίας και Πληρωμή — Οικόπεδο {plot_number} ({protocol_number})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {plot_number}, {disposal_price}, {appointment_date}, {location}, {agreement_deadline}.",
    ),
    (
        "agreementInvitationEmailBody",
        "Κείμενο email Πρόσκλησης για Υπογραφή Συμφωνίας & Πληρωμή (Ενότ. 9, 12, 15)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας γνωστοποιούμε ότι σας κατανεμήθηκε το οικόπεδο {plot_number} στην Κοινότητα {community} "
            "(τιμή διάθεσης: € {disposal_price}). Παρακαλούμε όπως προσέλθετε στις {appointment_date} "
            "({location}) για καταβολή της τιμής διάθεσης και υπογραφή της Συμφωνίας Παραχώρησης, "
            "το αργότερο έως {agreement_deadline}."
        ),
        "Αποστέλλεται στους δικαιούχους μετά την κλήρωση οικοπέδων (Ενότ. 9, 12, 15).",
    ),
    (
        "runnerUpPromotionEmailSubject",
        "Θέμα email Ανάθεσης Οικοπέδου σε Επιλαχόντα (Ενότ. 8)",
        "Ανάθεση Οικοπέδου σε Επιλαχόντα — Οικόπεδο {plot_number} ({protocol_number})",
        "Διαθέσιμα πεδία: {protocol_number}, {community}, {applicant_name}, {plot_number}, {disposal_price}, {appointment_date}, {location}, {agreement_deadline}.",
    ),
    (
        "runnerUpPromotionEmailBody",
        "Κείμενο email Ανάθεσης Οικοπέδου σε Επιλαχόντα (Ενότ. 8)",
        (
            "Αγαπητέ/ή {applicant_name},\n\n"
            "Σας ενημερώνουμε ότι ως επιλαχών στον Τελικό Κατάλογο της Κοινότητας {community} "
            "σας ανατίθεται το οικόπεδο {plot_number} (τιμή διάθεσης: € {disposal_price}). "
            "Παρακαλούμε όπως προσέλθετε στις {appointment_date} ({location}) για πληρωμή και "
            "υπογραφή της Συμφωνίας Παραχώρησης, το αργότερο έως {agreement_deadline}."
        ),
        "Αποστέλλεται στον επιλαχόντα όταν ανατίθεται οικόπεδο μετά από έκπτωση προηγούμενου δικαιούχου (Ενότ. 8).",
    ),
)

WORKFLOW_EMAIL_DEFAULTS: dict[str, str] = {
    key: default for key, _label, default, _help in WORKFLOW_EMAIL_TEMPLATES
}


def render_workflow_template(key: str, context: dict[str, object]) -> str:
    template = get_setting(key, WORKFLOW_EMAIL_DEFAULTS[key])
    result = template
    for k, v in context.items():
        result = result.replace(f"{{{k}}}", "" if v is None else str(v))
    return result


def _applicant_context(application: PlotApplication) -> dict[str, str]:
    applicant = application.applicant if application.applicant_id else None
    community = application.community
    return {
        "protocol_number": application.protocol_number or "",
        "community": community.name if community else "",
        "applicant_name": (
            f"{applicant.first_name} {applicant.last_name}".strip() if applicant else ""
        ),
    }


def send_workflow_notification(
    application: PlotApplication,
    subject_key: str,
    body_key: str,
    extra_context: dict[str, object] | None = None,
    *,
    section_ref: str = "announcement_workflow",
    user=None,
) -> tuple[str, Communication | None]:
    """Send a templated email to `application` and record a `Communication` entry.

    Returns `("sent", communication)`, `("postal_only", None)` when the applicant has no
    email address (Sect. 6 postal dispatch), or `("failed", communication)` on SMTP error.
    """
    recipient = (application.email or "").strip()
    if not recipient:
        return "postal_only", None

    ctx = {**_applicant_context(application), **(extra_context or {})}
    subject = render_workflow_template(subject_key, ctx).strip()
    body = render_workflow_template(body_key, ctx).strip()

    owner_type = ContentType.objects.get_for_model(PlotApplication)
    communication = Communication(
        content_type=owner_type,
        object_id=application.pk,
        recipient=recipient,
        subject=subject,
        body=body,
        status=CommunicationStatus.SENDING,
        created_by_id=user.pk if (user is not None and getattr(user, "pk", None)) else None,
    )
    communication._section_ref = section_ref
    communication.save()

    try:
        if smtp_is_configured():
            send_email(recipient, subject, body)
        elif "locmem" in getattr(settings, "EMAIL_BACKEND", "") or "console" in getattr(
            settings, "EMAIL_BACKEND", ""
        ):
            from_email = get_setting("smtpFromEmail", "noreply@moi.gov.cy") or "noreply@moi.gov.cy"
            EmailMultiAlternatives(
                subject=subject, body=body, from_email=from_email, to=[recipient]
            ).send()
        else:
            send_email(recipient, subject, body)
    except Exception:
        communication.status = CommunicationStatus.FAILED
        communication._section_ref = section_ref
        communication.save()
        return "failed", communication

    communication.status = CommunicationStatus.SENT
    communication.sent_at = timezone.now()
    communication._section_ref = section_ref
    communication.save()
    return "sent", communication


def resend_failed_communication(communication: Communication) -> Communication:
    """Retry sending a failed `Communication` email."""
    send_email(communication.recipient, communication.subject, communication.body)
    communication.status = CommunicationStatus.SENT
    communication.sent_at = timezone.now()
    communication.save()
    return communication


# ─────────────────────────────────────────────────────────────────────────────
# Στάδιο 2 → Στάδιο 3: Επιτροπή Εξέτασης Αιτήσεων (Ενότ. 6)
# ─────────────────────────────────────────────────────────────────────────────


def submission_period_warning(cycle: SubmissionCycle) -> str:
    """Η κόκκινη προειδοποίηση όταν ζητείται μετάβαση στο Στάδιο 3 πριν λήξει η προθεσμία υποβολής."""
    deadline = cycle.submission_end_date
    deadline_text = f"{deadline:%d/%m/%Y}" if deadline else "—"
    return (
        f"Η προθεσμία υποβολής αιτήσεων (Ενότ. 4, 5) λήγει στις {deadline_text}. Αν προχωρήσετε "
        "τώρα στην Επιτροπή Εξέτασης Αιτήσεων, η περίοδος υποβολής και επεξεργασίας αιτήσεων "
        "κλείνει πριν από τη λήξη της προθεσμίας. Η αποδοχή καταγράφεται στο ιστορικό."
    )


@transaction.atomic
def start_applications_committee(
    cycle: SubmissionCycle,
    meeting_date: date | None = None,
    *,
    accept_open_submission: bool = False,
    today: date | None = None,
) -> SubmissionCycle:
    """Μετάβαση της γνωστοποίησης στο Στάδιο 3 (Επιτροπή Εξέτασης Αιτήσεων).

    Προϋποθέσεις:
    - Η γνωστοποίηση έχει δημοσιευθεί.
    - Όλες οι αιτήσεις της γνωστοποίησης έχουν περάσει το στάδιο πληρότητας (πλήρεις και
      ελεγμένες, ή απορριφθείσες από τον λειτουργό).
    - Η προθεσμία υποβολής έχει λήξει ή έχει γίνει αποδοχή της προειδοποίησης (`accept_open_submission`).
    """
    if not cycle.is_published:
        raise AnnouncementWorkflowError(
            "Η γνωστοποίηση πρέπει πρώτα να οριστικοποιηθεί/εκδοθεί (9.3)."
        )
    _check_no_blockers(cycle)
    if not cycle.applications.exclude(application_stage=ApplicationStage.REJECTED).exists():
        raise AnnouncementWorkflowError(
            "Δεν υπάρχουν πλήρεις αιτήσεις στη γνωστοποίηση για εξέταση από την Επιτροπή."
        )
    fields = ["stage", "applications_committee_date"]
    if today is not None and today <= cycle.submission_end_date and not cycle.submission_closed_early:
        if not accept_open_submission:
            raise SubmissionPeriodOpenError(submission_period_warning(cycle))
        cycle.submission_closed_early = True
        fields.append("submission_closed_early")
    elif accept_open_submission and cycle.submission_open():
        cycle.submission_closed_early = True
        fields.append("submission_closed_early")
    cycle.stage = SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
    if meeting_date is not None:
        cycle.applications_committee_date = meeting_date
    elif cycle.applications_committee_date is None:
        cycle.applications_committee_date = today or timezone.localdate()
    cycle._section_ref = "stage:applications_committee"
    cycle.save(update_fields=fields)
    return cycle


@transaction.atomic
def record_applications_committee_decision(
    cycle: SubmissionCycle,
    *,
    decided_on: date | None = None,
    user=None,
) -> dict:
    """Καταχώριση απόφασης Επιτροπής Εξέτασης Αιτήσεων (Στάδιο 2, Ενότ. 6):
    - Εκδίδει τον Προκαταρκτικό Κατάλογο Δικαιούχων (ή χρησιμοποιεί αυτόν που εκδόθηκε από την
      οθόνη προτεραιοποίησης και δεν έχει γνωστοποιηθεί).
    - Αποστέλλει email σε όλους τους αιτητές του καταλόγου (δικαιούχους με σειρά κατάταξης
      και μη δικαιούχους).
    - Ξεκινά την 21ήμερη προθεσμία ενστάσεων ανά αιτητή και μεταφέρει τη γνωστοποίηση στο Στάδιο 3.
    """
    existing = community_lists(cycle).preliminary
    if existing is not None and existing.notifications_sent_at is not None:
        raise AnnouncementWorkflowError(
            "Ο Προκαταρκτικός Κατάλογος Δικαιούχων έχει ήδη γνωστοποιηθεί στους αιτητές (Ενότ. 6(β))."
        )
    decision_date = decided_on or cycle.applications_committee_date or timezone.localdate()
    cycle.applications_committee_date = decision_date
    cycle.stage = SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
    cycle.save(update_fields=["stage", "applications_committee_date"])

    preliminary = existing or issue_preliminary_list(cycle, user, today=decision_date)
    if existing is not None:
        # Η προθεσμία ενστάσεων μετρά από την αποστολή των επιστολών (Ενότ. 6(β), 7(α)).
        notified_dt = timezone.make_aware(datetime.combine(decision_date, time(9, 0)))
        deadline = decision_date + timedelta(days=parameter("plotApp.objectionDays"))
        for entry in preliminary.entries.all():
            entry.notified_at = notified_dt
            entry.objection_deadline = deadline
            entry.save(update_fields=["notified_at", "objection_deadline", "updated_at"])
        preliminary.objection_deadline = deadline
        preliminary.save(update_fields=["objection_deadline"])
    sent = []
    postal_only = []
    failed = []

    for entry in preliminary.entries.select_related(
        "application", "application__applicant", "application__announcement"
    ).all():
        app = entry.application
        deadline_str = (
            f"{entry.objection_deadline:%d/%m/%Y}" if entry.objection_deadline else ""
        )
        if entry.status == RankingEntry.Status.ELIGIBLE:
            outcome, comm = send_workflow_notification(
                app,
                "preliminaryBeneficiaryEmailSubject",
                "preliminaryBeneficiaryEmailBody",
                {"rank": entry.proposed_rank, "objection_deadline": deadline_str},
                section_ref="stage:prioritization",
                user=user,
            )
        else:
            outcome, comm = send_workflow_notification(
                app,
                "preliminaryRejectedEmailSubject",
                "preliminaryRejectedEmailBody",
                {"objection_deadline": deadline_str},
                section_ref="stage:prioritization",
                user=user,
            )
        if outcome == "sent":
            sent.append(app)
        elif outcome == "postal_only":
            postal_only.append(app)
        else:
            failed.append(app)

    preliminary.notifications_sent_at = timezone.now()
    preliminary.save(update_fields=["notifications_sent_at"])
    cycle.stage = SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
    cycle.save(update_fields=["stage"])
    return {
        "ranking_list": preliminary,
        "sent": sent,
        "postal_only": postal_only,
        "failed": failed,
    }


@transaction.atomic
def confirm_letter_receipt(entry: RankingEntry, confirmed_on: date) -> RankingEntry:
    """Επιβεβαίωση λήψης της επιστολής από τον αιτητή (Ενότ. 6, 7).

    Αν η επιβεβαίωση γίνει εντός 5 ημερών (`plotApp.receiptConfirmationDays`) από την αποστολή,
    η 21ήμερη προθεσμία ένστασης μετρά από την ημερομηνία επιβεβαίωσης· διαφορετικά μετρά
    από την ημερομηνία ηλεκτρονικής αποστολής.
    """
    notified_date = (
        timezone.localtime(entry.notified_at).date()
        if entry.notified_at and timezone.is_aware(entry.notified_at)
        else (entry.notified_at.date() if entry.notified_at else timezone.localdate())
    )
    if confirmed_on < notified_date:
        raise AnnouncementWorkflowError(
            "Η ημερομηνία επιβεβαίωσης λήψης δεν μπορεί να προηγείται της ημερομηνίας αποστολής."
        )
    max_confirm_days = parameter("plotApp.receiptConfirmationDays")
    objection_days = parameter("plotApp.objectionDays")
    entry.receipt_confirmed_on = confirmed_on
    if (confirmed_on - notified_date).days <= max_confirm_days:
        effective_date = confirmed_on
    else:
        effective_date = notified_date
    entry.objection_deadline = effective_date + timedelta(days=objection_days)
    entry.save(update_fields=["receipt_confirmed_on", "objection_deadline"])

    rlist = entry.ranking_list
    all_deadlines = [
        e.objection_deadline
        for e in rlist.entries.all()
        if e.objection_deadline is not None
    ]
    if all_deadlines:
        rlist.objection_deadline = max(all_deadlines)
        rlist.save(update_fields=["objection_deadline"])
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Στάδιο 4: Ενστάσεις (Ενότ. 7) και μετάβαση στο Στάδιο 5 (Τελικός Κατάλογος)
# ─────────────────────────────────────────────────────────────────────────────


@transaction.atomic
def refresh_time_based_stages(
    cycle: SubmissionCycle, *, today: date | None = None
) -> bool:
    """Ενημερώνει τη γνωστοποίηση μετά την έκδοση του Προκαταρκτικού Καταλόγου:
    - Στο Στάδιο 4 (`objections_committee`) μόλις γνωστοποιηθεί ο κατάλογος ή, αν δεν
      γνωστοποιήθηκε, μόλις παρέλθουν οι 21 ημέρες ενστάσεων.
    - Κλείνει την περίοδο ενστάσεων (`objections_closed_on`) μόλις παρέλθουν οι 21 ημέρες για όλους
      τους αιτητές· οι αιτήσεις περνούν από «Προκαταρκτικός κατάλογος — Ενστάσεις» σε «Επιτροπή
      Εξέτασης Ενστάσεων».
    """
    check_date = today or timezone.localdate()
    state = community_lists(cycle)
    if state.preliminary is None or state.final is not None:
        return False
    period_open = state.objections_open(check_date)
    changed = []
    if cycle.stage in (
        SubmissionCycle.Stage.DETAILS,
        SubmissionCycle.Stage.SUBMISSION,
        SubmissionCycle.Stage.APPLICATIONS_COMMITTEE,
    ) and (
        state.preliminary.notifications_sent_at is not None or not period_open
    ):
        cycle.stage = SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        changed.append("stage")
    if not period_open and cycle.objections_closed_on is None:
        deadline = state.objection_deadline
        cycle.objections_closed_on = deadline + timedelta(days=1) if deadline else check_date
        changed.append("objections_closed_on")
    if not changed:
        return False
    cycle.save(update_fields=changed)
    for entry in state.preliminary.entries.select_related("application").all():
        if entry.application_id:
            apply_evaluation(entry.application)
    return True


def objection_period_warning(state) -> str:
    """Η κόκκινη προειδοποίηση όταν ζητείται μετάβαση στο Στάδιο 5 πριν λήξει η περίοδος ενστάσεων."""
    deadline = state.objection_deadline
    deadline_text = f"{deadline:%d/%m/%Y}" if deadline else "—"
    return (
        f"Η περίοδος ενστάσεων των 21 ημερών (Ενότ. 7(α)) λήγει στις {deadline_text}. Αν προχωρήσετε "
        "τώρα στον Τελικό Κατάλογο, οι αιτητές που δεν έχουν υποβάλει ακόμη ένσταση δεν θα μπορούν να "
        "υποβάλουν, και ο Τελικός Κατάλογος θα καταρτιστεί πριν από την πάροδο της προθεσμίας, σε "
        "απόκλιση από την Ενότ. 7(ε). Η αποδοχή καταγράφεται στο ιστορικό."
    )


@transaction.atomic
def start_final_list(
    cycle: SubmissionCycle,
    *,
    accept_open_period: bool = False,
    today: date | None = None,
) -> SubmissionCycle:
    """Στάδιο 4 → Στάδιο 5: κατάρτιση Τελικού Καταλόγου από τον Έπαρχο (Ενότ. 7(ε)).

    Απαιτεί απόφαση σε όλες τις ενστάσεις και καμία εκκρεμότητα. Πριν από τη λήξη των 21 ημερών
    η μετάβαση γίνεται μόνο με ρητή αποδοχή της προειδοποίησης (`accept_open_period`).
    """
    check_date = today or timezone.localdate()
    refresh_time_based_stages(cycle, today=check_date)
    state = community_lists(cycle)
    if state.preliminary is None or state.preliminary.notifications_sent_at is None:
        raise AnnouncementWorkflowError(
            "Πρέπει πρώτα να εκδοθεί και να γνωστοποιηθεί ο Προκαταρκτικός Κατάλογος (Στάδιο 3)."
        )
    if state.final is not None or cycle.stage != SubmissionCycle.Stage.OBJECTIONS_COMMITTEE:
        raise AnnouncementWorkflowError(
            "Η γνωστοποίηση δεν βρίσκεται στο Στάδιο 4 (Ενστάσεις)."
        )
    _check_no_open_objections_or_pending_items(
        cycle, "να ξεκινήσει η κατάρτιση του Τελικού Καταλόγου"
    )
    fields = ["stage"]
    if state.objections_open(check_date):
        if not accept_open_period:
            raise ObjectionPeriodOpenError(objection_period_warning(state))
        cycle.objections_closed_on = check_date
        cycle.objections_closed_early = True
        fields += ["objections_closed_on", "objections_closed_early"]
    cycle.stage = SubmissionCycle.Stage.FINAL_LIST
    cycle._section_ref = "stage:final_list"
    cycle.save(update_fields=fields)
    for entry in state.preliminary.entries.select_related("application").all():
        if entry.application_id:
            apply_evaluation(entry.application)
    return cycle


@transaction.atomic
def register_objection(
    application: PlotApplication,
    *,
    submitted_on: date | None = None,
    objection_type: str = "",
    grounds: str = "",
) -> Objection:
    """Καταχώριση ένστασης αιτητή εντός της 21ήμερης προθεσμίας (Ενότ. 7)."""
    state = community_lists(application.announcement)
    if state.preliminary is None:
        raise AnnouncementWorkflowError(
            "Δεν έχει εκδοθεί Προκαταρκτικός Κατάλογος για την υποβολή ένστασης."
        )
    if state.final is not None:
        raise AnnouncementWorkflowError(
            "Ο Τελικός Κατάλογος έχει ήδη εκδοθεί· δεν επιτρέπεται νέα ένσταση."
        )
    if state.cycle is not None and state.cycle.objections_closed_early:
        raise AnnouncementWorkflowError(
            f"Η περίοδος ενστάσεων έκλεισε στις {state.cycle.objections_closed_on:%d/%m/%Y}, πριν από "
            "τη λήξη της προθεσμίας, με τη μετάβαση στο Στάδιο 5 (Τελικός Κατάλογος)."
        )
    entry = state.preliminary.entries.filter(application=application).first()
    if entry is None:
        raise AnnouncementWorkflowError(
            "Η αίτηση δεν περιλαμβάνεται στον Προκαταρκτικό Κατάλογο."
        )
    sub_date = submitted_on or timezone.localdate()
    deadline = entry.objection_deadline or state.preliminary.objection_deadline
    if deadline is not None and sub_date > deadline:
        raise AnnouncementWorkflowError(
            f"Η προθεσμία υποβολής ένστασης ({deadline:%d/%m/%Y}) έχει παρέλθει (Ενότ. 7)."
        )
    clean_grounds = (grounds or "").strip()
    if not clean_grounds:
        raise AnnouncementWorkflowError("Η ένσταση πρέπει να είναι δεόντως αιτιολογημένη (Ενότ. 7).")
    if not objection_type:
        objection_type = (
            Objection.ObjectionType.REJECTION
            if entry.status == RankingEntry.Status.REJECTED
            else Objection.ObjectionType.RANK
        )
    return Objection.objects.create(
        application=application,
        preliminary_entry=entry,
        submitted_on=sub_date,
        objection_type=objection_type,
        grounds=clean_grounds,
    )


@transaction.atomic
def add_pending_requirement(
    application: PlotApplication,
    description: str,
    *,
    objection: Objection | None = None,
) -> PendingRequirement:
    """Προσθήκη εκκρεμότητας (checkbox + περιγραφή) σε αίτηση με ένσταση (Στάδιο 3)."""
    if not application.has_registered_objection and objection is None:
        raise AnnouncementWorkflowError(
            "Επιπλέον στοιχεία στο Στάδιο 3 ζητούνται μόνο για αιτήσεις με καταχωρισμένη ένσταση (Ενότ. 7)."
        )
    clean_desc = (description or "").strip()
    if not clean_desc:
        raise AnnouncementWorkflowError("Συμπληρώστε την περιγραφή του στοιχείου που εκκρεμεί.")
    target_objection = objection or application.objections.order_by("-id").first()
    return PendingRequirement.objects.create(
        application=application,
        objection=target_objection,
        description=clean_desc,
        is_fulfilled=False,
    )


@transaction.atomic
def toggle_pending_requirement(
    requirement: PendingRequirement,
    is_fulfilled: bool,
    *,
    fulfilled_on: date | None = None,
) -> PendingRequirement:
    """Ενημέρωση checkbox εκκρεμότητας. Η αίτηση παύει να είναι pending μόνο όταν όλα γίνουν checked."""
    requirement.is_fulfilled = bool(is_fulfilled)
    requirement.fulfilled_on = (
        (fulfilled_on or timezone.localdate()) if requirement.is_fulfilled else None
    )
    requirement.save(update_fields=["is_fulfilled", "fulfilled_on", "updated_at"])
    return requirement


@transaction.atomic
def decide_objection(
    objection: Objection,
    status: str,
    decision_notes: str = "",
    *,
    decided_on: date | None = None,
    user=None,
) -> dict:
    """Απόφαση Επιτροπής Εξέτασης Ενστάσεων επί ένστασης και αποστολή email στον αιτητή (Ενότ. 7)."""
    if status not in (Objection.Status.UPHELD, Objection.Status.DISMISSED):
        raise AnnouncementWorkflowError("Επιλέξτε έγκυρη απόφαση ένστασης (Ικανοποιήθηκε / Δεν ικανοποιήθηκε).")
    app = objection.application
    if app.is_pending_extra_info:
        raise AnnouncementWorkflowError(
            "Δεν μπορεί να ληφθεί απόφαση επί της ένστασης όσο εκκρεμεί προσκόμιση επιπλέον στοιχείων."
        )
    objection.status = status
    objection.decided_on = decided_on or timezone.localdate()
    objection.decision_notes = (decision_notes or "").strip()
    objection.outcome_notified_at = timezone.now()
    objection.save()

    if status == Objection.Status.UPHELD:
        subj_key, body_key = "objectionUpheldEmailSubject", "objectionUpheldEmailBody"
    else:
        subj_key, body_key = "objectionDismissedEmailSubject", "objectionDismissedEmailBody"

    outcome, comm = send_workflow_notification(
        app,
        subj_key,
        body_key,
        {"decision_notes": objection.decision_notes or "—"},
        section_ref="stage:objections_committee",
        user=user,
    )
    return {"objection": objection, "email_outcome": outcome, "communication": comm}


@transaction.atomic
def issue_final_list_and_notify(
    cycle: SubmissionCycle,
    *,
    user=None,
    decided_on: date | None = None,
) -> dict:
    """Έκδοση Τελικού Καταλόγου Δικαιούχων (Στάδιο 5 → Στάδιο 6, Ενότ. 7, 8) και αποστολή email:
    - Οι πρώτοι N δικαιούχοι (όπου N = αριθμός οικοπέδων της γνωστοποίησης) λαμβάνουν email δικαιούχου οικοπέδου.
    - Οι υπόλοιποι δικαιούχοι (θέση > N) λαμβάνουν διαφορετικό email ως επιλαχόντες.
    """
    refresh_time_based_stages(cycle, today=decided_on)
    final_list = issue_final_list(cycle, user, today=decided_on)
    cycle.refresh_from_db()
    if cycle.stage != SubmissionCycle.Stage.LOTTERY:
        cycle.stage = SubmissionCycle.Stage.LOTTERY
        cycle.save(update_fields=["stage"])
        for entry in final_list.entries.select_related("application").all():
            if entry.application_id:
                apply_evaluation(entry.application)

    plots_count = final_list.plots_count or 0
    sent_beneficiaries = []
    sent_runner_ups = []
    postal_only = []
    failed = []

    for entry in final_list.entries.select_related(
        "application", "application__applicant", "application__announcement"
    ).all():
        if entry.status == RankingEntry.Status.REJECTED:
            continue
        app = entry.application
        rank = entry.finalized_rank or entry.proposed_rank
        if entry.status == RankingEntry.Status.ELIGIBLE:
            outcome, _comm = send_workflow_notification(
                app,
                "finalPlotBeneficiaryEmailSubject",
                "finalPlotBeneficiaryEmailBody",
                {"rank": rank, "plots_count": plots_count},
                section_ref="stage:final_list",
                user=user,
            )
            if outcome == "sent":
                sent_beneficiaries.append(app)
            elif outcome == "postal_only":
                postal_only.append(app)
            else:
                failed.append(app)
        elif entry.status == RankingEntry.Status.ALTERNATE:
            outcome, _comm = send_workflow_notification(
                app,
                "finalRunnerUpEmailSubject",
                "finalRunnerUpEmailBody",
                {"rank": rank, "plots_count": plots_count},
                section_ref="stage:final_list",
                user=user,
            )
            if outcome == "sent":
                sent_runner_ups.append(app)
            elif outcome == "postal_only":
                postal_only.append(app)
            else:
                failed.append(app)

    final_list.notifications_sent_at = timezone.now()
    final_list.save(update_fields=["notifications_sent_at"])
    return {
        "ranking_list": final_list,
        "sent_beneficiaries": sent_beneficiaries,
        "sent_runner_ups": sent_runner_ups,
        "postal_only": postal_only,
        "failed": failed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Στάδιο 6: Κλήρωση Οικοπέδων (Ενότ. 9)
# ─────────────────────────────────────────────────────────────────────────────


@transaction.atomic
def schedule_lottery(
    cycle: SubmissionCycle,
    lottery_date: datetime | date,
    location: str,
    *,
    comments: str = "",
    user=None,
) -> dict:
    """Προγραμματισμός φυσικής κλήρωσης οικοπέδων και αποστολή πρόσκλησης στους δικαιούχους (Ενότ. 9)."""
    state = community_lists(cycle)
    if state.final is None:
        raise AnnouncementWorkflowError(
            "Πρέπει πρώτα να εκδοθεί ο Τελικός Κατάλογος Δικαιούχων πριν από την κλήρωση."
        )
    clean_location = (location or "").strip()
    if not clean_location:
        raise AnnouncementWorkflowError("Συμπληρώστε τον τόπο διεξαγωγής της κλήρωσης (Ενότ. 9).")
    if isinstance(lottery_date, date) and not isinstance(lottery_date, datetime):
        lottery_dt = timezone.make_aware(datetime.combine(lottery_date, time(10, 0)))
    elif timezone.is_naive(lottery_date):
        lottery_dt = timezone.make_aware(lottery_date)
    else:
        lottery_dt = lottery_date

    lottery = (
        cycle.lotteries.filter(lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION)
        .order_by("-id")
        .first()
    )
    if lottery is None:
        lottery = Lottery.objects.create(
            submission_cycle=cycle,
            lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION,
            lottery_date=lottery_dt,
            location=clean_location,
            comments=comments,
        )
    else:
        lottery.lottery_date = lottery_dt
        lottery.location = clean_location
        if comments:
            lottery.comments = comments
        lottery.save()

    if cycle.stage != SubmissionCycle.Stage.LOTTERY:
        cycle.stage = SubmissionCycle.Stage.LOTTERY
        cycle.save(update_fields=["stage"])

    dt_local = timezone.localtime(lottery_dt)
    date_str = f"{dt_local:%d/%m/%Y %H:%M}"
    sent = []
    postal_only = []
    for entry in state.final.entries.filter(status=RankingEntry.Status.ELIGIBLE).select_related(
        "application", "application__applicant"
    ):
        outcome, _ = send_workflow_notification(
            entry.application,
            "lotteryInvitationEmailSubject",
            "lotteryInvitationEmailBody",
            {"lottery_date": date_str, "location": clean_location},
            section_ref="stage:lottery",
            user=user,
        )
        if outcome == "sent":
            sent.append(entry.application)
        elif outcome == "postal_only":
            postal_only.append(entry.application)

    return {"lottery": lottery, "sent": sent, "postal_only": postal_only}


@transaction.atomic
def record_lottery_result(
    cycle: SubmissionCycle,
    assignments: dict,
    *,
    lottery: Lottery | None = None,
) -> list[Allocation]:
    """Καταχώριση αποτελέσματος φυσικής κλήρωσης: αντιστοίχιση δικαιούχου -> οικοπέδου (Ενότ. 9)."""
    state = community_lists(cycle)
    if state.final is None:
        raise AnnouncementWorkflowError("Δεν έχει εκδοθεί Τελικός Κατάλογος Δικαιούχων.")
    eligible_ids = set(
        state.final.entries.filter(status=RankingEntry.Status.ELIGIBLE).values_list(
            "application_id", flat=True
        )
    )
    offered_plots = {plot.pk: plot for plot in cycle.plots.all()}
    if not assignments:
        raise AnnouncementWorkflowError("Δεν δόθηκαν αντιστοιχίσεις οικοπέδων.")

    if lottery is None:
        lottery = (
            cycle.lotteries.filter(lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION)
            .order_by("-id")
            .first()
        )
        if lottery is None:
            lottery = Lottery.objects.create(
                submission_cycle=cycle,
                lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION,
                lottery_date=timezone.now(),
                location="Επαρχιακή Διοίκηση",
            )

    normalized: list[tuple[PlotApplication, Plot]] = []
    chosen_plot_ids: set[int] = set()
    for app_key, plot_key in assignments.items():
        app = (
            app_key
            if isinstance(app_key, PlotApplication)
            else PlotApplication.objects.get(pk=int(app_key))
        )
        plot_id = plot_key.pk if isinstance(plot_key, Plot) else int(plot_key)
        if app.pk not in eligible_ids:
            raise AnnouncementWorkflowError(
                f"Η αίτηση {app.protocol_number} δεν είναι δικαιούχος οικοπέδου στον Τελικό Κατάλογο."
            )
        if plot_id not in offered_plots:
            raise AnnouncementWorkflowError(
                "Το επιλεγμένο οικόπεδο δεν ανήκει στα προσφερόμενα οικόπεδα της γνωστοποίησης."
            )
        if plot_id in chosen_plot_ids:
            raise AnnouncementWorkflowError(
                f"Το οικόπεδο {offered_plots[plot_id].number or offered_plots[plot_id].row_label} επιλέχθηκε περισσότερες από μία φορές."
            )
        chosen_plot_ids.add(plot_id)
        normalized.append((app, offered_plots[plot_id]))

    created_allocations: list[Allocation] = []
    for app, plot in normalized:
        # Cancel or update any previous active allocation of this application in the lottery
        existing = (
            Allocation.objects.filter(application=app, status=Allocation.Status.ACTIVE)
            .order_by("-id")
            .first()
        )
        if existing is not None and existing.parcel_id != plot.pk:
            existing.delete()
            existing = None
        if existing is None:
            conflict = (
                Allocation.objects.filter(parcel=plot, status=Allocation.Status.ACTIVE)
                .exclude(application=app)
                .first()
            )
            if conflict is not None:
                raise AnnouncementWorkflowError(
                    f"Το οικόπεδο {plot.number or plot.row_label} είναι ήδη κατανεμημένο."
                )
            existing = Allocation.objects.create(
                lottery=lottery,
                application=app,
                parcel=plot,
                status=Allocation.Status.ACTIVE,
            )
        Payment.objects.get_or_create(
            allocation=existing,
            defaults={
                "amount": plot.disposal_price or Decimal("0.00"),
                "status": Payment.Status.PENDING,
            },
        )
        Agreement.objects.get_or_create(
            allocation=existing,
            defaults={
                "appointment_at": cycle.agreement_appointment_at,
                "deadline": cycle.agreement_deadline,
                "status": Agreement.Status.NOT_SIGNED,
            },
        )
        apply_evaluation(app)
        created_allocations.append(existing)

    return created_allocations


@transaction.atomic
def complete_lottery(cycle: SubmissionCycle) -> SubmissionCycle:
    """Ολοκλήρωση Σταδίου 6 (Κλήρωση) και μετάβαση στο Στάδιο 7 (Υπογραφή Συμφωνίας & Πληρωμή)."""
    state = community_lists(cycle)
    if state.final is None:
        raise AnnouncementWorkflowError("Δεν έχει εκδοθεί Τελικός Κατάλογος Δικαιούχων.")
    eligible_entries = list(
        state.final.entries.filter(status=RankingEntry.Status.ELIGIBLE).select_related("application")
    )
    missing = [
        entry.application.protocol_number
        for entry in eligible_entries
        if not entry.application.allocations.filter(status=Allocation.Status.ACTIVE).exists()
    ]
    if missing:
        raise AnnouncementWorkflowError(
            "Δεν έχει καταχωριστεί οικόπεδο κλήρωσης για όλες τις αιτήσεις δικαιούχων: "
            + ", ".join(missing)
            + "."
        )
    lottery = (
        cycle.lotteries.filter(lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION)
        .order_by("-id")
        .first()
    )
    if lottery is not None and lottery.completed_at is None:
        lottery.completed_at = timezone.now()
        lottery.save(update_fields=["completed_at"])

    cycle.stage = SubmissionCycle.Stage.AGREEMENTS
    cycle.save(update_fields=["stage"])
    for entry in eligible_entries:
        apply_evaluation(entry.application)
    _close_announcement_if_agreements_completed(cycle)
    return cycle


def _close_announcement_if_agreements_completed(cycle: SubmissionCycle) -> bool:
    """Ολοκληρώνει τη γνωστοποίηση (`Stage.CLOSED`) μόλις ολοκληρωθεί το Στάδιο 7:
    - Όλες οι ενεργές κατανομές έχουν υπογεγραμμένη Συμφωνία και εξοφλημένη Πληρωμή, ΚΑΙ
    - Δεν υπάρχουν αδιάθετα οικόπεδα που μπορούν να ανατεθούν σε διαθέσιμο επιλαχόντα, ΚΑΙ
    - Υπήρξε τουλάχιστον μία κατανομή (ενεργή ή ακυρωθείσα) ή δεν υπήρχαν δικαιούχοι στον Τελικό Κατάλογο.
    Τα οικόπεδα της γνωστοποίησης που δεν δόθηκαν (χωρίς ενεργή κατανομή) απελευθερώνονται αυτόματα
    και γίνονται ξανά διαθέσιμα για νέα γνωστοποίηση.
    """
    cycle.refresh_from_db(fields=["stage"])
    if cycle.stage != SubmissionCycle.Stage.AGREEMENTS:
        return False
    active_allocs = list(
        Allocation.objects.filter(
            application__announcement=cycle, status=Allocation.Status.ACTIVE
        ).select_related("agreement", "payment")
    )
    if not all(
        getattr(a, "agreement", None) is not None
        and a.agreement.status == Agreement.Status.SIGNED
        and getattr(a, "payment", None) is not None
        and a.payment.status == Payment.Status.PAID
        for a in active_allocs
    ):
        return False

    allocated_plot_ids = {a.parcel_id for a in active_allocs}
    has_unallocated_plots = cycle.plots.exclude(pk__in=allocated_plot_ids).exists()
    if has_unallocated_plots and available_runner_ups(cycle):
        return False

    any_allocations = bool(active_allocs) or Allocation.objects.filter(
        application__announcement=cycle
    ).exists()
    if not any_allocations:
        state = community_lists(cycle)
        if state.final is None or state.final.entries.filter(
            status=RankingEntry.Status.ELIGIBLE
        ).exists():
            return False

    cycle.stage = SubmissionCycle.Stage.CLOSED
    cycle._section_ref = "stage:agreement"
    cycle.save(update_fields=["stage"])
    return True


@transaction.atomic
def complete_agreements(
    cycle: SubmissionCycle,
    *,
    accept_open_submission: bool = False,
    today: date | None = None,
) -> SubmissionCycle:
    """Ολοκλήρωση της γνωστοποίησης (`Stage.CLOSED`):
    - Στο Στάδιο 7 (`agreements`): όταν όλες οι ενεργές κατανομές έχουν υπογεγραμμένη Συμφωνία και εξοφλημένη Πληρωμή.
    - Στο Στάδιο 6 (`lottery`): όταν δεν υπάρχουν δικαιούχοι οικοπέδου στον Τελικό Κατάλογο.
    - Στο Στάδιο 2 (`submission`): όταν δεν υπάρχουν πλήρεις αιτήσεις (0 αιτήσεις ή όλες απορριφθείσες ως ελλιπείς).

    Τα οικόπεδα της γνωστοποίησης που δεν δόθηκαν (χωρίς ενεργή κατανομή) απελευθερώνονται
    και γίνονται ξανά διαθέσιμα για νέα γνωστοποίηση (Ενότ. 8).
    """
    if cycle.stage == SubmissionCycle.Stage.CLOSED:
        return cycle

    if cycle.stage == SubmissionCycle.Stage.SUBMISSION:
        if not cycle.is_published:
            raise AnnouncementWorkflowError(
                "Η γνωστοποίηση πρέπει πρώτα να οριστικοποιηθεί/εκδοθεί (9.3)."
            )
        _check_no_blockers(cycle)
        if cycle.applications.exclude(application_stage=ApplicationStage.REJECTED).exists():
            raise AnnouncementWorkflowError(
                "Υπάρχουν πλήρεις αιτήσεις στη γνωστοποίηση· προχωρήστε στο Στάδιο 3 (Επιτροπή Εξέτασης Αιτήσεων)."
            )
        check_date = today or timezone.localdate()
        fields = ["stage"]
        if cycle.submission_open(check_date):
            if not accept_open_submission:
                raise SubmissionPeriodOpenError(submission_period_warning(cycle))
            cycle.submission_closed_early = True
            fields.append("submission_closed_early")
        cycle.stage = SubmissionCycle.Stage.CLOSED
        cycle._section_ref = "stage:submission"
        cycle.save(update_fields=fields)
        return cycle

    state = community_lists(cycle)
    if state.final is None:
        raise AnnouncementWorkflowError("Δεν έχει εκδοθεί Τελικός Κατάλογος Δικαιούχων.")

    if cycle.stage == SubmissionCycle.Stage.LOTTERY:
        if state.final.entries.filter(status=RankingEntry.Status.ELIGIBLE).exists():
            raise AnnouncementWorkflowError(
                "Υπάρχουν δικαιούχοι οικοπέδου στον Τελικό Κατάλογο· ολοκληρώστε πρώτα την κλήρωση οικοπέδων (Στάδιο 6)."
            )
        cycle.stage = SubmissionCycle.Stage.CLOSED
        cycle._section_ref = "stage:lottery"
        cycle.save(update_fields=["stage"])
        return cycle

    if cycle.stage != SubmissionCycle.Stage.AGREEMENTS:
        raise AnnouncementWorkflowError(
            "Η γνωστοποίηση δεν βρίσκεται στο Στάδιο 7 (Υπογραφή συμφωνίας και πληρωμή)."
        )
    active_allocs = list(
        Allocation.objects.filter(
            application__announcement=cycle, status=Allocation.Status.ACTIVE
        ).select_related("application", "agreement", "payment")
    )
    pending = [
        a.application.protocol_number
        for a in active_allocs
        if getattr(a, "agreement", None) is None
        or a.agreement.status != Agreement.Status.SIGNED
        or getattr(a, "payment", None) is None
        or a.payment.status != Payment.Status.PAID
    ]
    if pending:
        raise AnnouncementWorkflowError(
            "Δεν έχουν ολοκληρωθεί οι υπογραφές και πληρωμές (ή η απόρριψη/αποδέσμευση) για τις ενεργές κατανομές: "
            + ", ".join(pending)
            + "."
        )
    cycle.stage = SubmissionCycle.Stage.CLOSED
    cycle._section_ref = "stage:agreement"
    cycle.save(update_fields=["stage"])
    return cycle


# ─────────────────────────────────────────────────────────────────────────────
# Στάδιο 7: Συμφωνία Παραχώρησης, Πληρωμή & Αντικατάσταση από Επιλαχόντα (Ενότ. 8, 9, 12, 15)
# ─────────────────────────────────────────────────────────────────────────────


@transaction.atomic
def invite_to_agreement(
    allocation: Allocation,
    *,
    appointment_at: datetime | date | None = None,
    deadline: date | None = None,
    location: str | None = None,
    user=None,
) -> dict:
    """Αποστολή πρόσκλησης στον δικαιούχο να προσέλθει συγκεκριμένη ημερομηνία για πληρωμή & υπογραφή (Ενότ. 9, 12, 15)."""
    cycle = allocation.application.announcement
    if appointment_at is not None:
        if isinstance(appointment_at, date) and not isinstance(appointment_at, datetime):
            appt_dt = timezone.make_aware(datetime.combine(appointment_at, time(10, 0)))
        elif timezone.is_naive(appointment_at):
            appt_dt = timezone.make_aware(appointment_at)
        else:
            appt_dt = appointment_at
    else:
        appt_dt = cycle.agreement_appointment_at or timezone.now()

    target_deadline = deadline or cycle.agreement_deadline or (timezone.localdate() + timedelta(days=30))
    target_location = (location if location is not None else cycle.agreement_location) or "Επαρχιακή Διοίκηση"
    if cycle is not None and location is not None:
        clean_loc = location.strip() or "Επαρχιακή Διοίκηση"
        if cycle.agreement_location != clean_loc:
            cycle.agreement_location = clean_loc
            cycle.save(update_fields=["agreement_location"])

    agreement, _ = Agreement.objects.get_or_create(allocation=allocation)
    agreement.appointment_at = appt_dt
    agreement.deadline = target_deadline
    agreement.invited_at = timezone.now()
    agreement.save()

    payment, _ = Payment.objects.get_or_create(
        allocation=allocation,
        defaults={"amount": allocation.parcel.disposal_price or Decimal("0.00")},
    )

    appt_local = timezone.localtime(appt_dt) if timezone.is_aware(appt_dt) else appt_dt
    outcome, comm = send_workflow_notification(
        allocation.application,
        "agreementInvitationEmailSubject",
        "agreementInvitationEmailBody",
        {
            "plot_number": allocation.parcel.number or allocation.parcel.row_label,
            "disposal_price": f"{payment.amount:.2f}",
            "appointment_date": f"{appt_local:%d/%m/%Y %H:%M}",
            "location": target_location,
            "agreement_deadline": f"{target_deadline:%d/%m/%Y}",
        },
        section_ref="stage:agreement",
        user=user,
    )
    apply_evaluation(allocation.application)
    return {"agreement": agreement, "email_outcome": outcome, "communication": comm}


@transaction.atomic
def record_signature_and_payment(
    allocation: Allocation,
    *,
    signed: bool = True,
    signed_on: date | None = None,
    paid: bool = True,
    paid_on: date | None = None,
    amount: Decimal | None = None,
    comments: str = "",
) -> Allocation:
    """Καταχώριση πληρωμής (25% Γενικής Εκτίμησης) και υπογραφής Συμφωνίας Παραχώρησης (Ενότ. 12, 15)."""
    today = timezone.localdate()
    plot = allocation.parcel
    agreement, _ = Agreement.objects.get_or_create(allocation=allocation)
    payment, _ = Payment.objects.get_or_create(
        allocation=allocation,
        defaults={"amount": plot.disposal_price or Decimal("0.00")},
    )
    if amount is not None:
        payment.amount = amount
    if paid:
        payment.status = Payment.Status.PAID
        payment.paid_on = paid_on or today
    else:
        payment.status = Payment.Status.PENDING
        payment.paid_on = None
    if comments:
        payment.comments = comments
    payment.save()

    if signed:
        agreement.status = Agreement.Status.SIGNED
        agreement.signed_on = signed_on or today
    else:
        agreement.status = Agreement.Status.NOT_SIGNED
        agreement.signed_on = None
    if comments:
        agreement.comments = comments
    agreement.save()

    app = allocation.application
    apply_evaluation(app)

    cycle = app.announcement
    _close_announcement_if_agreements_completed(cycle)

    return allocation


def available_runner_ups(cycle: SubmissionCycle) -> list[PlotApplication]:
    """Επιλαχόντες του Τελικού Καταλόγου κατά σειρά προτεραιότητας που δεν έχουν λάβει οικόπεδο ούτε έχουν εκπέσει."""
    state = community_lists(cycle)
    if state.final is None:
        return []
    entries = (
        state.final.entries.filter(status=RankingEntry.Status.ALTERNATE)
        .select_related("application", "application__applicant", "application__spouse")
        .order_by("finalized_rank", "proposed_rank", "id")
    )
    result = []
    for entry in entries:
        app = entry.application
        if app.forfeited or app.incomplete_rejected:
            continue
        if app.allocations.filter(status=Allocation.Status.ACTIVE).exists():
            continue
        result.append(app)
    return result


def next_runner_up(cycle: SubmissionCycle) -> PlotApplication | None:
    """Ο αμέσως επόμενος επιλαχών κατά σειρά προτεραιότητας του Τελικού Καταλόγου (Ενότ. 8)."""
    runners = available_runner_ups(cycle)
    return runners[0] if runners else None


@transaction.atomic
def forfeit_allocation(
    allocation: Allocation,
    *,
    reason: str = "",
    agreement_status: str = Agreement.Status.NOT_SIGNED,
    payment_status: str = Payment.Status.UNPAID,
    forfeited_on: date | None = None,
) -> dict:
    """Έκπτωση/απόρριψη δικαιούχου που δεν προσήλθε να πληρώσει ή να υπογράψει (Ενότ. 8).

    Ακυρώνει την κατανομή, απορρίπτει την αίτηση (`ApplicationStage.FORFEITED`) και επιστρέφει
    τον προτεινόμενο επόμενο επιλαχόντα καθώς και τη λίστα διαθέσιμων επιλαχόντων.
    """
    clean_reason = (reason or "").strip() or "Μη προσέλευση / μη υπογραφή Συμφωνίας / μη πληρωμή τιμής διάθεσης."
    app = allocation.application
    plot = allocation.parcel
    cycle = app.announcement
    f_date = forfeited_on or timezone.localdate()

    agreement, _ = Agreement.objects.get_or_create(allocation=allocation)
    if agreement_status in (Agreement.Status.NOT_SIGNED, Agreement.Status.NO_SHOW):
        agreement.status = agreement_status
    else:
        agreement.status = Agreement.Status.NOT_SIGNED
    agreement.comments = clean_reason
    agreement.save()

    payment, _ = Payment.objects.get_or_create(
        allocation=allocation,
        defaults={"amount": plot.disposal_price or Decimal("0.00")},
    )
    if payment_status in (Payment.Status.UNPAID, Payment.Status.PENDING):
        payment.status = payment_status
    else:
        payment.status = Payment.Status.UNPAID
    payment.comments = clean_reason
    payment.save()

    allocation.status = Allocation.Status.CANCELLED
    allocation.cancellation_reason = clean_reason
    allocation.save()

    app.forfeited = True
    app.forfeited_reason = clean_reason
    app.forfeited_on = f_date
    app._section_ref = "stage:agreement"
    app.save(update_fields=["forfeited", "forfeited_reason", "forfeited_on", "updated_at"])
    apply_evaluation(app)

    _close_announcement_if_agreements_completed(cycle)

    return {
        "forfeited_application": app,
        "plot": plot,
        "proposed_runner_up": next_runner_up(cycle),
        "available_runner_ups": available_runner_ups(cycle),
    }


@transaction.atomic
def promote_runner_up(
    cycle: SubmissionCycle,
    plot: Plot,
    runner_up_application: PlotApplication,
    *,
    replaces_allocation: Allocation | None = None,
    justification: str = "",
    appointment_at: datetime | date | None = None,
    deadline: date | None = None,
    location: str | None = None,
    user=None,
) -> dict:
    """Ανάθεση ελεύθερου οικοπέδου σε επιλαχόντα μετά από έκπτωση δικαιούχου (Ενότ. 8).

    Προτείνεται ο αμέσως επόμενος επιλαχών κατά σειρά Τελικού Καταλόγου· αν επιλεγεί άλλος
    επιλαχών, απαιτείται υποχρεωτική αιτιολογία (καταγράφεται στο ιστορικό).
    """
    runners = available_runner_ups(cycle)
    if runner_up_application not in runners:
        raise AnnouncementWorkflowError(
            "Η επιλεγμένη αίτηση δεν είναι διαθέσιμος επιλαχών στον Τελικό Κατάλογο της γνωστοποίησης."
        )
    if Allocation.objects.filter(parcel=plot, status=Allocation.Status.ACTIVE).exists():
        raise AnnouncementWorkflowError(
            f"Το οικόπεδο {plot.number or plot.row_label} έχει ήδη ενεργή κατανομή."
        )
    first_runner = runners[0]
    clean_justification = (justification or "").strip()
    if runner_up_application.pk != first_runner.pk and not clean_justification:
        raise AnnouncementWorkflowError(
            f"Ο αμέσως επόμενος επιλαχών κατά σειρά προτεραιότητας (Ενότ. 8) είναι η αίτηση "
            f"{first_runner.protocol_number}. Απαιτείται αιτιολογία για την επιλογή άλλου επιλαχόντα."
        )

    lottery = (
        cycle.lotteries.filter(lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION)
        .order_by("-id")
        .first()
    )
    new_alloc = Allocation.objects.create(
        lottery=lottery,
        application=runner_up_application,
        parcel=plot,
        replaces=replaces_allocation,
        runner_up_justification=clean_justification,
        status=Allocation.Status.ACTIVE,
    )
    payment = Payment.objects.create(
        allocation=new_alloc,
        amount=plot.disposal_price or Decimal("0.00"),
        status=Payment.Status.PENDING,
    )
    appt_dt = appointment_at or cycle.agreement_appointment_at or timezone.now()
    if isinstance(appt_dt, date) and not isinstance(appt_dt, datetime):
        appt_dt = timezone.make_aware(datetime.combine(appt_dt, time(10, 0)))
    elif timezone.is_naive(appt_dt):
        appt_dt = timezone.make_aware(appt_dt)
    target_deadline = deadline or cycle.agreement_deadline or (timezone.localdate() + timedelta(days=30))
    target_location = (location if location is not None else cycle.agreement_location) or "Επαρχιακή Διοίκηση"
    if cycle is not None and location is not None:
        clean_loc = location.strip() or "Επαρχιακή Διοίκηση"
        if cycle.agreement_location != clean_loc:
            cycle.agreement_location = clean_loc
            cycle.save(update_fields=["agreement_location"])

    agreement = Agreement.objects.create(
        allocation=new_alloc,
        appointment_at=appt_dt,
        deadline=target_deadline,
        invited_at=timezone.now(),
        status=Agreement.Status.NOT_SIGNED,
    )

    state = community_lists(cycle)
    if state.final is not None:
        final_entry = state.final.entries.filter(application=runner_up_application).first()
        if final_entry is not None and final_entry.status != RankingEntry.Status.ELIGIBLE:
            final_entry.status = RankingEntry.Status.ELIGIBLE
            final_entry.save(update_fields=["status", "updated_at"])

    apply_evaluation(runner_up_application)

    appt_local = timezone.localtime(appt_dt) if timezone.is_aware(appt_dt) else appt_dt
    outcome, comm = send_workflow_notification(
        runner_up_application,
        "runnerUpPromotionEmailSubject",
        "runnerUpPromotionEmailBody",
        {
            "plot_number": plot.number or plot.row_label,
            "disposal_price": f"{payment.amount:.2f}",
            "appointment_date": f"{appt_local:%d/%m/%Y %H:%M}",
            "location": target_location,
            "agreement_deadline": f"{target_deadline:%d/%m/%Y}",
        },
        section_ref="stage:agreement",
        user=user,
    )

    return {
        "allocation": new_alloc,
        "agreement": agreement,
        "payment": payment,
        "email_outcome": outcome,
        "communication": comm,
    }
