"""«Άτομα»: the registered persons (Person) in one table, with add / edit / delete."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import Application, Person
from applications.person_forms import PersonForm
from cases.views.common import disable_fields
from core.function_catalog import CREATE, DELETE, EDIT
from core.permissions import access_required, has_access

PERSON_LIST_PAGE_SIZE = 50


def person_applications(person):
    return (
        Application.objects.filter(Q(person=person) | Q(person2=person))
        .select_related("community", "person", "person2")
        .order_by("-submitted_on", "-id")
    )


def delete_refusal(person) -> str:
    """Why `person` cannot be deleted, or "" when it can."""
    if (
        person_applications(person).exists()
        or person.plot_applications_as_applicant.exists()
        or person.plot_applications_as_spouse.exists()
    ):
        return "Το άτομο δεν διαγράφεται γιατί συμμετέχει σε αιτήσεις."
    if person.owned_design_plots.exists() or person.owned_plots.exists():
        return "Το άτομο δεν διαγράφεται γιατί είναι ιδιοκτήτης οικοπέδου."
    return ""


@access_required("persons")
def person_list(request):
    persons = Person.objects.annotate(
        applications_count=Count("applications_as_person1", distinct=True)
        + Count("applications_as_person2", distinct=True)
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
    applications = person_applications(person)
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
