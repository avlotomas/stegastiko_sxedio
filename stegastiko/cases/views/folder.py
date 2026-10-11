"""Case list, creation, read-only folder view and aggregate history."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from cases import section_refs as refs
from cases.forms import CaseCreateForm
from cases.models import ApprovedDesignPlot, Case, Consultation
from cases.services import (
    announcement_readiness,
    case_communications,
    create_case,
    section8_completion,
    suitability_summary,
)
from cases.services import case_history as case_history_entries
from cases.views.common import case_nav_items
from cases.views.grids import case_utility_services, consultation_grid
from core.function_catalog import CREATE
from core.models import Community
from core.permissions import access_required

CASE_LIST_PAGE_SIZE = 50


@access_required("cases")
def case_list(request):
    cases = Case.objects.with_list_data()
    communities = Community.objects.filter(is_active=True).order_by("name")
    community_id = request.GET.get("community_id") or ""
    case_type = request.GET.get("case_type") or ""
    q = (request.GET.get("q") or "").strip()
    if community_id:
        cases = cases.filter(community_id=community_id)
    if case_type:
        cases = cases.filter(case_type=case_type)
    if q:
        cases = cases.filter(case_number__icontains=q)
    page = Paginator(cases, CASE_LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    # Filters stay in the pagination links.
    filter_query = request.GET.copy()
    filter_query.pop("page", None)
    return render(
        request,
        "cases/list.html",
        {
            "cases": page.object_list,
            "page_obj": page,
            "filter_query": filter_query.urlencode(),
            "communities": communities,
            "community_id": community_id,
            "case_type": case_type,
            "case_types": Case.CaseType.choices,
            "q": q,
        },
    )


@access_required("cases", CREATE)
def case_create(request):
    if request.method == "POST":
        form = CaseCreateForm(request.POST)
        if form.is_valid():
            try:
                case = create_case(form.save(commit=False))
            except ValidationError as exc:
                form.add_error(None, exc.messages[0] if exc.messages else str(exc))
            else:
                messages.success(request, f"Δημιουργήθηκε η υπόθεση {case.case_number}.")
                return redirect("cases:detail", pk=case.pk)
    else:
        form = CaseCreateForm()
    communities = Community.objects.filter(is_active=True)
    community_emails = {str(community.pk): community.contact_email for community in communities}
    community_districts = {str(community.pk): community.district for community in communities}
    return render(
        request,
        "cases/create.html",
        {
            "form": form,
            "community_emails": community_emails,
            "community_districts": community_districts,
        },
    )


@access_required("cases")
def case_detail(request, pk):
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    return render(
        request,
        "cases/detail.html",
        {
            "case": case,
            "case_nav": case_nav_items(case, request.user),
            "suitability_summary": suitability_summary(case) if case.is_new_division else None,
            "completeness_checks": case.completeness_checks.all(),
            "land_plots": case.land_plots.prefetch_related("attachments"),
            "utility_services": case_utility_services(case),
            "technical_attachments": case.attachments.filter(
                section_ref=refs.REF_TECHNICAL_FILES
            ),
            "division_design_attachments": case.division_design_attachments(),
            "tpo_application_attachments": case.tpo_application_attachments(),
            "dls_application_attachments": case.dls_application_attachments(),
            "approved_design_plots": case.approved_design_plots.all(),
            "suitability_consultation_grid": consultation_grid(
                request.user, case, Consultation.Stage.SUITABILITY
            ),
            "division_consultation_grid": consultation_grid(
                request.user, case, Consultation.Stage.DIVISION
            ),
            "infrastructure_checks": case.infrastructure_checks.all(),
            "parcels": case.approved_design_plots.filter(
                plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT
            ).select_related("field", "valuation_referral", "owner"),
            "completion": section8_completion(case),
            "readiness": announcement_readiness(case),
            "communications": case_communications(case),
            "submission_cycles": case.submission_cycles.all(),
            "ministry_decision_rounds": case.ministry_decision_rounds.prefetch_related(
                "attachments"
            ),
        },
    )


@access_required("case_history")
def case_history(request, pk):
    case = get_object_or_404(Case, pk=pk)
    return render(
        request,
        "cases/history.html",
        {
            "case": case,
            "history_entries": case_history_entries(case),
            "case_nav": case_nav_items(case, request.user),
        },
    )
