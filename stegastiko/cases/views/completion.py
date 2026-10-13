"""«Ολοκλήρωση αίτησης»: the case produces its plots in the «Οικόπεδα» table."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from cases.models import Case
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
