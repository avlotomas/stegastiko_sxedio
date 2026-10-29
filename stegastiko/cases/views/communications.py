"""2.2 deficiency emails, 3.1 land plot emails: sending and the read-only history modal."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import formats, timezone

from cases import section_refs as refs
from cases.forms import DeficiencyEmailForm
from cases.models import Case, CommunicationStatus, CompletenessCheck, LandPlot
from cases.services import (
    case_communications,
    communication_section,
    land_plot_communications,
    send_deficiency_email,
    send_land_plot_email,
)
from cases.views.common import case_for_section, wants_json
from cases.views.grids import COMPLETENESS_CHECKS, LAND_PLOTS
from core.function_catalog import SEND, case_section_function
from core.models import Communication
from core.permissions import require_access


@login_required
def case_deficiency_email_send(request, pk, check_id):
    """2.2 Send the deficiencies email for one completeness check."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    case = case_for_section(request, pk, refs.SECTION_2, SEND)
    check = get_object_or_404(CompletenessCheck, pk=check_id, case=case)

    form = DeficiencyEmailForm(request.POST)
    errors = []
    communication = None
    if form.is_valid():
        try:
            communication = send_deficiency_email(
                check, form.cleaned_data["subject"], form.cleaned_data["body"]
            )
        except ValidationError as exc:
            errors = exc.messages
    else:
        errors = [error for field_errors in form.errors.values() for error in field_errors]

    if communication:
        message = f"Το email ελλείψεων στάλθηκε στο {communication.recipient}."
    if wants_json(request):
        if not communication:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        log_html = render_to_string(
            "cases/_deficiency_email_log.html",
            {"case": case, "communications": case_communications(case)},
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                "message": message,
                "log_html": log_html,
                "grid_html": COMPLETENESS_CHECKS.grid_html(request, case),
            }
        )

    if communication:
        messages.success(request, message)
    else:
        for error in errors:
            messages.error(request, error)
    return redirect("cases:section_edit", pk=case.pk, section=refs.SECTION_2)


@login_required
def land_plot_email_send(request, pk, plot_id):
    """3.1 Send an email about one land plot to the Κ.Σ./Δ.Δ. contact address."""
    if request.method != "POST" or not wants_json(request):
        raise Http404("Επιτρέπεται μόνο POST.")
    case = case_for_section(request, pk, refs.SECTION_3, SEND)
    plot = get_object_or_404(LandPlot, pk=plot_id, case=case)

    form = DeficiencyEmailForm(request.POST)
    if not form.is_valid():
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    try:
        communication = send_land_plot_email(
            plot, form.cleaned_data["subject"], form.cleaned_data["body"]
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)

    log_html = render_to_string(
        "cases/_land_plot_email_log.html",
        {"case": case, "land_plot_communications": land_plot_communications(case)},
        request=request,
    )
    return JsonResponse(
        {
            "ok": True,
            "message": (
                f"Το email για το τεμάχιο {plot.parcel_number} στάλθηκε στο "
                f"{communication.recipient}."
            ),
            "log_html": log_html,
            "grid_html": LAND_PLOTS.grid_html(request, case),
        }
    )


def _communication_detail_payload(communication: Communication) -> dict:
    sent_at = ""
    if communication.sent_at:
        sent_at = formats.date_format(
            timezone.localtime(communication.sent_at), "SHORT_DATETIME_FORMAT"
        )
    return {
        "recipient": communication.recipient,
        "sender": communication.sender_label,
        "stage_label": communication.stage_label,
        "subject": communication.subject,
        "body": communication.body,
        "check_label": getattr(communication.content_object, "row_label", ""),
        "status": communication.status,
        "status_display": CommunicationStatus.label(communication.status),
        "sent_at": sent_at,
    }


@login_required
def case_communication_detail(request, pk, communication_id):
    """Return one sent email (2.2 or 3.1) for the history view modal."""
    case = get_object_or_404(Case, pk=pk)
    communication = (
        case_communications(case).filter(pk=communication_id).first()
        or get_object_or_404(land_plot_communications(case), pk=communication_id)
    )
    require_access(request.user, case_section_function(communication_section(communication)))
    if request.method != "GET":
        raise Http404("Επιτρέπεται μόνο GET.")
    if not wants_json(request):
        raise Http404()
    return JsonResponse({"ok": True, **_communication_detail_payload(communication)})
