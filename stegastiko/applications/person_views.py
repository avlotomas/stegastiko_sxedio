"""«Άτομα»: the registered persons (Person) in one table, with add / edit / delete."""

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import Person
from applications.person_forms import PersonForm
from cases.views.common import disable_fields
from core.function_catalog import CREATE, DELETE, EDIT, SEND
from core.permissions import access_required, has_access, has_any_access
from core.services import smtp_is_configured
from plot_applications.forms import PlotApplicationEmailForm
from plot_applications.models import PlotApplication
from plot_applications.services import (
    missing_documents_email_text,
    person_communications,
    plot_application_email_subject,
)

PERSON_LIST_PAGE_SIZE = 50


def person_applications(person):
    """Αιτήσεις παραχώρησης οικοπέδου στις οποίες συμμετέχει το άτομο (ως αιτητής ή σύζυγος)."""
    return (
        PlotApplication.objects.filter(Q(applicant=person) | Q(spouse=person))
        .select_related("announcement", "applicant", "spouse")
        .prefetch_related("announcement__plots__community", "parties", "children", "incomes")
        .order_by(F("preference_order").asc(nulls_last=True), "submitted_on", "id")
    )


def delete_refusal(person) -> str:
    """Why `person` cannot be deleted, or "" when it can."""
    if person_applications(person).exists():
        return "Το άτομο δεν διαγράφεται γιατί συμμετέχει σε αιτήσεις."
    if person.owned_design_plots.exists() or person.owned_plots.exists():
        return "Το άτομο δεν διαγράφεται γιατί είναι ιδιοκτήτης οικοπέδου."
    return ""


@access_required("persons")
def person_list(request):
    persons = Person.objects.annotate(
        applications_count=Count("plot_applications_as_applicant", distinct=True)
        + Count("plot_applications_as_spouse", distinct=True)
    ).order_by("last_name", "first_name", "identity_number")
    q = (request.GET.get("q") or "").strip()
    if q:
        persons = persons.filter(
            Q(identity_number__icontains=q)
            | Q(last_name__icontains=q)
            | Q(first_name__icontains=q)
        )
    page = Paginator(persons, PERSON_LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    filter_query = request.GET.copy()
    filter_query.pop("page", None)
    return render(
        request,
        "persons/list.html",
        {
            "persons": page.object_list,
            "page_obj": page,
            "filter_query": filter_query.urlencode(),
            "q": q,
        },
    )


@access_required("persons", CREATE)
def person_create(request):
    if request.method == "POST":
        form = PersonForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                person = form.save()
            messages.success(request, f"Καταχωρίστηκε το άτομο {person}.")
            return redirect("persons:detail", pk=person.pk)
    else:
        form = PersonForm()
    return render(request, "persons/form.html", {"form": form, "is_create": True})


@access_required("persons", post_action=EDIT)
def person_detail(request, pk):
    person = get_object_or_404(Person, pk=pk)
    can_edit = has_access(request.user, "persons", EDIT)
    if request.method == "POST":
        form = PersonForm(request.POST, instance=person)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, f"Οι αλλαγές στο άτομο {person} αποθηκεύτηκαν.")
            return redirect("persons:detail", pk=person.pk)
    else:
        form = PersonForm(instance=person)
    if not can_edit:
        disable_fields(form)
    applications = list(person_applications(person))
    for app in applications:
        app.email_subject = plot_application_email_subject(app)
        app.missing_documents_text = missing_documents_email_text(app)
    can_send_email = has_access(request.user, "plot_applications", SEND)
    return render(
        request,
        "persons/form.html",
        {
            "form": form,
            "person": person,
            "is_create": False,
            "can_edit": can_edit,
            "can_delete": has_access(request.user, "persons", DELETE),
            "delete_refusal": delete_refusal(person),
            "applications": applications,
            "can_send_email": can_send_email,
            "smtp_ready": smtp_is_configured(),
            "plot_application_email_form": PlotApplicationEmailForm(),
            "communications": person_communications(person),
        },
    )


@access_required("persons", DELETE)
def person_delete(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    person = get_object_or_404(Person, pk=pk)
    refusal = delete_refusal(person)
    if refusal:
        messages.error(request, refusal)
        return redirect("persons:detail", pk=person.pk)
    label = str(person)
    with transaction.atomic():
        person.delete()
    messages.success(request, f"Διαγράφηκε το άτομο {label}.")
    return redirect("persons:list")


@access_required("persons")
def person_applications_reorder(request, pk):
    """Ενημέρωση σειράς προτεραιότητας των αιτήσεων παραχώρησης οικοπέδου του ατόμου (drag and drop)."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if not (
        has_access(request.user, "persons", EDIT)
        or has_access(request.user, "plot_applications", EDIT)
    ):
        raise PermissionDenied("Δεν έχετε δικαίωμα τροποποίησης.")
    person = get_object_or_404(Person, pk=pk)

    if (request.content_type or "").startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            payload = {}
        raw_order = payload.get("order") or []
    else:
        raw_order = request.POST.getlist("order")

    requested_ids: list[int] = []
    for item in raw_order:
        try:
            app_id = int(item)
        except (TypeError, ValueError):
            continue
        if app_id not in requested_ids:
            requested_ids.append(app_id)

    apps_by_id = {app.pk: app for app in person_applications(person)}
    ordered_apps = [apps_by_id[app_id] for app_id in requested_ids if app_id in apps_by_id]
    for app_id, app in apps_by_id.items():
        if app_id not in requested_ids:
            ordered_apps.append(app)

    with transaction.atomic():
        for index, app in enumerate(ordered_apps, start=1):
            if app.preference_order != index:
                app.preference_order = index
                app.save()

    return JsonResponse(
        {
            "ok": True,
            "order": [
                {"id": app.pk, "preference_order": app.preference_order}
                for app in ordered_apps
            ],
        }
    )
