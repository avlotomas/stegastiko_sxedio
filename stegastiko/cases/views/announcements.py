"""Ενότητα 9 — Γνωστοποίηση / ανακοίνωση έναρξης αιτήσεων (9.1–9.5)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from cases import section_refs as refs
from cases.forms import AnnouncementTextForm, SubmissionCycleForm, SubmissionCyclePublicationFormSet
from cases.models import Case, SubmissionCycle
from cases.section_labels import get_case_section_label
from cases.services import (
    announcement_readiness,
    build_announcement_text,
    create_announcement,
    publish_announcement,
)
from cases.views.common import case_nav_items, disable_fields
from core.function_catalog import CREATE, EDIT, PUBLISH, VIEW, case_section_function
from core.permissions import has_access, require_access

SECTION_9_FUNCTION = case_section_function(refs.SECTION_9)
PUBLISHED_MESSAGE = "Η ανακοίνωση έχει οριστικοποιηθεί και δεν αλλάζει."


def _first_error(exc: ValidationError) -> str:
    return exc.messages[0] if exc.messages else str(exc)


@login_required
def announcement_create(request, pk):
    """9.1 Create the announcement of a case, gated by the 9.4 readiness check (§Β.2)."""
    require_access(request.user, SECTION_9_FUNCTION, CREATE if request.method == "POST" else VIEW)
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    readiness = announcement_readiness(case)
    if request.method == "POST":
        form = SubmissionCycleForm(request.POST, community=case.community)
        if form.is_valid():
            try:
                cycle = create_announcement(form, case)
            except ValidationError as exc:
                form.add_error(None, _first_error(exc))
            else:
                messages.success(request, "Δημιουργήθηκε η γνωστοποίηση (9.1) με προσχέδιο (9.3).")
                return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)
    else:
        form = SubmissionCycleForm(community=case.community, initial={"cases": [case]})
    return render(
        request,
        "cases/announcement_form.html",
        {
            "case": case,
            "form": form,
            "readiness": readiness,
            "submission_cycles": case.submission_cycles.all(),
            "case_nav": case_nav_items(case, request.user, active_key=refs.SECTION_9),
            "section_title": get_case_section_label(refs.SECTION_9),
        },
    )


@login_required
def announcement_detail(request, pk, cycle_id):
    """9.2–9.4 Publication methods, announcement text and readiness.

    A published announcement is locked (9.3): it is shown read-only and edits are refused.
    """
    require_access(request.user, SECTION_9_FUNCTION, EDIT if request.method == "POST" else VIEW)
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    cycle = get_object_or_404(SubmissionCycle, pk=cycle_id, cases=case)
    status = 200

    if request.method == "POST" and cycle.is_published:
        messages.error(request, PUBLISHED_MESSAGE)
        status = 409
        text_form = AnnouncementTextForm(instance=cycle)
        publications = SubmissionCyclePublicationFormSet(instance=cycle, prefix="publications")
    elif request.method == "POST":
        text_form = AnnouncementTextForm(request.POST, instance=cycle)
        publications = SubmissionCyclePublicationFormSet(
            request.POST, instance=cycle, prefix="publications"
        )
        if text_form.is_valid() and publications.is_valid():
            with transaction.atomic():
                text_form.save()
                publications.save()
            messages.success(request, "Οι αλλαγές της γνωστοποίησης αποθηκεύτηκαν.")
            return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)
    else:
        text_form = AnnouncementTextForm(instance=cycle)
        publications = SubmissionCyclePublicationFormSet(instance=cycle, prefix="publications")
    if cycle.is_published or not has_access(request.user, SECTION_9_FUNCTION, EDIT):
        disable_fields(text_form)
        for child in publications:
            disable_fields(child)

    return render(
        request,
        "cases/announcement_detail.html",
        {
            "case": case,
            "cycle": cycle,
            "text_form": text_form,
            "publications": publications,
            "readiness_by_case": [
                (linked, announcement_readiness(linked)) for linked in cycle.cases.all()
            ],
            "case_nav": case_nav_items(case, request.user, active_key=refs.SECTION_9),
            "section_title": get_case_section_label(refs.SECTION_9),
        },
        status=status,
    )


@login_required
def announcement_regenerate(request, pk, cycle_id):
    """9.3 Rebuild the draft from current case data."""
    require_access(request.user, SECTION_9_FUNCTION, EDIT)
    case = get_object_or_404(Case, pk=pk)
    cycle = get_object_or_404(SubmissionCycle, pk=cycle_id, cases=case)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if cycle.is_published:
        messages.error(request, PUBLISHED_MESSAGE)
    else:
        cycle.announcement_text = build_announcement_text(cycle)
        cycle.save()
        messages.success(request, "Το προσχέδιο ανακοίνωσης δημιουργήθηκε ξανά (9.3).")
    return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)


@login_required
def announcement_publish(request, pk, cycle_id):
    """9.3 Finalise and issue the announcement."""
    require_access(request.user, SECTION_9_FUNCTION, PUBLISH)
    case = get_object_or_404(Case, pk=pk)
    cycle = get_object_or_404(SubmissionCycle, pk=cycle_id, cases=case)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    try:
        publish_announcement(cycle)
    except ValidationError as exc:
        messages.error(request, _first_error(exc))
    else:
        messages.success(request, "Η ανακοίνωση οριστικοποιήθηκε και εκδόθηκε (9.3).")
    return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)
