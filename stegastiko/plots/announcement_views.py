"""Ενότητα 9 — Γνωστοποιήσεις: a flow of its own over the completed plots of a community."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from cases.models import SubmissionCycle, SubmissionCyclePublication
from cases.views.common import disable_fields
from cases.views.grid import GridEndpoint
from core.function_catalog import CREATE, EDIT, PUBLISH
from core.models import Community
from core.permissions import access_required, has_access, require_access
from plots.forms import (
    AnnouncementCommunitiesForm,
    PublicationDateForm,
    SubmissionCycleForm,
    SubmissionCyclePublicationForm,
)
from plots.models import Plot
from plots.notice_export import NoticeExportError, notice_filename, render_notice
from plots.services import create_announcement, publish_announcement

PUBLISHED_MESSAGE = "Η ανακοίνωση έχει οριστικοποιηθεί και δεν αλλάζει."


def _first_error(exc: ValidationError) -> str:
    return exc.messages[0] if exc.messages else str(exc)


@access_required("announcements")
def announcement_list(request):
    cycles = SubmissionCycle.objects.prefetch_related("communities", "plots")
    community_id = request.GET.get("community_id") or ""
    if community_id:
        cycles = cycles.filter(communities=community_id)
    return render(
        request,
        "plots/announcement_list.html",
        {
            "cycles": cycles,
            "communities": Community.objects.filter(is_active=True).order_by("name"),
            "community_id": community_id,
        },
    )


def _community_choices():
    """Step 1 of the wizard: active communities by district, with their available plots."""
    available = dict(
        Plot.objects.available()
        .order_by()
        .values_list("community")
        .annotate(count=Count("pk", distinct=True))
    )
    districts = {}
    for community in Community.objects.filter(is_active=True).order_by("district", "name"):
        districts.setdefault(community.district, []).append(
            {"community": community, "available": available.get(community.pk, 0)}
        )
    return list(districts.items())


@access_required("announcements", CREATE)
def announcement_create(request):
    """9.1 New announcement, as a two-step wizard.

    Step 1 chooses the communities (several per announcement, all of one district); step 2
    offers only the available plots of those communities and takes the submission period.
    """
    data = request.POST if request.method == "POST" else request.GET
    selection = None
    if request.method == "POST" or "next" in request.GET:
        selection = AnnouncementCommunitiesForm(data)
    form = None
    if selection is not None and selection.is_valid():
        communities = selection.cleaned_data["communities"]
        if request.method == "POST":
            form = SubmissionCycleForm(request.POST, communities=communities)
            if form.is_valid():
                cycle = create_announcement(form)
                messages.success(request, "Δημιουργήθηκε η γνωστοποίηση (9.1). Μπορείτε να την εξάγετε με το κουμπί «Export».")
                return redirect("announcements:detail", pk=cycle.pk)
        else:
            form = SubmissionCycleForm(communities=communities)
    return render(
        request,
        "plots/announcement_form.html",
        {
            "step": 2 if form is not None else 1,
            "selection": selection,
            "form": form,
            "communities": selection.cleaned_data["communities"] if form is not None else [],
            "district_groups": _community_choices(),
            "selected_ids": {str(value) for value in data.getlist("communities")},
        },
    )


@access_required("announcements", post_action=EDIT)
def announcement_detail(request, pk):
    """9.1 and 9.3: offered plots and the notice dates (the 9.2 grid saves on its own).

    A published announcement is locked (9.3): it is shown read-only and edits are refused.
    """
    cycle = get_object_or_404(SubmissionCycle.objects.prefetch_related("communities"), pk=pk)
    status = 200
    forms_args = {}
    if request.method == "POST" and cycle.is_published:
        messages.error(request, PUBLISHED_MESSAGE)
        status = 409
    elif request.method == "POST":
        forms_args = {"data": request.POST}
    cycle_form = SubmissionCycleForm(instance=cycle, prefix="cycle", **forms_args)
    if forms_args and cycle_form.is_valid():
        with transaction.atomic():
            cycle_form.save()
        messages.success(request, "Οι αλλαγές της γνωστοποίησης αποθηκεύτηκαν.")
        return redirect("announcements:detail", pk=cycle.pk)
    if cycle.is_published or not has_access(request.user, "announcements", EDIT):
        disable_fields(cycle_form)

    return render(
        request,
        "plots/announcement_detail.html",
        {
            "cycle": cycle,
            "cycle_form": cycle_form,
            **publication_rows(cycle),
        },
        status=status,
    )


@access_required("announcements")
def announcement_export(request, pk):
    """9.3 «Export»: the Πρότυπο 1 notice (.docx) filled in from the announcement."""
    cycle = get_object_or_404(SubmissionCycle.objects.prefetch_related("communities"), pk=pk)
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


# --- 9.2 Publication methods: one row per method, add / edit / delete in a modal ----------------


class PublishedAnnouncement(Exception):
    pass


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
        cycle = get_object_or_404(SubmissionCycle, pk=pk)
        if cycle.is_published:
            raise PublishedAnnouncement()
        return cycle

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
        try:
            return handler(request, pk, publication_id)
        except PublishedAnnouncement:
            return JsonResponse({"ok": False, "message": PUBLISHED_MESSAGE}, status=409)

    return view


def _publication_date(request, pk, method):
    """9.2 Inline date of one of the four fixed methods; an empty date removes the row."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    require_access(request.user, "announcements", EDIT)
    if method not in SubmissionCyclePublication.FIXED_METHODS:
        raise Http404("Άγνωστος τρόπος δημοσίευσης.")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    if cycle.is_published:
        raise PublishedAnnouncement()
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


def _publication_date_endpoint(request, pk, method):
    try:
        return _publication_date(request, pk, method)
    except PublishedAnnouncement:
        return JsonResponse({"ok": False, "message": PUBLISHED_MESSAGE}, status=409)


publication_date = login_required(_publication_date_endpoint)
publication_form = _publication_endpoint(PUBLICATIONS.form_view)
publication_delete = _publication_endpoint(PUBLICATIONS.delete_view)
