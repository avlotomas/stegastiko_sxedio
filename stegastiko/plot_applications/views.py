from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from applications.models import Person
from applications.person_forms import PersonForm
from core.function_catalog import CREATE, EDIT
from core.models import Community
from core.permissions import access_required, has_access, has_any_access
from plot_applications.documents import DOCUMENT_GROUPS, DOCUMENT_LABELS
from plot_applications.forms import (
    ApplicationPartyForm,
    ChildFormSet,
    IncomeDeclarationForm,
    PersonIdentityForm,
    PlotApplicationForm,
)
from plot_applications.models import (
    ApplicationParty,
    EligibilityResult,
    IncomeDeclaration,
    PlotApplication,
)
from plot_applications.rules import apply_evaluation, evaluate
from plot_applications.services import save_with_new_protocol_number

FUNCTION = "plot_applications"
COUPLE_VALUES = {str(value) for value in PlotApplication.COUPLE_STATUSES}
INCOME_MEMBERS = (
    (IncomeDeclaration.Member.APPLICANT, "income_applicant"),
    (IncomeDeclaration.Member.SPOUSE, "income_spouse"),
    (IncomeDeclaration.Member.OTHER, "income_other"),
)


class ApplicationForms:
    """Όλες οι φόρμες της Αίτησης Παραρτήματος 3, με τα prefixes τους."""

    def __init__(self, data=None, instance: PlotApplication | None = None):
        instance = instance or PlotApplication()
        self.instance = instance
        bound = data is not None
        if bound:
            self.is_couple = data.get("main-family_status") in COUPLE_VALUES
        else:
            self.is_couple = instance.pk is None or instance.is_couple

        initial_attached = {"attached_documents": instance.attached_documents} if instance.pk else {}
        self.main = PlotApplicationForm(data, instance=instance, prefix="main", initial=initial_attached)
        self.applicant = PersonIdentityForm(
            data, prefix="applicant", initial=self._person_initial(instance.applicant if instance.pk else None)
        )
        self.spouse = PersonIdentityForm(
            data,
            prefix="spouse",
            required=True,
            initial=self._person_initial(instance.spouse if instance.pk else None),
        )
        self.applicant_party = ApplicationPartyForm(
            data, prefix="applicant_party", role=ApplicationParty.Role.APPLICANT,
            instance=instance.applicant_party if instance.pk else None,
        )
        self.spouse_party = ApplicationPartyForm(
            data, prefix="spouse_party", role=ApplicationParty.Role.SPOUSE,
            instance=instance.spouse_party if instance.pk else None,
            use_required_attribute=False,
        )
        self.children = ChildFormSet(data, instance=instance, prefix="children")
        incomes = {income.member: income for income in instance.incomes.all()} if instance.pk else {}
        self.incomes = [
            (member, IncomeDeclarationForm(data, prefix=prefix, member=member, instance=incomes.get(member)))
            for member, prefix in INCOME_MEMBERS
        ]

    @staticmethod
    def _person_initial(person):
        if person is None:
            return {}
        return {
            name: getattr(person, name)
            for name in ("identity_number", *PersonIdentityForm.FIXED_FIELDS)
        }

    def _active_forms(self):
        forms = [self.main, self.applicant, self.applicant_party, self.children]
        forms.append(self.incomes[0][1])
        forms.append(self.incomes[2][1])
        if self.is_couple:
            forms += [self.spouse, self.spouse_party, self.incomes[1][1]]
        return forms

    def is_valid(self) -> bool:
        valid = all([form.is_valid() for form in self._active_forms()])
        if not valid:
            return False
        if self.is_couple and not self.spouse.is_filled:
            self.spouse.add_error("identity_number", "Για Ζεύγος απαιτούνται τα στοιχεία συζύγου/συμβίου.")
            return False
        applicant_id = self.applicant.cleaned_data["identity_number"].strip()
        if self.is_couple and applicant_id == self.spouse.cleaned_data["identity_number"].strip():
            self.spouse.add_error("identity_number", "Ο/Η σύζυγος δεν μπορεί να έχει το ίδιο ΑΔΤ με τον/την αιτητή/τρια.")
            return False
        return True

    @transaction.atomic
    def save(self) -> PlotApplication:
        application = self.main.save(commit=False)
        application.attached_documents = list(self.main.cleaned_data.get("attached_documents") or [])
        application.applicant = self.applicant.get_or_create_person()
        application.spouse = self.spouse.get_or_create_person() if self.is_couple else None
        if not self.is_couple:
            application.spouse_signed = False
            application.sworn_by_spouse = False
        if application.pk:
            application.save()
        else:
            save_with_new_protocol_number(application)

        self._save_party(application, self.applicant_party, ApplicationParty.Role.APPLICANT)
        if self.is_couple:
            self._save_party(application, self.spouse_party, ApplicationParty.Role.SPOUSE)
        else:
            application.parties.filter(role=ApplicationParty.Role.SPOUSE).delete()

        self.children.instance = application
        self.children.save()

        for member, form in self.incomes:
            skip = (member == IncomeDeclaration.Member.SPOUSE and not self.is_couple) or (
                member == IncomeDeclaration.Member.OTHER and form.is_empty
            )
            if skip:
                application.incomes.filter(member=member).delete()
                continue
            income = form.save(commit=False)
            income.application = application
            income.member = member
            income.save()

        apply_evaluation(application)
        return application

    @staticmethod
    def _save_party(application, form, role):
        party = form.save(commit=False)
        party.application = application
        party.role = role
        party.save()


def _render_form(request, forms: ApplicationForms, application=None):
    main = forms.main
    return render(
        request,
        "plot_applications/form.html",
        {
            "forms": forms,
            "form": main,
            "application": application,
            "is_create": application is None,
            "document_groups": [
                (title, [choice for choice in main["attached_documents"] if choice.data["value"] in dict(items)])
                for title, items in DOCUMENT_GROUPS
            ],
        },
    )


def _person_payload(request, person: Person) -> dict:
    fields = {name: getattr(person, name) for name in ("identity_number", *PersonIdentityForm.FIXED_FIELDS)}
    fields["date_of_birth"] = person.date_of_birth.isoformat()
    return {
        "found": True,
        "person": fields,
        "can_edit": has_access(request.user, "persons", EDIT),
        "edit_url": reverse("plot_applications:person_edit", args=[person.pk]),
    }


@login_required
def person_lookup(request):
    """Υπάρχον Άτομο με ακριβές ΑΔΤ, για συμπλήρωση των σταθερών στοιχείων στη φόρμα αίτησης."""
    if not has_any_access(request.user, FUNCTION, (CREATE, EDIT)):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
    identity = (request.GET.get("identity") or "").strip()
    person = Person.objects.filter(identity_number=identity).first() if identity else None
    if person is None:
        return JsonResponse({"found": False})
    return JsonResponse(_person_payload(request, person))


@access_required("persons", EDIT)
def person_edit(request, pk):
    """Modal επεξεργασίας των σταθερών στοιχείων ατόμου· επιστρέφει τη φόρμα ή, μετά την αποθήκευση, JSON."""
    person = get_object_or_404(Person, pk=pk)
    status = 200
    if request.method == "POST":
        form = PersonForm(request.POST, instance=person)
        if form.is_valid():
            with transaction.atomic():
                person = form.save()
            return JsonResponse({**_person_payload(request, person), "saved": True})
        status = 422
    else:
        form = PersonForm(instance=person)
    return render(
        request,
        "plot_applications/_person_edit_dialog.html",
        {"form": form, "person": person},
        status=status,
    )


@access_required(FUNCTION, CREATE)
def plot_application_create(request):
    if request.method == "POST":
        forms = ApplicationForms(request.POST)
        if forms.is_valid():
            try:
                application = forms.save()
            except ValidationError as exc:
                forms.main.add_error(None, exc.messages[0] if exc.messages else str(exc))
            except IntegrityError:
                forms.main.add_error(None, "Η αποθήκευση δεν ολοκληρώθηκε λόγω ταυτόχρονης καταχώρισης. Δοκιμάστε ξανά.")
            else:
                messages.success(request, f"Η αίτηση {application.protocol_number} καταχωρήθηκε.")
                return redirect("plot_applications:detail", pk=application.pk)
    else:
        forms = ApplicationForms()
        community_id = request.GET.get("community")
        if community_id and community_id.isdigit():
            forms.main.initial["community"] = int(community_id)
    return _render_form(request, forms)


@access_required(FUNCTION, EDIT)
def plot_application_edit(request, pk):
    application = get_object_or_404(PlotApplication, pk=pk)
    if request.method == "POST":
        forms = ApplicationForms(request.POST, instance=application)
        if forms.is_valid():
            try:
                application = forms.save()
            except ValidationError as exc:
                forms.main.add_error(None, exc.messages[0] if exc.messages else str(exc))
            else:
                messages.success(request, "Η αίτηση ενημερώθηκε.")
                return redirect("plot_applications:detail", pk=application.pk)
    else:
        forms = ApplicationForms(instance=application)
    return _render_form(request, forms, application)


@access_required(FUNCTION)
def plot_application_detail(request, pk):
    application = get_object_or_404(
        PlotApplication.objects.select_related(
            "community", "applicant", "spouse"
        ).prefetch_related("parties", "children", "incomes"),
        pk=pk,
    )
    outcome = evaluate(application)
    persons = [p for p in (application.applicant, application.spouse) if p]
    other_applications = (
        PlotApplication.objects.filter(Q(applicant__in=persons) | Q(spouse__in=persons))
        .exclude(pk=application.pk)
        .select_related("community", "applicant", "spouse")
    )
    attached = set(application.attached_documents)
    return render(
        request,
        "plot_applications/detail.html",
        {
            "application": application,
            "outcome": outcome,
            "other_applications": other_applications,
            "document_groups": [
                (title, [(code, label, code in attached) for code, label in items])
                for title, items in DOCUMENT_GROUPS
            ],
            "attached_count": len(attached & set(DOCUMENT_LABELS)),
        },
    )


@access_required(FUNCTION)
def plot_application_list(request):
    applications = PlotApplication.objects.select_related(
        "community", "applicant", "spouse"
    )
    community_id = request.GET.get("community_id") or ""
    result = request.GET.get("result") or ""
    q = (request.GET.get("q") or "").strip()
    if community_id:
        applications = applications.filter(community_id=community_id)
    if result in EligibilityResult.values:
        applications = applications.filter(eligibility_result=result)
    if q:
        applications = applications.filter(
            Q(protocol_number__icontains=q)
            | Q(applicant__identity_number__icontains=q)
            | Q(spouse__identity_number__icontains=q)
            | Q(applicant__last_name__icontains=q)
            | Q(spouse__last_name__icontains=q)
        )
    order = request.GET.get("order") or ""
    if order == "priority":
        applications = applications.order_by(
            "community__name", "priority_primary", "priority_secondary", "submitted_on", "id"
        )
    return render(
        request,
        "plot_applications/list.html",
        {
            "applications": applications,
            "communities": Community.objects.filter(is_active=True).order_by("name"),
            "results": EligibilityResult.choices,
            "community_id": community_id,
            "result": result,
            "order": order,
            "q": q,
        },
    )
