"""«Ολοκλήρωση αίτησης»: the case produces its plots in the «Οικόπεδα» table."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string

from cases.models import Case
from cases.templatetags.case_detail import case_readiness_context
from core.function_catalog import EDIT
from core.permissions import access_required
from plots.services import complete_case, completion_message


@access_required("case_completion", EDIT)
def case_complete(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    case = get_object_or_404(Case, pk=pk)
    try:
        summary = complete_case(case, request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else str(exc))
    else:
        messages.success(request, completion_message(summary))
    return redirect("cases:detail", pk=case.pk)


@access_required("case_completion")
def case_completion_readiness(request, pk):
    """The left readiness panel, re-rendered after changes made in place (dialogs)."""
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    html = render_to_string(
        "cases/_case_readiness_panel.html",
        case_readiness_context(request.user, case),
        request=request,
    )
    return JsonResponse({"ok": True, "html": html})
