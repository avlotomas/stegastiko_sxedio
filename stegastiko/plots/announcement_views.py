"""Ενότητα 9 — Γνωστοποιήσεις και ροή 7 σταδίων."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from allocation.models import Agreement, Allocation, Lottery, Payment, RankingEntry
from cases.models import SubmissionCycle, SubmissionCyclePublication
from cases.views.common import disable_fields
from cases.views.grid import GridEndpoint
from core.docx_merge import render_agreement_docx
from core.function_catalog import CREATE, EDIT, EXPORT, PUBLISH
from core.models import Community
from core.permissions import access_required, has_access, require_access
from plot_applications.announcement_workflow import (
    AnnouncementWorkflowError,
    ObjectionPeriodOpenError,
    SubmissionPeriodOpenError,
    add_pending_requirement,
    available_runner_ups,
    complete_agreements,
    complete_lottery,
    confirm_letter_receipt,
    decide_objection,
    forfeit_allocation,
    invite_to_agreement,
    issue_final_list_and_notify,
    next_runner_up,
    objection_period_warning,
    record_applications_committee_decision,
    record_lottery_result,
    record_signature_and_payment,
    refresh_time_based_stages,
    register_objection,
    schedule_lottery,
    start_applications_committee,
    start_final_list,
    submission_period_warning,
    toggle_pending_requirement,
    promote_runner_up,
)
from plot_applications.beneficiary_lists import (
    BeneficiaryListError,
    announcement_communications,
    blocking_applications,
    community_lists,
    list_changes,
    list_notifications,
    snapshot_listing,
)
from plot_applications.models import (
    Objection,
    PendingRequirement,
    PlotApplication,
)
from plot_applications.prioritization import build_prioritization_list
from plot_applications.rules import parameter
from plots.forms import (
    AnnouncementPlotsField,
    AnnouncementPlotsSelectionForm,
    PublicationDateForm,
    SubmissionCycleForm,
    SubmissionCyclePublicationForm,
)
from plots.models import Plot
from plots.notice_export import NoticeExportError, notice_filename, render_notice
from plots.services import create_announcement, publish_announcement

STAGE_STEPPER = (
    (SubmissionCycle.Stage.DETAILS, "1. Στοιχεία γνωστοποίησης"),
    (SubmissionCycle.Stage.SUBMISSION, "2. Υποβολή αιτήσεων"),
    (SubmissionCycle.Stage.APPLICATIONS_COMMITTEE, "3. Επιτροπή Εξέτασης Αιτήσεων"),
    (SubmissionCycle.Stage.OBJECTIONS_COMMITTEE, "4. Ενστάσεις"),
    (SubmissionCycle.Stage.FINAL_LIST, "5. Τελικός Κατάλογος Δικαιούχων"),
    (SubmissionCycle.Stage.LOTTERY, "6. Στάδιο κλήρωσης"),
    (SubmissionCycle.Stage.AGREEMENTS, "7. Υπογραφή συμφωνίας και πληρωμή"),
)
STAGE_ORDER = [code for code, _label in STAGE_STEPPER] + [SubmissionCycle.Stage.CLOSED]
STAGE_TEMPLATES = {
    SubmissionCycle.Stage.DETAILS: "plots/stages/_details.html",
    SubmissionCycle.Stage.SUBMISSION: "plots/stages/_submission.html",
    SubmissionCycle.Stage.APPLICATIONS_COMMITTEE: "plots/stages/_applications_committee.html",
    SubmissionCycle.Stage.OBJECTIONS_COMMITTEE: "plots/stages/_objections.html",
    SubmissionCycle.Stage.FINAL_LIST: "plots/stages/_final_list.html",
    SubmissionCycle.Stage.LOTTERY: "plots/stages/_lottery.html",
    SubmissionCycle.Stage.AGREEMENTS: "plots/stages/_agreements.html",
}


def _redirect_stage(cycle: SubmissionCycle, stage_code: str | None = None):
    url = reverse("announcements:detail", kwargs={"pk": cycle.pk})
    if stage_code:
        return redirect(f"{url}?stage={stage_code}")
    return redirect(url)


def _first_error(exc: ValidationError) -> str:
    return exc.messages[0] if exc.messages else str(exc)


@access_required("announcements")
def announcement_list(request):
    cycles = SubmissionCycle.objects.prefetch_related("plots__community")
    community_id = request.GET.get("community_id") or ""
    if community_id:
        cycles = cycles.filter(plots__community=community_id).distinct()
    return render(
        request,
        "plots/announcement_list.html",
        {
            "cycles": cycles,
            "communities": Community.objects.filter(is_active=True).order_by("name"),
            "community_id": community_id,
        },
    )


def _plot_choices():
    """Step 1 of the wizard: available plots grouped by district and community.

    Communities without available plots are not shown.
    """
    field = AnnouncementPlotsField(queryset=Plot.objects.none())
    plots = (
        Plot.objects.available()
        .filter(community__is_active=True)
        .select_related("community", "source_case")
        .order_by("community__district", "community__name", "id")
    )
    by_community = {}
    for plot in plots:
        by_community.setdefault(plot.community_id, []).append(
            {"plot": plot, "label": field.label_from_instance(plot)}
        )
    districts = {}
    for community in Community.objects.filter(is_active=True).order_by("district", "name"):
        community_plots = by_community.get(community.pk, [])
        if not community_plots:
            continue
        districts.setdefault(community.district, []).append(
            {"community": community, "plots": community_plots, "available": len(community_plots)}
        )
    return list(districts.items())


@access_required("announcements", CREATE)
def announcement_create(request):
    """9.1 New announcement, as a two-step wizard.

    Step 1 chooses the available plots (all belonging to a single Community); step 2
    takes the announcement date and submission period.
    """
    data = request.POST if request.method == "POST" else request.GET
    selection = None
    if request.method == "POST" or "next" in request.GET:
        selection = AnnouncementPlotsSelectionForm(data)
    form = None
    communities = []
    selected_plots = []
    if selection is not None and selection.is_valid():
        selected_plots = list(selection.cleaned_data["plots"])
        communities = list({p.community for p in selected_plots})
        if request.method == "POST":
            form = SubmissionCycleForm(request.POST, selected_plots=selected_plots)
            if form.is_valid():
                cycle = create_announcement(form)
                messages.success(
                    request,
                    "Δημιουργήθηκε η γνωστοποίηση (9.1). Μπορείτε να την εξάγετε με το κουμπί «Export».",
                )
                return redirect("announcements:detail", pk=cycle.pk)
        else:
            form = SubmissionCycleForm(selected_plots=selected_plots)
    return render(
        request,
        "plots/announcement_form.html",
        {
            "step": 2 if form is not None else 1,
            "selection": selection,
            "form": form,
            "communities": communities,
            "selected_plots": selected_plots,
            "district_groups": _plot_choices(),
            "selected_ids": {str(value) for value in data.getlist("plots")},
        },
    )


def _workspace_context(cycle: SubmissionCycle) -> dict:
    refresh_time_based_stages(cycle)
    state = community_lists(cycle)
    applications = list(
        cycle.applications.select_related("applicant", "spouse")
        .prefetch_related("pending_requirements", "objections")
        .order_by("protocol_number", "id")
    )
    blockers = list(blocking_applications(cycle))
    prioritization = (
        snapshot_listing(state.final)
        if state.final is not None
        else build_prioritization_list(cycle)
    )
    objections = list(
        Objection.objects.filter(application__announcement=cycle)
        .select_related("application", "application__applicant", "preliminary_entry")
        .prefetch_related("application__pending_requirements")
        .order_by("submitted_on", "id")
    )
    preliminary_entries = (
        list(
            state.preliminary.entries.select_related(
                "application", "application__applicant"
            ).order_by("proposed_rank", "id")
        )
        if state.preliminary
        else []
    )
    final_entries = (
        list(
            state.final.entries.select_related(
                "application", "application__applicant"
            ).order_by("finalized_rank", "id")
        )
        if state.final
        else []
    )
    eligible_final_entries = [
        e for e in final_entries if e.status == RankingEntry.Status.ELIGIBLE
    ]
    lottery = (
        cycle.lotteries.filter(lottery_type=Lottery.LotteryType.PARCEL_ALLOCATION)
        .order_by("-id")
        .first()
    )
    offered_plots = list(cycle.plots.select_related("community").order_by("id"))
    active_allocations = list(
        Allocation.objects.filter(
            application__announcement=cycle, status=Allocation.Status.ACTIVE
        )
        .select_related("application", "application__applicant", "parcel", "agreement", "payment")
        .order_by("id")
    )
    allocated_plot_ids = {alloc.parcel_id for alloc in active_allocations}
    unallocated_plots = [plot for plot in offered_plots if plot.pk not in allocated_plot_ids]
    alloc_by_app_id = {alloc.application_id: alloc for alloc in active_allocations}
    lottery_rows = [
        {
            "entry": entry,
            "application": entry.application,
            "allocation": alloc_by_app_id.get(entry.application_id),
        }
        for entry in eligible_final_entries
    ]
    runners = available_runner_ups(cycle)
    proposed_runner = next_runner_up(cycle)
    stage_index = STAGE_ORDER.index(cycle.stage) if cycle.stage in STAGE_ORDER else 0
    objection_period_open = state.objections_open() and not state.objections_closed
    submission_open = cycle.is_published and cycle.submission_open()
    days_remaining = cycle.submission_days_remaining()
    warning_days = parameter("plotApp.submissionDeadlineWarningDays")
    all_emails, emails_by_stage = announcement_communications(cycle, state=state)
    # Το Στάδιο 1 δεν στέλνει email (τα email αιτήσεων καταγράφονται από το Στάδιο 2 και μετά).
    stage_email_groups = [
        {
            "code": code,
            "label": label,
            "emails": emails_by_stage.get(code, []),
            "count": len(emails_by_stage.get(code, [])),
        }
        for code, label in STAGE_STEPPER
        if code != SubmissionCycle.Stage.DETAILS
    ]

    return {
        "stage_index": stage_index,
        "stage_done": {code: STAGE_ORDER.index(code) < stage_index for code, _label in STAGE_STEPPER},
        "submission_open": submission_open,
        "submission_days_remaining": days_remaining,
        "submission_deadline_warning": (
            submission_open and days_remaining is not None and days_remaining <= warning_days
        ),
        "submission_period_warning": submission_period_warning(cycle) if submission_open else "",
        "allocated_plot_ids": allocated_plot_ids,
        "lists": state,
        "preliminary_notifications": list_notifications(state.preliminary),
        "preliminary_listing": snapshot_listing(state.preliminary) if state.preliminary else None,
        "announcement_emails": all_emails,
        "emails_by_stage": emails_by_stage,
        "stage_email_groups": stage_email_groups,
        "objection_period_open": objection_period_open,
        "objection_period_warning": (
            objection_period_warning(state) if objection_period_open else ""
        ),
        "applications": applications,
        "blockers": blockers,
        "prioritization": prioritization,
        "list_changes": list_changes(state),
        "preliminary_entries": preliminary_entries,
        "final_entries": final_entries,
        "eligible_final_entries": eligible_final_entries,
        "objections": objections,
        "objection_types": Objection.ObjectionType.choices,
        "objection_statuses": (
            (Objection.Status.UPHELD, "Ικανοποιήθηκε"),
            (Objection.Status.DISMISSED, "Δεν ικανοποιήθηκε"),
        ),
        "lottery": lottery,
        "lottery_rows": lottery_rows,
        "offered_plots": offered_plots,
        "active_allocations": active_allocations,
        "unallocated_plots": unallocated_plots,
        "available_runner_ups": runners,
        "proposed_runner_up": proposed_runner,
        "complete_applications": [app for app in applications if not app.is_rejected_incomplete],
        "can_complete_without_applications": (
            cycle.is_published
            and cycle.stage == SubmissionCycle.Stage.SUBMISSION
            and not blockers
            and not any(not app.is_rejected_incomplete for app in applications)
        ),
        "can_complete_without_beneficiaries": (
            cycle.stage == SubmissionCycle.Stage.LOTTERY
            and state.final is not None
            and not eligible_final_entries
        ),
        "pending_agreement_allocations": [
            a
            for a in active_allocations
            if getattr(a, "agreement", None) is None
            or a.agreement.status != Agreement.Status.SIGNED
            or getattr(a, "payment", None) is None
            or a.payment.status != Payment.Status.PAID
        ],
        "can_complete_agreements": (
            cycle.stage == SubmissionCycle.Stage.AGREEMENTS
            and state.final is not None
            and all(
                getattr(a, "agreement", None) is not None
                and a.agreement.status == Agreement.Status.SIGNED
                and getattr(a, "payment", None) is not None
                and a.payment.status == Payment.Status.PAID
                for a in active_allocations
            )
        ),
        "can_complete_announcement": (
            (
                cycle.stage == SubmissionCycle.Stage.AGREEMENTS
                and state.final is not None
                and all(
                    getattr(a, "agreement", None) is not None
                    and a.agreement.status == Agreement.Status.SIGNED
                    and getattr(a, "payment", None) is not None
                    and a.payment.status == Payment.Status.PAID
                    for a in active_allocations
                )
            )
            or (
                cycle.stage == SubmissionCycle.Stage.LOTTERY
                and state.final is not None
                and not eligible_final_entries
            )
            or (
                cycle.is_published
                and cycle.stage == SubmissionCycle.Stage.SUBMISSION
                and not blockers
                and not any(not app.is_rejected_incomplete for app in applications)
                and not submission_open
            )
        ),
    }


def _stage_tabs(
    cycle: SubmissionCycle,
    stage_index: int,
    requested: str | None,
    emails_by_stage: dict | None = None,
):
    """Τα στάδια ως καρτέλες: τρέχον και ολοκληρωμένα ανοίγουν, τα μελλοντικά είναι ανενεργά."""
    current = cycle.stage if cycle.stage in STAGE_TEMPLATES else STAGE_STEPPER[-1][0]
    available = {code for code, _label in STAGE_STEPPER if STAGE_ORDER.index(code) <= stage_index}
    selected = requested if requested in available else current
    steps = [
        {
            "code": code,
            "label": label,
            "done": STAGE_ORDER.index(code) < stage_index,
            "current": code == cycle.stage,
            "available": code in available,
            "selected": code == selected,
            "emails_count": len((emails_by_stage or {}).get(code, [])),
        }
        for code, label in STAGE_STEPPER
    ]
    return steps, selected


@access_required("announcements", post_action=EDIT)
def announcement_detail(request, pk):
    """9.1, 9.2, 9.3 and the 7-stage announcement workflow workspace (one stage per tab)."""
    cycle = get_object_or_404(SubmissionCycle.objects.prefetch_related("plots__community"), pk=pk)
    forms_args = {"data": request.POST} if request.method == "POST" else {}
    cycle_form = SubmissionCycleForm(instance=cycle, prefix="cycle", **forms_args)
    if forms_args and cycle_form.is_valid():
        with transaction.atomic():
            cycle_form.instance._section_ref = "9.1"
            cycle_form.save()
        messages.success(request, "Οι αλλαγές της γνωστοποίησης αποθηκεύτηκαν.")
        return _redirect_stage(cycle, SubmissionCycle.Stage.DETAILS)
    if not has_access(request.user, "announcements", EDIT):
        disable_fields(cycle_form)

    context = _workspace_context(cycle)
    requested = SubmissionCycle.Stage.DETAILS if forms_args else request.GET.get("stage")
    steps, selected = _stage_tabs(
        cycle, context["stage_index"], requested, context["emails_by_stage"]
    )
    selected_pos = next(i for i, step in enumerate(steps) if step["selected"])
    return render(
        request,
        "plots/announcement_detail.html",
        {
            "cycle": cycle,
            "cycle_form": cycle_form,
            **publication_rows(cycle),
            **context,
            "stage_stepper": steps,
            "selected_stage": selected,
            "selected_stage_label": dict(STAGE_STEPPER).get(selected, ""),
            "selected_stage_emails": context["emails_by_stage"].get(selected, []),
            "selected_stage_template": STAGE_TEMPLATES[selected],
            "prev_stage": steps[selected_pos - 1] if selected_pos > 0 else None,
            "next_stage": steps[selected_pos + 1] if selected_pos + 1 < len(steps) else None,
        },
        status=400 if forms_args else 200,
    )


@access_required("announcements")
def announcement_export(request, pk):
    """9.3 «Export»: the Πρότυπο 1 notice (.docx) filled in from the announcement."""
    cycle = get_object_or_404(SubmissionCycle.objects.prefetch_related("plots__community"), pk=pk)
    try:
        document = render_notice(cycle)
    except NoticeExportError as exc:
        messages.error(request, str(exc))
        return redirect("announcements:detail", pk=cycle.pk)
    return FileResponse(document, as_attachment=True, filename=notice_filename(cycle))


@access_required("announcements", PUBLISH)
def announcement_publish(request, pk):
    """9.3 Finalise and issue the announcement."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    try:
        publish_announcement(cycle)
    except ValidationError as exc:
        messages.error(request, _first_error(exc))
    else:
        messages.success(request, "Η ανακοίνωση οριστικοποιήθηκε και εκδόθηκε (9.3).")
    return redirect("announcements:detail", pk=cycle.pk)


# --- 7-stage workflow views -------------------------------------------------------------------


def _require_stage_edit(request, subfunction: str):
    if has_access(request.user, subfunction, EDIT) or has_access(
        request.user, "announcements", EDIT
    ):
        return
    require_access(request.user, subfunction, EDIT)


@login_required
def announcement_start_committee(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_committee")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    meeting_date = parse_date(request.POST.get("meeting_date") or "")
    accept = request.POST.get("accept_open_submission") in ("1", "true", "True", "on")
    try:
        start_applications_committee(
            cycle,
            meeting_date=meeting_date,
            accept_open_submission=accept,
            today=timezone.localdate(),
        )
    except SubmissionPeriodOpenError as exc:
        messages.error(
            request, f"{exc} Επιλέξτε «Αποδέχομαι» για να προχωρήσετε πριν από τη λήξη της προθεσμίας."
        )
        return _redirect_stage(cycle, SubmissionCycle.Stage.SUBMISSION)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
        return _redirect_stage(cycle, SubmissionCycle.Stage.SUBMISSION)
    if cycle.submission_closed_early:
        messages.warning(
            request,
            "Η γνωστοποίηση προχώρησε στο Στάδιο 3 (Επιτροπή Εξέτασης Αιτήσεων) πριν από τη λήξη της "
            "προθεσμίας υποβολής, κατόπιν αποδοχής της προειδοποίησης.",
        )
    else:
        messages.success(
            request, "Η γνωστοποίηση προχώρησε στο Στάδιο 3 (Επιτροπή Εξέτασης Αιτήσεων)."
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_committee_decision(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_committee")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    decided_on = parse_date(request.POST.get("decided_on") or "")
    try:
        result = record_applications_committee_decision(
            cycle, decided_on=decided_on, user=request.user
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        sent_cnt = len(result["sent"])
        postal_cnt = len(result["postal_only"])
        messages.success(
            request,
            f"Εκδόθηκε ο Προκαταρκτικός Κατάλογος Δικαιούχων (απεστάλησαν {sent_cnt} email"
            + (f", {postal_cnt} μόνο ταχυδρομικώς" if postal_cnt else "")
            + ")· η γνωστοποίηση προχώρησε στο Στάδιο 4 (Ενστάσεις).",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_confirm_receipt(request, pk, entry_id):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_committee")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    entry = get_object_or_404(
        RankingEntry, pk=entry_id, ranking_list__submission_cycle=cycle
    )
    confirmed_on = parse_date(request.POST.get("receipt_confirmed_on") or "") or timezone.localdate()
    try:
        confirm_letter_receipt(entry, confirmed_on)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Καταχωρίστηκε η επιβεβαίωση λήψης ({confirmed_on:%d/%m/%Y})· προθεσμία ένστασης έως {entry.objection_deadline:%d/%m/%Y}.",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_register_objection(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_objections")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    application = get_object_or_404(
        PlotApplication, pk=request.POST.get("application_id"), announcement=cycle
    )
    submitted_on = parse_date(request.POST.get("submitted_on") or "") or timezone.localdate()
    objection_type = request.POST.get("objection_type") or ""
    grounds = request.POST.get("grounds") or ""
    try:
        register_objection(
            application,
            submitted_on=submitted_on,
            objection_type=objection_type,
            grounds=grounds,
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, f"Καταχωρίστηκε η ένσταση για την αίτηση {application.protocol_number}."
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_decide_objection(request, pk, objection_id):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_objections")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    objection = get_object_or_404(
        Objection, pk=objection_id, application__announcement=cycle
    )
    status = request.POST.get("status") or ""
    decision_notes = request.POST.get("decision_notes") or ""
    decided_on = parse_date(request.POST.get("decided_on") or "") or timezone.localdate()
    try:
        decide_objection(
            objection,
            status=status,
            decision_notes=decision_notes,
            decided_on=decided_on,
            user=request.user,
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Καταχωρίστηκε η απόφαση επί της ένστασης ({objection.get_status_display()}) και στάλθηκε ενημερωτικό email.",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_add_pending_requirement(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_objections")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    application = get_object_or_404(
        PlotApplication, pk=request.POST.get("application_id"), announcement=cycle
    )
    description = request.POST.get("description") or ""
    objection_id = request.POST.get("objection_id")
    objection = (
        Objection.objects.filter(pk=objection_id, application=application).first()
        if objection_id
        else None
    )
    try:
        add_pending_requirement(application, description, objection=objection)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Προστέθηκε εκκρεμότητα (pending) στην αίτηση {application.protocol_number}.",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_toggle_pending_requirement(request, pk, requirement_id):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_objections")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    req = get_object_or_404(
        PendingRequirement, pk=requirement_id, application__announcement=cycle
    )
    is_fulfilled = request.POST.get("is_fulfilled") in ("1", "true", "True", "on")
    toggle_pending_requirement(req, is_fulfilled=is_fulfilled)
    messages.success(request, "Ενημερώθηκε η κατάσταση της εκκρεμότητας.")
    next_url = request.POST.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_start_final_list(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_objections")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    accept = request.POST.get("accept_open_period") in ("1", "true", "True", "on")
    try:
        start_final_list(cycle, accept_open_period=accept)
    except ObjectionPeriodOpenError as exc:
        messages.error(
            request, f"{exc} Επιλέξτε «Αποδέχομαι» για να προχωρήσετε πριν από τη λήξη της προθεσμίας."
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        if cycle.objections_closed_early:
            messages.warning(
                request,
                "Η γνωστοποίηση προχώρησε στο Στάδιο 5 (Τελικός Κατάλογος Δικαιούχων) πριν από τη λήξη "
                "της περιόδου ενστάσεων, κατόπιν αποδοχής της προειδοποίησης.",
            )
        else:
            messages.success(
                request, "Η γνωστοποίηση προχώρησε στο Στάδιο 5 (Τελικός Κατάλογος Δικαιούχων)."
            )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_issue_final_list(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_objections")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    decided_on = parse_date(request.POST.get("decided_on") or "")
    try:
        result = issue_final_list_and_notify(
            cycle, user=request.user, decided_on=decided_on
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        ben_cnt = len(result["sent_beneficiaries"])
        run_cnt = len(result["sent_runner_ups"])
        messages.success(
            request,
            f"Εκδόθηκε ο Τελικός Κατάλογος Δικαιούχων ({ben_cnt} email σε δικαιούχους οικοπέδου, {run_cnt} email σε επιλαχόντες).",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_schedule_lottery(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_lottery")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    raw_dt = request.POST.get("lottery_date") or ""
    lottery_dt = parse_datetime(raw_dt) or parse_date(raw_dt) or timezone.now()
    location = request.POST.get("location") or ""
    comments = request.POST.get("comments") or ""
    try:
        schedule_lottery(cycle, lottery_dt, location, comments=comments, user=request.user)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "Προγραμματίστηκε η κλήρωση οικοπέδων και απεστάλησαν οι προσκλήσεις."
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_record_lottery(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_lottery")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    assignments = {}
    for key, value in request.POST.items():
        if key.startswith("plot_for_") and value and str(value).isdigit():
            app_id_str = key[len("plot_for_") :]
            if app_id_str.isdigit():
                assignments[int(app_id_str)] = int(value)
    try:
        record_lottery_result(cycle, assignments)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Καταχωρίστηκε το αποτέλεσμα της κλήρωσης οικοπέδων.")
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_complete_lottery(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_lottery")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    try:
        complete_lottery(cycle)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        if cycle.stage == SubmissionCycle.Stage.CLOSED:
            messages.success(
                request,
                "Η γνωστοποίηση ολοκληρώθηκε· τυχόν αδιάθετα οικόπεδα απελευθερώθηκαν και είναι ξανά διαθέσιμα για νέα γνωστοποίηση.",
            )
        else:
            messages.success(
                request,
                "Η κλήρωση ολοκληρώθηκε· η γνωστοποίηση προχώρησε στο Στάδιο 7 (Υπογραφή Συμφωνίας & Πληρωμή).",
            )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_invite_agreement(request, pk, allocation_id):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_agreements")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    allocation = get_object_or_404(
        Allocation, pk=allocation_id, application__announcement=cycle
    )
    raw_appt = request.POST.get("appointment_at") or ""
    appt_dt = parse_datetime(raw_appt) or parse_date(raw_appt)
    deadline = parse_date(request.POST.get("deadline") or "")
    location = request.POST.get("location")
    try:
        invite_to_agreement(
            allocation,
            appointment_at=appt_dt,
            deadline=deadline,
            location=location,
            user=request.user,
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Απεστάλη πρόσκληση υπογραφής Συμφωνίας και πληρωμής στην αίτηση {allocation.application.protocol_number}.",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_agreement_docx(request, pk, allocation_id):
    if not (
        has_access(request.user, "announcement_agreements", EXPORT)
        or has_access(request.user, "announcements")
    ):
        require_access(request.user, "announcement_agreements", EXPORT)
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    allocation = get_object_or_404(
        Allocation.objects.select_related(
            "application", "application__applicant", "application__spouse", "parcel", "parcel__community"
        ),
        pk=allocation_id,
        application__announcement=cycle,
    )
    doc_stream = render_agreement_docx(allocation)
    plot_label = allocation.parcel.number or str(allocation.parcel.pk)
    filename = f"Συμφωνία_{allocation.application.protocol_number}_{plot_label}.docx"
    return FileResponse(doc_stream, as_attachment=True, filename=filename)


@login_required
def announcement_record_signature_payment(request, pk, allocation_id):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_agreements")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    allocation = get_object_or_404(
        Allocation, pk=allocation_id, application__announcement=cycle
    )
    signed = request.POST.get("signed") in ("1", "true", "True", "on")
    paid = request.POST.get("paid") in ("1", "true", "True", "on")
    signed_on = parse_date(request.POST.get("signed_on") or "")
    paid_on = parse_date(request.POST.get("paid_on") or "")
    raw_amount = (request.POST.get("amount") or "").strip()
    amount = None
    if raw_amount:
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            amount = None
    comments = request.POST.get("comments") or ""
    record_signature_and_payment(
        allocation,
        signed=signed,
        signed_on=signed_on,
        paid=paid,
        paid_on=paid_on,
        amount=amount,
        comments=comments,
    )
    messages.success(
        request,
        f"Ενημερώθηκε η κατάσταση υπογραφής/πληρωμής για την αίτηση {allocation.application.protocol_number}.",
    )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_forfeit_allocation(request, pk, allocation_id):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_agreements")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    allocation = get_object_or_404(
        Allocation, pk=allocation_id, application__announcement=cycle
    )
    reason = request.POST.get("reason") or ""
    agreement_status = request.POST.get("agreement_status") or Agreement.Status.NOT_SIGNED
    payment_status = request.POST.get("payment_status") or Payment.Status.UNPAID
    try:
        result = forfeit_allocation(
            allocation,
            reason=reason,
            agreement_status=agreement_status,
            payment_status=payment_status,
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        proposed = result["proposed_runner_up"]
        extra = (
            f" Προτεινόμενος επιλαχών: {proposed.protocol_number}."
            if proposed
            else " Δεν υπάρχουν διαθέσιμοι επιλαχόντες."
        )
        messages.success(
            request,
            f"Η αίτηση {allocation.application.protocol_number} απορρίφθηκε λόγω μη προσέλευσης/υπογραφής/πληρωμής.{extra}",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_promote_runner_up(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    _require_stage_edit(request, "announcement_agreements")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    plot = get_object_or_404(Plot, pk=request.POST.get("plot_id"), submission_cycles=cycle)
    runner_up = get_object_or_404(
        PlotApplication, pk=request.POST.get("application_id"), announcement=cycle
    )
    justification = request.POST.get("justification") or ""
    try:
        promote_runner_up(
            cycle,
            plot,
            runner_up,
            justification=justification,
            user=request.user,
        )
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Το οικόπεδο {plot.number or plot.row_label} ανατέθηκε στον επιλαχόντα ({runner_up.protocol_number}) και στάλθηκε πρόσκληση.",
        )
    return redirect("announcements:detail", pk=cycle.pk)


@login_required
def announcement_complete_agreements(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    if cycle.stage == SubmissionCycle.Stage.SUBMISSION:
        _require_stage_edit(request, "announcement_committee")
    elif cycle.stage == SubmissionCycle.Stage.LOTTERY:
        _require_stage_edit(request, "announcement_lottery")
    else:
        _require_stage_edit(request, "announcement_agreements")
    accept = request.POST.get("accept_open_submission") in ("1", "true", "True", "on")
    try:
        complete_agreements(
            cycle,
            accept_open_submission=accept,
            today=timezone.localdate(),
        )
    except SubmissionPeriodOpenError as exc:
        messages.error(
            request, f"{exc} Επιλέξτε «Αποδέχομαι» για να ολοκληρώσετε τη γνωστοποίηση πριν από τη λήξη της προθεσμίας."
        )
        return _redirect_stage(cycle, SubmissionCycle.Stage.SUBMISSION)
    except BeneficiaryListError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Η γνωστοποίηση ολοκληρώθηκε· τυχόν αδιάθετα οικόπεδα απελευθερώθηκαν και είναι ξανά διαθέσιμα για νέα γνωστοποίηση.",
        )
    return redirect("announcements:detail", pk=cycle.pk)


# --- 9.2 Publication methods: one row per method, add / edit / delete in a modal ----------------


def publication_rows(cycle):
    """The 9.2 table: the four fixed methods (recorded or still open), then the «Άλλο» rows."""
    recorded = {p.method: p for p in cycle.publications.all() if p.is_fixed}
    return {
        "fixed_rows": [
            {"method": method, "label": method.label, "publication": recorded.get(method)}
            for method in SubmissionCyclePublication.FIXED_METHODS
        ],
        "other_rows": cycle.publications.filter(method=SubmissionCyclePublication.PublicationMethod.OTHER),
    }


class PublicationGrid(GridEndpoint):
    """9.2 grid of an announcement; `case` in the GridEndpoint hooks is the SubmissionCycle."""

    model = SubmissionCyclePublication
    form_class = SubmissionCyclePublicationForm
    section_ref = "9.2"
    grid_template = "plots/_publication_grid.html"
    form_template = "plots/_publication_form.html"
    form_context_name = "publication_form"
    noun_saved = "ο τρόπος δημοσίευσης"
    noun_deleted = "ο τρόπος δημοσίευσης"

    def get_case(self, request, pk, kind):
        # «Γνωστοποιήσεις» has no separate create / delete access: rows change with «Τροποποίηση».
        require_access(request.user, "announcements", EDIT)
        return get_object_or_404(SubmissionCycle, pk=pk)

    def queryset(self, cycle):
        # Only the «Άλλο» rows are edited in the modal; the fixed methods are dated inline.
        return SubmissionCyclePublication.objects.filter(
            submission_cycle=cycle, method=SubmissionCyclePublication.PublicationMethod.OTHER
        )

    def new_instance(self, cycle):
        return SubmissionCyclePublication(
            submission_cycle=cycle, method=SubmissionCyclePublication.PublicationMethod.OTHER
        )

    def grid_context(self, request, cycle):
        return publication_rows(cycle)

    def grid_html(self, request, cycle):
        return render_to_string(
            self.grid_template, {"cycle": cycle, **self.grid_context(request, cycle)}, request=request
        )

    def form_html(self, request, cycle, form):
        return render_to_string(
            self.form_template, {"cycle": cycle, self.form_context_name: form}, request=request
        )


PUBLICATIONS = PublicationGrid()


def _publication_endpoint(handler):
    @login_required
    def view(request, pk, publication_id=None):
        return handler(request, pk, publication_id)

    return view


def _publication_date(request, pk, method):
    """9.2 Inline date of one of the four fixed methods; an empty date removes the row."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    require_access(request.user, "announcements", EDIT)
    if method not in SubmissionCyclePublication.FIXED_METHODS:
        raise Http404("Άγνωστος τρόπος δημοσίευσης.")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    form = PublicationDateForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "message": "Μη έγκυρη ημερομηνία δημοσίευσης."}, status=400)
    published_on = form.cleaned_data["published_on"]
    label = SubmissionCyclePublication.PublicationMethod(method).label
    with transaction.atomic():
        rows = SubmissionCyclePublication.objects.filter(submission_cycle=cycle, method=method)
        row = rows.first()
        if published_on is None:
            if row is not None:
                row._section_ref = PUBLICATIONS.section_ref
                row.delete()
            message = f"Αφαιρέθηκε η ημερομηνία: {label}."
        elif row is None:
            row = SubmissionCyclePublication(submission_cycle=cycle, method=method, published_on=published_on)
            row._section_ref = PUBLICATIONS.section_ref
            row.save()
            message = f"Καταχωρίστηκε η ημερομηνία: {label} — {published_on}."
        else:
            row.published_on = published_on
            row._section_ref = PUBLICATIONS.section_ref
            row.save()
            message = f"Ενημερώθηκε η ημερομηνία: {label} — {published_on}."
    return JsonResponse({"ok": True, "message": message, "grid_html": PUBLICATIONS.grid_html(request, cycle)})


publication_date = login_required(_publication_date)
publication_form = _publication_endpoint(PUBLICATIONS.form_view)
publication_delete = _publication_endpoint(PUBLICATIONS.delete_view)
