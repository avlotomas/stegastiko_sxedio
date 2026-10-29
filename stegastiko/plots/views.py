"""«Οικόπεδα»: list, manual entry, edit and delete of completed plots."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from cases.models import Case
from cases.views.common import disable_fields
from core.function_catalog import CREATE, DELETE, EDIT
from core.models import Community
from core.permissions import access_required, has_access
from plots.forms import PlotForm
from plots.models import Plot

PLOT_LIST_PAGE_SIZE = 50
ORIGIN_CASE = "case"
ORIGIN_MANUAL = "manual"
AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_UNAVAILABLE = "unavailable"


@access_required("plots")
def plot_list(request):
    plots = Plot.objects.select_related("community", "source_case").prefetch_related(
        "allocations", "submission_cycles"
    )
    community_id = request.GET.get("community_id") or ""
    source_case = request.GET.get("source_case") or ""
    origin = request.GET.get("origin") or ""
    availability = request.GET.get("availability") or ""
    q = (request.GET.get("q") or "").strip()
    if community_id:
        plots = plots.filter(community_id=community_id)
    if source_case:
        plots = plots.filter(source_case_id=source_case)
    if origin == ORIGIN_CASE:
        plots = plots.filter(source_case__isnull=False)
    elif origin == ORIGIN_MANUAL:
        plots = plots.filter(source_case__isnull=True)
    if availability == AVAILABILITY_AVAILABLE:
        plots = plots.available()
    elif availability == AVAILABILITY_UNAVAILABLE:
        plots = plots.exclude(pk__in=Plot.objects.available().values("pk"))
    if q:
        plots = plots.filter(
            Q(design_number__icontains=q)
            | Q(tkx_number__icontains=q)
            | Q(title_deed_number__icontains=q)
            | Q(parcel_number__icontains=q)
            | Q(source_case__case_number__icontains=q)
        )
    page = Paginator(plots, PLOT_LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    filter_query = request.GET.copy()
    filter_query.pop("page", None)
    return render(
        request,
        "plots/list.html",
        {
            "plots": page.object_list,
            "page_obj": page,
            "filter_query": filter_query.urlencode(),
            "communities": Community.objects.filter(is_active=True).order_by("name"),
            "community_id": community_id,
            "source_case": source_case,
            "source_case_obj": Case.objects.filter(pk=source_case).first()
            if source_case.isdigit()
            else None,
            "origin": origin,
            "origins": ((ORIGIN_CASE, "Από αίτηση διαχωρισμού"), (ORIGIN_MANUAL, "Χειροκίνητη καταχώριση")),
            "availability": availability,
            "availabilities": (
                (AVAILABILITY_AVAILABLE, "Διαθέσιμα για γνωστοποίηση"),
                (AVAILABILITY_UNAVAILABLE, "Μη διαθέσιμα για γνωστοποίηση"),
            ),
            "q": q,
        },
    )


@access_required("plots", CREATE)
def plot_create(request):
    if request.method == "POST":
        form = PlotForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                plot = form.save()
            messages.success(request, f"Καταχωρίστηκε το {plot.row_label}.")
            return redirect("plots:detail", pk=plot.pk)
    else:
        form = PlotForm(initial={"community": request.GET.get("community_id") or None})
    return render(request, "plots/form.html", {"form": form, "is_create": True})


@access_required("plots", post_action=EDIT)
def plot_detail(request, pk):
    plot = get_object_or_404(
        Plot.objects.select_related(
            "community", "source_case", "source_design_plot", "field", "valuation_referral"
        ).prefetch_related("allocations", "submission_cycles"),
        pk=pk,
    )
    can_edit = has_access(request.user, "plots", EDIT)
    if request.method == "POST":
        form = PlotForm(request.POST, instance=plot)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, f"Οι αλλαγές στο {plot.row_label} αποθηκεύτηκαν.")
            return redirect("plots:detail", pk=plot.pk)
    else:
        form = PlotForm(instance=plot)
    if not can_edit:
        disable_fields(form)
    return render(
        request,
        "plots/form.html",
        {
            "form": form,
            "plot": plot,
            "is_create": False,
            "can_edit": can_edit,
            "can_delete": has_access(request.user, "plots", DELETE),
            "submission_cycles": plot.submission_cycles.prefetch_related("plots__community"),
            "allocations": plot.allocations.select_related("application"),
        },
    )


def delete_refusal(plot):
    if plot.is_allocated:
        return "Το οικόπεδο δεν διαγράφεται γιατί έχει κατανομή."
    if plot.submission_cycles.filter(published_at__isnull=False).exists():
        return "Το οικόπεδο δεν διαγράφεται γιατί περιλαμβάνεται σε εκδοθείσα γνωστοποίηση."
    return ""


@access_required("plots", DELETE)
def plot_delete(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    plot = get_object_or_404(Plot, pk=pk)
    refusal = delete_refusal(plot)
    if refusal:
        messages.error(request, refusal)
        return redirect("plots:detail", pk=plot.pk)
    label = plot.row_label
    with transaction.atomic():
        plot.submission_cycles.clear()
        plot.delete()
    messages.success(request, f"Διαγράφηκε το {label}.")
    return redirect("plots:list")
