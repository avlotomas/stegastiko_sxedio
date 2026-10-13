"""Ενότητα 9 — Γνωστοποιήσεις: a flow of its own over the completed plots of a community."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from cases.models import SubmissionCycle, SubmissionCyclePublication
from cases.views.common import disable_fields
from cases.views.grid import GridEndpoint
from core.function_catalog import CREATE, EDIT, PUBLISH
from core.models import Community
from core.permissions import access_required, has_access, require_access
from plots.forms import AnnouncementTextForm, SubmissionCycleForm, SubmissionCyclePublicationForm
from plots.services import build_announcement_text, create_announcement, publish_announcement

PUBLISHED_MESSAGE = "Η ανακοίνωση έχει οριστικοποιηθεί και δεν αλλάζει."


def _first_error(exc: ValidationError) -> str:
    return exc.messages[0] if exc.messages else str(exc)


@access_required("announcements")
def announcement_list(request):
    cycles = SubmissionCycle.objects.select_related("community").prefetch_related("plots")
    community_id = request.GET.get("community_id") or ""
    if community_id:
        cycles = cycles.filter(community_id=community_id)
    return render(
        request,
        "plots/announcement_list.html",
        {
            "cycles": cycles,
            "communities": Community.objects.filter(is_active=True).order_by("name"),
            "community_id": community_id,
        },
    )


@access_required("announcements", CREATE)
def announcement_create(request):
    """9.1 New announcement: the community is chosen first, then its available plots."""
    community_id = request.POST.get("community_id") or request.GET.get("community_id")
    community = (
        Community.objects.filter(pk=community_id).first()
        if community_id and str(community_id).isdigit()
        else None
    )
    form = None
    if community is not None:
        if request.method == "POST":
            form = SubmissionCycleForm(request.POST, community=community)
            if form.is_valid():
                cycle = create_announcement(form)
                messages.success(request, "Δημιουργήθηκε η γνωστοποίηση (9.1) με προσχέδιο (9.3).")
                return redirect("announcements:detail", pk=cycle.pk)
        else:
            form = SubmissionCycleForm(community=community)
    return render(
        request,
        "plots/announcement_form.html",
        {
            "form": form,
            "community": community,
            "communities": Community.objects.filter(is_active=True).order_by("name"),
        },
    )


@access_required("announcements", post_action=EDIT)
def announcement_detail(request, pk):
    """9.1 and 9.3: offered plots and announcement text (the 9.2 grid saves on its own).

    A published announcement is locked (9.3): it is shown read-only and edits are refused.
    """
    cycle = get_object_or_404(SubmissionCycle.objects.select_related("community"), pk=pk)
    status = 200
    forms_args = {}
    if request.method == "POST" and cycle.is_published:
        messages.error(request, PUBLISHED_MESSAGE)
        status = 409
    elif request.method == "POST":
        forms_args = {"data": request.POST}
    cycle_form = SubmissionCycleForm(instance=cycle, prefix="cycle", **forms_args)
    text_form = AnnouncementTextForm(instance=cycle, **forms_args)
    if forms_args and all(f.is_valid() for f in (cycle_form, text_form)):
        with transaction.atomic():
            cycle_form.save()
            text_form.save()
        messages.success(request, "Οι αλλαγές της γνωστοποίησης αποθηκεύτηκαν.")
        return redirect("announcements:detail", pk=cycle.pk)
    if cycle.is_published or not has_access(request.user, "announcements", EDIT):
        disable_fields(cycle_form)
        disable_fields(text_form)

    return render(
        request,
        "plots/announcement_detail.html",
        {
            "cycle": cycle,
            "cycle_form": cycle_form,
            "text_form": text_form,
            "publications": cycle.publications.all(),
        },
        status=status,
    )


@access_required("announcements", EDIT)
def announcement_regenerate(request, pk):
    """9.3 Rebuild the draft from the current data."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    cycle = get_object_or_404(SubmissionCycle, pk=pk)
    if cycle.is_published:
        messages.error(request, PUBLISHED_MESSAGE)
    else:
        cycle.announcement_text = build_announcement_text(cycle)
        cycle.save()
        messages.success(request, "Το προσχέδιο ανακοίνωσης δημιουργήθηκε ξανά (9.3).")
    return redirect("announcements:detail", pk=cycle.pk)


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
        cycle = get_object_or_404(SubmissionCycle.objects.select_related("community"), pk=pk)
        if cycle.is_published:
            raise PublishedAnnouncement()
        return cycle

    def queryset(self, cycle):
        return SubmissionCyclePublication.objects.filter(submission_cycle=cycle)

    def new_instance(self, cycle):
        return SubmissionCyclePublication(submission_cycle=cycle)

    def grid_context(self, request, cycle):
        return {"publications": cycle.publications.all()}

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


publication_form = _publication_endpoint(PUBLICATIONS.form_view)
publication_delete = _publication_endpoint(PUBLICATIONS.delete_view)
