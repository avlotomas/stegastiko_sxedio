from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from allocation.models import Agreement, Allocation, Payment, RankingList
from cases.forms import UtilityServiceTypeFormSet
from cases.models import (
    Case,
    InfrastructureCheck,
    MinistryDecisionRound,
    SubmissionCycle,
    UtilityServiceType,
    YesNo,
)
from core.audit import record_user_changes, user_audit_snapshot
from core.forms import AppPasswordChangeForm
from core.function_catalog import EDIT
from core.models import set_must_change_password, user_must_change_password
from core.permissions import access_required, has_access
from core.reminders import (
    CONSULTATION_DUE_REMINDER_TYPE,
    consultation_due_reminders,
    mark_reminder_read,
)
from core.settings_navigation import settings_nav
from plot_applications.models import ApplicationStage, Objection, PendingRequirement, PlotApplication
from plots.models import Plot

PERMISSION_DENIED_MESSAGE = "Δεν έχετε πρόσβαση σε αυτή τη λειτουργία."


def permission_denied(request, exception=None):
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(
            {"ok": False, "message": PERMISSION_DENIED_MESSAGE, "errors": [PERMISSION_DENIED_MESSAGE]},
            status=403,
        )
    return render(request, "403.html", {"message": PERMISSION_DENIED_MESSAGE}, status=403)


class AppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        if user_must_change_password(self.request.user):
            return redirect("account").url
        return super().get_success_url()


class AppLogoutView(LogoutView):
    next_page = "login"
    http_method_names = ["post", "options"]


@login_required
def home(request):
    reminders = []
    if has_access(request.user, "reminders"):
        reminders = consultation_due_reminders(request.user, include_read=False)
    can_view_announcements = has_access(request.user, "announcements")
    can_view_cases = has_access(request.user, "cases")
    can_view_plots = has_access(request.user, "plots") or can_view_announcements or can_view_cases
    deadlines = submission_deadlines() if can_view_announcements else []
    ann_data = _announcements_dashboard_data() if (can_view_announcements or can_view_plots) else {}
    cases_data = _cases_dashboard_data() if can_view_cases else {}
    return render(
        request,
        "core/home.html",
        {
            "dashboard_reminders": reminders[:5],
            "dashboard_reminders_total": len(reminders),
            "submission_deadlines": deadlines,
            "submission_deadline_alerts": [row for row in deadlines if row["warning"] or row["expired"]],
            **ann_data,
            **cases_data,
        },
    )


def _announcements_dashboard_data() -> dict:
    """Συγκεντρωτικά στοιχεία (KPIs), εκκρεμότητες και πίνακας προόδου Γνωστοποιήσεων & Παραχωρήσεων Οικοπέδων."""
    cycles = list(
        SubmissionCycle.objects.prefetch_related(
            "plots__community",
            "applications__applicant",
            "applications__objections",
            "applications__pending_requirements",
            "ranking_lists",
        ).order_by("-announcement_date", "-id")
    )
    active_allocations = list(
        Allocation.objects.filter(status=Allocation.Status.ACTIVE)
        .select_related("application", "application__applicant", "parcel", "agreement", "payment")
        .order_by("id")
    )
    allocs_by_cycle: dict[int, list[Allocation]] = {}
    signed_paid_total = 0
    pending_agreements = []
    for alloc in active_allocations:
        cid = alloc.application.announcement_id
        allocs_by_cycle.setdefault(cid, []).append(alloc)
        agr = getattr(alloc, "agreement", None)
        pay = getattr(alloc, "payment", None)
        is_signed = agr is not None and agr.status == Agreement.Status.SIGNED
        is_paid = pay is not None and pay.status == Payment.Status.PAID
        if is_signed and is_paid:
            signed_paid_total += 1
        else:
            pending_agreements.append(alloc)

    stage_labels = [
        (SubmissionCycle.Stage.DETAILS, "1. Στοιχεία γνωστοποίησης"),
        (SubmissionCycle.Stage.SUBMISSION, "2. Υποβολή αιτήσεων"),
        (SubmissionCycle.Stage.APPLICATIONS_COMMITTEE, "3. Επιτροπή Εξέτασης Αιτήσεων"),
        (SubmissionCycle.Stage.OBJECTIONS_COMMITTEE, "4. Ενστάσεις"),
        (SubmissionCycle.Stage.FINAL_LIST, "5. Τελικός Κατάλογος Δικαιούχων"),
        (SubmissionCycle.Stage.LOTTERY, "6. Στάδιο κλήρωσης"),
        (SubmissionCycle.Stage.AGREEMENTS, "7. Υπογραφή συμφωνίας & πληρωμή"),
        (SubmissionCycle.Stage.CLOSED, "Ολοκληρωμένες"),
    ]
    stage_counts_map = {code: 0 for code, _ in stage_labels}

    announcement_rows = []
    workflow_action_items = []
    total_apps = 0
    total_beneficiaries = 0
    offered_plot_ids: set[int] = set()

    for cycle in cycles:
        stage_counts_map[cycle.stage] = stage_counts_map.get(cycle.stage, 0) + 1
        plots = list(cycle.plots.all())
        if cycle.is_active:
            offered_plot_ids.update(p.pk for p in plots)
        apps = list(cycle.applications.all())
        total_apps += len(apps)
        blockers_cnt = sum(
            1
            for a in apps
            if a.application_stage in (ApplicationStage.COLLECTION, ApplicationStage.EXAMINATION)
        )
        beneficiaries_cnt = sum(1 for a in apps if a.is_beneficiary)
        total_beneficiaries += beneficiaries_cnt

        objections = [obj for a in apps for obj in a.objections.all()]
        undecided_obj_cnt = sum(1 for o in objections if o.status == Objection.Status.PENDING)
        pending_reqs_cnt = sum(
            1 for a in apps for req in a.pending_requirements.all() if not req.is_fulfilled
        )

        rlists = {rl.list_type: rl for rl in cycle.ranking_lists.all()}
        prelim = rlists.get(RankingList.ListType.PRELIMINARY)
        final = rlists.get(RankingList.ListType.FINAL)

        cycle_allocs = allocs_by_cycle.get(cycle.pk, [])
        cycle_signed_paid = sum(
            1
            for al in cycle_allocs
            if getattr(al, "agreement", None) is not None
            and al.agreement.status == Agreement.Status.SIGNED
            and getattr(al, "payment", None) is not None
            and al.payment.status == Payment.Status.PAID
        )

        stage_link_code = (
            SubmissionCycle.Stage.AGREEMENTS
            if cycle.stage == SubmissionCycle.Stage.CLOSED
            else cycle.stage
        )

        if cycle.stage == SubmissionCycle.Stage.DETAILS:
            next_action = "Οριστικοποίηση & έκδοση (9.3)"
        elif cycle.stage == SubmissionCycle.Stage.SUBMISSION:
            if blockers_cnt:
                next_action = f"Έλεγχος πληρότητας ({blockers_cnt} εκκρεμείς)"
            elif apps:
                next_action = "Έτοιμη για Επιτροπή Εξέτασης (Στάδιο 3)"
            else:
                next_action = "Καταχώριση αιτήσεων"
        elif cycle.stage == SubmissionCycle.Stage.APPLICATIONS_COMMITTEE:
            next_action = "Έκδοση Προκαταρκτικού & Αποστολή Email"
        elif cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE:
            if undecided_obj_cnt or pending_reqs_cnt:
                next_action = f"Εξέταση ενστάσεων ({undecided_obj_cnt} εκκρεμείς, {pending_reqs_cnt} pending)"
            else:
                next_action = "Μετάβαση στον Τελικό Κατάλογο (Στάδιο 5)"
        elif cycle.stage == SubmissionCycle.Stage.FINAL_LIST:
            next_action = "Έκδοση Τελικού Καταλόγου & Αποστολή Email"
        elif cycle.stage == SubmissionCycle.Stage.LOTTERY:
            next_action = "Κλήρωση οικοπέδων & καταχώριση αποτελέσματος"
        elif cycle.stage == SubmissionCycle.Stage.AGREEMENTS:
            next_action = f"Υπογραφές & πληρωμές ({cycle_signed_paid}/{len(cycle_allocs)})"
        else:
            next_action = "Ολοκληρώθηκε"

        if cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE and (
            undecided_obj_cnt or pending_reqs_cnt or (prelim and prelim.objection_deadline)
        ):
            workflow_action_items.append(
                {
                    "cycle": cycle,
                    "stage_code": "objections_committee",
                    "stage_label": "4. Ενστάσεις (Ενότ. 7)",
                    "summary": (
                        f"{len(objections)} ενστάσεις ({undecided_obj_cnt} εκκρεμείς)"
                        + (f" · {pending_reqs_cnt} εκκρεμότητες PENDING" if pending_reqs_cnt else "")
                    ),
                    "deadline": prelim.objection_deadline if prelim else None,
                    "badge": "fail" if (undecided_obj_cnt or pending_reqs_cnt) else "pending",
                }
            )
        elif cycle.stage == SubmissionCycle.Stage.SUBMISSION and blockers_cnt:
            workflow_action_items.append(
                {
                    "cycle": cycle,
                    "stage_code": "submission",
                    "stage_label": "2. Υποβολή αιτήσεων (Ενότ. 5)",
                    "summary": f"Εκκρεμεί έλεγχος πληρότητας σε {blockers_cnt} από {len(apps)} αιτήσεις",
                    "deadline": cycle.submission_end_date,
                    "badge": "pending",
                }
            )
        elif cycle.stage in (
            SubmissionCycle.Stage.APPLICATIONS_COMMITTEE,
            SubmissionCycle.Stage.FINAL_LIST,
            SubmissionCycle.Stage.LOTTERY,
        ):
            workflow_action_items.append(
                {
                    "cycle": cycle,
                    "stage_code": stage_link_code,
                    "stage_label": cycle.get_stage_display(),
                    "summary": next_action,
                    "deadline": None,
                    "badge": "pending",
                }
            )

        announcement_rows.append(
            {
                "cycle": cycle,
                "stage_link_code": stage_link_code,
                "plots_count": len(plots),
                "allocated_count": len(cycle_allocs),
                "signed_paid_count": cycle_signed_paid,
                "applications_total": len(apps),
                "blockers_count": blockers_cnt,
                "beneficiaries_count": beneficiaries_cnt,
                "objections_total": len(objections),
                "undecided_objections_count": undecided_obj_cnt,
                "pending_reqs_count": pending_reqs_cnt,
                "preliminary": prelim,
                "final": final,
                "next_action": next_action,
            }
        )

    total_plots = Plot.objects.count()
    available_plots = Plot.objects.available().count()
    active_announcements = sum(
        1 for c in cycles if c.is_published and c.stage != SubmissionCycle.Stage.CLOSED
    )
    draft_announcements = sum(1 for c in cycles if not c.is_published)
    closed_announcements = sum(1 for c in cycles if c.stage == SubmissionCycle.Stage.CLOSED)

    return {
        "kpi_plots": {
            "total": total_plots,
            "available": available_plots,
            "offered": len(offered_plot_ids),
            "allocated": len(active_allocations),
        },
        "kpi_announcements": {
            "total": len(cycles),
            "active": active_announcements,
            "draft": draft_announcements,
            "closed": closed_announcements,
        },
        "kpi_allocations": {
            "total_applications": total_apps,
            "beneficiaries": total_beneficiaries,
            "active_allocations": len(active_allocations),
            "signed_paid": signed_paid_total,
        },
        "announcement_stage_counts": [
            {"code": code, "label": label, "count": stage_counts_map.get(code, 0)}
            for code, label in stage_labels
        ],
        "announcement_rows": announcement_rows,
        "workflow_action_items": workflow_action_items,
        "pending_agreements": pending_agreements,
    }


def _cases_dashboard_data() -> dict:
    """Συγκεντρωτικά στοιχεία (KPIs) και πίνακας προόδου Αιτήσεων Διαχωρισμού (Κ.Σ. / Δ.Δ., Ενότητες 1–7)."""
    cases = list(
        Case.objects.with_list_data()
        .prefetch_related("infrastructure_checks")
        .order_by("-start_date", "-id")
    )
    phase_counts = {
        "completeness": 0,
        "evaluation": 0,
        "works": 0,
        "ready_for_notice": 0,
        "completed": 0,
        "rejected": 0,
    }
    approved_count = 0
    rejected_count = 0
    completed_count = 0
    active_count = 0
    case_rows = []

    for c in cases:
        decision = getattr(c, "list_ministry_decision", "") or ""
        comp_res = c.completeness_result
        infra = c.latest_infrastructure_check
        infra_ready = bool(infra and infra.is_ready_for_submission_cycle)

        if decision == MinistryDecisionRound.MinistryDecision.APPROVED:
            approved_count += 1
        elif decision == MinistryDecisionRound.MinistryDecision.REJECTED:
            rejected_count += 1

        if c.is_completed:
            completed_count += 1
            phase_counts["completed"] += 1
            phase_label = "Ολοκληρώθηκε (Οικόπεδα)"
            phase_badge = "pass"
        elif decision == MinistryDecisionRound.MinistryDecision.REJECTED:
            phase_counts["rejected"] += 1
            phase_label = "Απορρίφθηκε από ΥΠΕΣ (Ενότ. 6)"
            phase_badge = "fail"
        else:
            active_count += 1
            if not c.is_new_division:
                phase_counts["works"] += 1
                phase_label = "7. Καταχώριση αδιάθετων οικοπέδων"
                phase_badge = "pending"
            elif comp_res != YesNo.YES:
                phase_counts["completeness"] += 1
                phase_label = "1–2. Έλεγχος πληρότητας Κ.Σ."
                phase_badge = "fail" if comp_res == YesNo.NO else "pending"
            elif decision != MinistryDecisionRound.MinistryDecision.APPROVED:
                phase_counts["evaluation"] += 1
                phase_label = "3–6. Τεχνική αξιολόγηση & Απόφαση ΥΠΕΣ"
                phase_badge = "pending"
            else:
                phase_counts["works"] += 1
                if infra_ready:
                    phase_counts["ready_for_notice"] += 1
                    phase_label = "7. Υποδομές έτοιμες για προκήρυξη (Ενότ. 4)"
                    phase_badge = "pass"
                else:
                    phase_label = "7. Σχεδιασμός & Κατασκευαστικές εργασίες"
                    phase_badge = "pending"

        if infra_ready:
            infra_label = "Έτοιμο (ρείθρα + κράσπεδα + άσφαλτος)"
            infra_badge = "pass"
        elif infra and infra.stage:
            infra_label = infra.stage
            infra_badge = "pending"
        elif not c.is_new_division:
            infra_label = "Αδιάθετα οικόπεδα"
            infra_badge = "pass"
        else:
            infra_label = "—"
            infra_badge = "pending"

        case_rows.append(
            {
                "case": c,
                "phase_label": phase_label,
                "phase_badge": phase_badge,
                "infra_label": infra_label,
                "infra_badge": infra_badge,
                "infra_ready": infra_ready,
            }
        )

    return {
        "kpi_cases": {
            "total": len(cases),
            "active": active_count,
            "completed": completed_count,
            "approved": approved_count,
            "rejected": rejected_count,
            "ready_for_notice": phase_counts["ready_for_notice"],
        },
        "case_phase_counts": [
            ("1–2. Έλεγχος πληρότητας", phase_counts["completeness"], "pending"),
            ("3–6. Τεχνική αξιολόγηση & ΥΠΕΣ", phase_counts["evaluation"], "pending"),
            ("7. Σχεδιασμός & Έργα", phase_counts["works"], "pending"),
            ("Έτοιμες για προκήρυξη (Ενότ. 4)", phase_counts["ready_for_notice"], "pass"),
            ("Ολοκληρωμένες", phase_counts["completed"], "pass"),
            ("Απορριφθείσες ΥΠΕΣ", phase_counts["rejected"], "fail"),
        ],
        "case_rows": case_rows,
    }


def submission_deadlines(today=None):
    """Ενότ. 4, 5: προθεσμίες υποβολής αιτήσεων των γνωστοποιήσεων που βρίσκονται στο Στάδιο 2."""
    from plot_applications.rules import parameter

    warning_days = parameter("plotApp.submissionDeadlineWarningDays")
    cycles = (
        SubmissionCycle.objects.filter(
            published_at__isnull=False,
            stage=SubmissionCycle.Stage.SUBMISSION,
            submission_closed_early=False,
        )
        .prefetch_related("plots__community")
        .order_by("submission_end_date", "pk")
    )
    rows = []
    for cycle in cycles:
        days = cycle.submission_days_remaining(today)
        rows.append(
            {
                "cycle": cycle,
                "days_remaining": days,
                "expired": days is not None and days < 0,
                "warning": days is not None and 0 <= days <= warning_days,
            }
        )
    return rows


@login_required
def account(request):
    must_change = user_must_change_password(request.user)
    if request.method == "POST":
        previous = user_audit_snapshot(request.user)
        form = AppPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                set_must_change_password(user, False)
                record_user_changes(user, previous, password_changed=True)
            update_session_auth_hash(request, user)
            messages.success(request, "Ο κωδικός πρόσβασης ενημερώθηκε.")
            return redirect("home" if must_change else "account")
    else:
        form = AppPasswordChangeForm(request.user)
    return render(
        request,
        "core/account.html",
        {"form": form, "must_change_password": must_change},
    )


@access_required("reminders")
def reminders(request):
    return render(
        request,
        "core/reminders.html",
        {"reminders": consultation_due_reminders(request.user, include_read=True)},
    )


@access_required("reminders")
def reminder_mark_read(request):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    reminder_key = (request.POST.get("reminder_key") or "").strip()
    reminder_type = (request.POST.get("reminder_type") or "").strip()
    if not reminder_key or reminder_type != CONSULTATION_DUE_REMINDER_TYPE:
        raise Http404("Μη έγκυρη υπενθύμιση.")
    active_reminders = consultation_due_reminders(request.user, include_read=True)
    if not any(item.key == reminder_key for item in active_reminders):
        raise Http404("Η υπενθύμιση δεν είναι διαθέσιμη.")
    mark_reminder_read(request.user, reminder_key, reminder_type)
    messages.success(request, "Η υπενθύμιση σημειώθηκε ως διαβασμένη.")
    next_url = request.POST.get("next") or "home"
    return redirect(next_url)


@access_required("settings_catalogs", post_action=EDIT)
def utility_service_types(request):
    """4.2 Values of the «Υπηρεσία» dropdown: rename, add, order, deactivate."""
    queryset = UtilityServiceType.objects.all()
    if request.method == "POST":
        formset = UtilityServiceTypeFormSet(request.POST, queryset=queryset, prefix="service_types")
        if formset.is_valid():
            with transaction.atomic():
                formset.save()
            messages.success(request, "Ο κατάλογος υπηρεσιών αποθηκεύτηκε.")
            return redirect("utility_service_types")
    else:
        formset = UtilityServiceTypeFormSet(queryset=queryset, prefix="service_types")
    can_edit = has_access(request.user, "settings_catalogs", EDIT)
    if not can_edit:
        for form in formset:
            for field in form.fields.values():
                field.disabled = True
    return render(
        request,
        "core/utility_service_types.html",
        {
            "formset": formset,
            "settings_nav": settings_nav(request.user, "catalogs"),
            "can_edit": can_edit,
        },
    )
