from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import formats, timezone

from applications.models import Person
from applications.person_forms import PersonForm
from cases.models import CommunicationStatus
from core.function_catalog import (
    CREATE,
    DELETE,
    EDIT,
    FUNCTIONS_BY_CODE,
    PLOT_APPLICATION_SUBSECTION_CODES,
    SEND,
    VIEW,
)
from core.models import Community
from core.permissions import (
    access_required,
    editable_plot_application_subsections,
    has_access,
    has_any_access,
    plot_application_subsection_map,
)
from core.services import smtp_is_configured
from plot_applications.documents import (
    DOCUMENT_GROUPS,
    DOCUMENT_LABELS,
    applicable_documents,
    applicable_documents_for_forms,
)
from plot_applications.forms import (
    ApplicationPartyForm,
    ChildFormSet,
    IncomeFormSet,
    PersonIdentityForm,
    PlotApplicationEmailForm,
    PlotApplicationForm,
)
from plot_applications.models import (
    ApplicationParty,
    EligibilityResult,
    IncomeDeclaration,
    PlotApplication,
)
from plot_applications.rules import apply_evaluation, evaluate, income_evaluation_parameters, parameter
from plot_applications.services import (
    missing_documents_email_text,
    missing_documents_for_application,
    plot_application_communications,
    plot_application_email_subject,
    save_with_new_protocol_number,
    send_plot_application_email,
)

FUNCTION = "plot_applications"
COUPLE_VALUES = {str(value) for value in PlotApplication.COUPLE_STATUSES}

MAIN_SUBSECTION_FIELDS = {
    "basic": ("community", "submitted_on"),
    "section_1": (
        "email",
        "correspondence_street",
        "correspondence_number",
        "correspondence_apartment",
        "correspondence_community",
        "correspondence_postal_code",
        "correspondence_district",
    ),
    "section_2": (
        "residence_category",
        "neighbouring_community",
        "residence_street",
        "residence_number",
        "residence_apartment",
        "residence_postal_code",
        "residence_community",
        "origin_parent_description",
        "previous_residence_address",
        "residence_notes",
    ),
    "section_3": (
        "family_status",
        "single_parent_status",
        "single_parent_other",
    ),
    "section_9": (
        "has_dwelling",
        "has_dwelling_details",
        "has_residential_land",
        "has_residential_land_details",
    ),
    "section_10": (
        "has_alienated_property",
        "has_alienated_property_details",
    ),
    "section_11": (
        "previous_housing_aid",
        "previous_housing_aid_details",
    ),
    "section_12": (
        "applicant_signed",
        "spouse_signed",
    ),
    "sworn_declaration": (
        "sworn_by_applicant",
        "sworn_by_spouse",
        "sworn_declaration_date",
        "sworn_court",
    ),
    "documents": (
        "attached_documents",
        "other_documents",
    ),
}

PARTY_IDENTITY_SUBSECTION_FIELDS = (
    "social_insurance_number",
    "refugee_identity_number",
    "alien_registration_number",
    "citizenship",
    "citizenship_other",
    "mobile_phone",
    "landline_phone",
    "email",
)

PARTY_EMPLOYMENT_SUBSECTION_FIELDS = (
    "is_self_employed",
    "is_employee",
    "is_unemployed",
    "has_disability",
    "employer_details",
)


class ApplicationForms:
    """Όλες οι φόρμες της Αίτησης Παραρτήματος 3, με τα prefixes τους."""

    def __init__(
        self,
        data=None,
        instance: PlotApplication | None = None,
        editable_subsections: set[str] | None = None,
    ):
        instance = instance or PlotApplication()
        self.instance = instance
        if editable_subsections is not None and set(editable_subsections) >= set(
            PLOT_APPLICATION_SUBSECTION_CODES
        ):
            editable_subsections = None
        self.editable_subsections = editable_subsections
        bound = data is not None
        self.is_draft = bool(bound and data.get("save_draft"))
        if bound and ("children-TOTAL_FORMS" not in data or "incomes-TOTAL_FORMS" not in data):
            data = data.copy()
            if "children-TOTAL_FORMS" not in data:
                initial_children = instance.children.count() if instance.pk else 0
                data.setdefault("children-TOTAL_FORMS", str(initial_children))
                data.setdefault("children-INITIAL_FORMS", str(initial_children))
            if "incomes-TOTAL_FORMS" not in data:
                initial_incomes = instance.incomes.count() if instance.pk else 0
                data.setdefault("incomes-TOTAL_FORMS", str(initial_incomes))
                data.setdefault("incomes-INITIAL_FORMS", str(initial_incomes))
        if (
            bound
            and self._can_edit("section_3")
            and "main-family_status" in data
        ):
            self.is_couple = data.get("main-family_status") in COUPLE_VALUES
        else:
            self.is_couple = instance.pk is None or instance.is_couple

        initial_attached = {"attached_documents": instance.attached_documents} if instance.pk else {}
        self.main = PlotApplicationForm(
            data, instance=instance, prefix="main", initial=initial_attached, is_draft=self.is_draft
        )
        self.applicant = PersonIdentityForm(
            data,
            prefix="applicant",
            is_draft=self.is_draft,
            initial=self._person_initial(instance.applicant if instance.pk else None),
        )
        self.spouse = PersonIdentityForm(
            data,
            prefix="spouse",
            required=not self.is_draft,
            is_draft=self.is_draft,
            initial=self._person_initial(instance.spouse if instance.pk else None),
        )
        self.applicant_party = ApplicationPartyForm(
            data,
            prefix="applicant_party",
            role=ApplicationParty.Role.APPLICANT,
            is_draft=self.is_draft,
            instance=instance.applicant_party if instance.pk else None,
        )
        self.spouse_party = ApplicationPartyForm(
            data,
            prefix="spouse_party",
            role=ApplicationParty.Role.SPOUSE,
            is_draft=self.is_draft,
            instance=instance.spouse_party if instance.pk else None,
            use_required_attribute=False,
        )
        submitted_on = self._submitted_on(bound, data, instance)
        self.children = ChildFormSet(
            data if self._can_edit("section_7") else None,
            instance=instance,
            prefix="children",
            form_kwargs={"submitted_on": submitted_on, "is_draft": self.is_draft},
        )
        children_choices, child_id_to_index = self._children_choices(
            bound and self._can_edit("section_7"), data
        )
        self.incomes = IncomeFormSet(
            data if self._can_edit("section_8") else None,
            instance=instance,
            prefix="incomes",
            form_kwargs={
                "is_couple": self.is_couple,
                "is_draft": self.is_draft,
                "children_choices": children_choices,
                "child_id_to_index": child_id_to_index,
            },
        )
        if self.editable_subsections is not None:
            self._apply_editable_subsections()

    def _can_edit(self, sub_code: str) -> bool:
        return self.editable_subsections is None or sub_code in self.editable_subsections

    def _apply_editable_subsections(self) -> None:
        for sub_code, field_names in MAIN_SUBSECTION_FIELDS.items():
            if not self._can_edit(sub_code):
                for name in field_names:
                    if name in self.main.fields:
                        self.main.fields[name].disabled = True
                        self.main.fields[name].required = False

        if not self._can_edit("section_1"):
            for field in self.applicant.fields.values():
                field.disabled = True
                field.required = False
            for name in PARTY_IDENTITY_SUBSECTION_FIELDS:
                if name in self.applicant_party.fields:
                    self.applicant_party.fields[name].disabled = True
                    self.applicant_party.fields[name].required = False

        if not self._can_edit("section_4"):
            for name in PARTY_EMPLOYMENT_SUBSECTION_FIELDS:
                if name in self.applicant_party.fields:
                    self.applicant_party.fields[name].disabled = True
                    self.applicant_party.fields[name].required = False

        if not self._can_edit("section_5"):
            for field in self.spouse.fields.values():
                field.disabled = True
                field.required = False
            for name in PARTY_IDENTITY_SUBSECTION_FIELDS:
                if name in self.spouse_party.fields:
                    self.spouse_party.fields[name].disabled = True
                    self.spouse_party.fields[name].required = False

        if not self._can_edit("section_6"):
            for name in PARTY_EMPLOYMENT_SUBSECTION_FIELDS:
                if name in self.spouse_party.fields:
                    self.spouse_party.fields[name].disabled = True
                    self.spouse_party.fields[name].required = False

    def _children_choices(self, bound: bool, data) -> tuple[list[tuple[str, str]], dict[int, int]]:
        choices: list[tuple[str, str]] = []
        child_id_to_index: dict[int, int] = {}
        for idx, child_form in enumerate(self.children.forms):
            if child_form.instance.pk:
                child_id_to_index[child_form.instance.pk] = idx
            if bound:
                first = (data.get(child_form.add_prefix("first_name")) or "").strip()
                last = (data.get(child_form.add_prefix("last_name")) or "").strip()
            else:
                first = (child_form.instance.first_name or "").strip()
                last = (child_form.instance.last_name or "").strip()
            full_name = f"{first} {last}".strip()
            label = f"Τέκνο: {full_name}" if full_name else f"Τέκνο #{idx + 1}"
            choices.append((f"child:{idx}", label))
        return choices, child_id_to_index

    @staticmethod
    def _submitted_on(bound: bool, data, instance: PlotApplication) -> date | None:
        if bound:
            raw = (data.get("main-submitted_on") or "").strip()
            if raw:
                try:
                    return date.fromisoformat(raw)
                except ValueError:
                    return None
            return None
        return instance.submitted_on if instance.pk else None

    @staticmethod
    def _person_initial(person):
        if person is None:
            return {}
        return {
            name: getattr(person, name)
            for name in ("identity_number", *PersonIdentityForm.FIXED_FIELDS)
        }

    def _active_forms(self):
        forms = [self.main, self.applicant_party]
        if self._can_edit("section_1"):
            forms.append(self.applicant)
        if self._can_edit("section_7"):
            forms.append(self.children)
        if self._can_edit("section_8"):
            forms.append(self.incomes)
        if self.is_couple:
            forms.append(self.spouse_party)
            if self._can_edit("section_5"):
                forms.append(self.spouse)
        return forms

    def is_valid(self) -> bool:
        valid = all([form.is_valid() for form in self._active_forms()])
        if not valid:
            return False
        if self._can_edit("section_5"):
            if self.is_couple and not self.spouse.is_filled:
                if not self.is_draft:
                    self.spouse.add_error("identity_number", "Για Ζεύγος απαιτούνται τα στοιχεία συζύγου/συμβίου.")
                    return False
            elif self.is_couple and self.spouse.is_filled:
                applicant_id = (
                    self.applicant.cleaned_data["identity_number"].strip()
                    if self._can_edit("section_1") and self.applicant.is_filled
                    else (self.instance.applicant.identity_number if self.instance.pk and self.instance.applicant_id else "")
                )
                if applicant_id and applicant_id == self.spouse.cleaned_data["identity_number"].strip():
                    self.spouse.add_error("identity_number", "Ο/Η σύζυγος δεν μπορεί να έχει το ίδιο ΑΔΤ με τον/την αιτητή/τρια.")
                    return False

        if self._can_edit("section_7"):
            parent_identities = set()
            if self._can_edit("section_1") and self.applicant.is_filled:
                parent_identities.add(self.applicant.cleaned_data["identity_number"].strip())
            elif self.instance.pk and self.instance.applicant_id:
                parent_identities.add(self.instance.applicant.identity_number)
            if self.is_couple:
                if self._can_edit("section_5") and self.spouse.is_filled:
                    parent_identities.add(self.spouse.cleaned_data["identity_number"].strip())
                elif self.instance.pk and self.instance.spouse_id:
                    parent_identities.add(self.instance.spouse.identity_number)
            seen_child_identities: set[str] = set()
            child_id_error = False
            for child_form in self.children.forms:
                cleaned = getattr(child_form, "cleaned_data", None) or {}
                if not cleaned or cleaned.get("DELETE"):
                    continue
                child_id = (cleaned.get("identity_number") or "").strip()
                if not child_id:
                    continue
                if child_id in parent_identities:
                    child_form.add_error(
                        "identity_number",
                        "Το τέκνο δεν μπορεί να έχει το ίδιο ΑΔΤ με τον/την αιτητή/τρια ή τον/τη σύζυγο.",
                    )
                    child_id_error = True
                elif child_id in seen_child_identities:
                    child_form.add_error(
                        "identity_number",
                        "Υπάρχει ήδη τέκνο με το ίδιο ΑΔΤ στην αίτηση.",
                    )
                    child_id_error = True
                else:
                    seen_child_identities.add(child_id)
            if child_id_error:
                return False
        return True

    @transaction.atomic
    def save(self) -> PlotApplication:
        application = self.main.save(commit=False)
        if self._can_edit("documents"):
            application.attached_documents = list(self.main.cleaned_data.get("attached_documents") or [])
        elif self.instance.pk:
            application.attached_documents = list(self.instance.attached_documents or [])
        if self._can_edit("section_1") or not self.instance.pk:
            application.applicant = self.applicant.get_or_create_person()
        if self._can_edit("section_5") or not self.instance.pk:
            has_spouse = self.is_couple and self.spouse.is_filled
            application.spouse = self.spouse.get_or_create_person() if has_spouse else None
        elif not self.is_couple:
            application.spouse = None
        if not self.is_couple:
            application.spouse_signed = False
            application.sworn_by_spouse = False
        if not application.pk and application.preference_order is None:
            persons = [p for p in (application.applicant, application.spouse) if p]
            max_order = (
                PlotApplication.objects.filter(Q(applicant__in=persons) | Q(spouse__in=persons))
                .aggregate(max_order=Max("preference_order"))
                .get("max_order")
                or 0
            )
            application.preference_order = max_order + 1
        if application.pk:
            application.save()
        else:
            save_with_new_protocol_number(application)

        self._save_party(application, self.applicant_party, ApplicationParty.Role.APPLICANT)
        if self.is_couple:
            self._save_party(application, self.spouse_party, ApplicationParty.Role.SPOUSE)
        else:
            application.parties.filter(role=ApplicationParty.Role.SPOUSE).delete()

        if self._can_edit("section_7"):
            self.children.instance = application
            self.children.save()
            saved_children_by_index = {
                idx: child_form.instance
                for idx, child_form in enumerate(self.children.forms)
                if child_form.instance.pk and not child_form.cleaned_data.get("DELETE")
            }
        else:
            saved_children_by_index = {
                idx: child for idx, child in enumerate(application.children.all())
            }

        if self._can_edit("section_8"):
            self.incomes.instance = application
            kept_income_ids: list[int] = []
            for income_form in self.incomes.forms:
                cleaned = getattr(income_form, "cleaned_data", None) or {}
                member = cleaned.get("member")
                skip = (
                    not cleaned
                    or cleaned.get("DELETE")
                    or income_form.is_empty
                    or (member == IncomeDeclaration.Member.SPOUSE and not self.is_couple)
                )
                if skip:
                    continue
                income = income_form.save(commit=False)
                income.application = application
                income.member = member
                if member == IncomeDeclaration.Member.CHILD:
                    child_idx = getattr(income_form, "selected_child_index", None)
                    income.child = (
                        saved_children_by_index.get(child_idx)
                        if child_idx is not None
                        else income.child
                    )
                else:
                    income.child = None
                income.save()
                kept_income_ids.append(income.pk)
            application.incomes.exclude(pk__in=kept_income_ids).delete()

        if not self.is_draft and self._can_edit("documents"):
            applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren"))
            application.attached_documents = [
                code for code in application.attached_documents if code in applicable
            ]

        apply_evaluation(application)
        return application

    @staticmethod
    def _save_party(application, form, role):
        party = form.save(commit=False)
        party.application = application
        party.role = role
        party.save()


def _can_send_email(user) -> bool:
    return has_access(user, FUNCTION, SEND)


def delete_refusal(application: PlotApplication) -> str:
    if application.allocations.exists():
        return "Η αίτηση δεν διαγράφεται γιατί έχει κατανομή οικοπέδου."
    return ""


def _wants_json(request) -> bool:
    accept = request.headers.get("Accept") or ""
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _email_context(request, application: PlotApplication | None) -> dict:
    if application is None or not application.pk:
        return {
            "can_send_email": False,
            "smtp_ready": smtp_is_configured(),
            "communications": [],
        }
    subject = plot_application_email_subject(application)
    missing_text = missing_documents_email_text(application)
    return {
        "can_send_email": _can_send_email(request.user),
        "smtp_ready": smtp_is_configured(),
        "email_subject": subject,
        "missing_documents_text": missing_text,
        "missing_documents": missing_documents_for_application(application),
        "plot_application_email_form": PlotApplicationEmailForm(
            initial={
                "recipient": application.email,
                "subject": subject,
                "body": missing_text,
            }
        ),
        "communications": plot_application_communications(application),
    }


def _render_form(request, forms: ApplicationForms, application=None):
    main = forms.main
    income_params = income_evaluation_parameters()
    visible_documents = applicable_documents_for_forms(
        forms, income_params["large_family_children"]
    )
    document_groups = []
    for title, items in DOCUMENT_GROUPS:
        item_codes = dict(items)
        choices = [choice for choice in main["attached_documents"] if choice.data["value"] in item_codes]
        for choice in choices:
            if choice.data["value"] not in visible_documents:
                choice.data["attrs"]["disabled"] = True
        group_visible = any(choice.data["value"] in visible_documents for choice in choices)
        document_groups.append((title, choices, group_visible))
    return render(
        request,
        "plot_applications/form.html",
        {
            "forms": forms,
            "form": main,
            "application": application,
            "is_create": application is None,
            "income_parameters": income_params,
            "visible_documents": visible_documents,
            "document_groups": document_groups,
            "sub_edit": plot_application_subsection_map(request.user, EDIT),
            "delete_refusal": delete_refusal(application) if application else "",
            **_email_context(request, application),
        },
    )


def _person_payload(request, person: Person) -> dict:
    fields = {name: getattr(person, name) for name in ("identity_number", *PersonIdentityForm.FIXED_FIELDS)}
    fields["date_of_birth"] = person.date_of_birth.isoformat() if person.date_of_birth else ""
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
                if forms.is_draft:
                    messages.success(
                        request,
                        f"Η αίτηση {application.protocol_number} αποθηκεύτηκε προσωρινά.",
                    )
                else:
                    messages.success(request, f"Η αίτηση {application.protocol_number} καταχωρήθηκε.")
                if has_access(request.user, FUNCTION, EDIT):
                    return redirect("plot_applications:edit", pk=application.pk)
                if has_access(request.user, FUNCTION, VIEW):
                    return redirect("plot_applications:detail", pk=application.pk)
                return redirect("plot_applications:list")
    else:
        forms = ApplicationForms()
        community_id = request.GET.get("community")
        if community_id and community_id.isdigit():
            forms.main.initial["community"] = int(community_id)
    return _render_form(request, forms)


@access_required(FUNCTION, EDIT)
def plot_application_edit(request, pk):
    application = get_object_or_404(PlotApplication, pk=pk)
    editable_subsections = editable_plot_application_subsections(request.user)
    if request.method == "POST":
        forms = ApplicationForms(
            request.POST,
            instance=application,
            editable_subsections=editable_subsections,
        )
        if forms.is_valid():
            try:
                application = forms.save()
            except ValidationError as exc:
                forms.main.add_error(None, exc.messages[0] if exc.messages else str(exc))
            else:
                if forms.is_draft:
                    messages.success(request, "Η αίτηση αποθηκεύτηκε προσωρινά.")
                else:
                    messages.success(request, "Η αίτηση ενημερώθηκε.")
                return redirect("plot_applications:edit", pk=application.pk)
    else:
        forms = ApplicationForms(
            instance=application,
            editable_subsections=editable_subsections,
        )
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
        .order_by(F("preference_order").asc(nulls_last=True), "submitted_on", "id")
    )
    attached = set(application.attached_documents)
    applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren")) | attached
    document_groups = [
        (title, [(code, label, code in attached) for code, label in items if code in applicable])
        for title, items in DOCUMENT_GROUPS
    ]
    document_groups = [(title, items) for title, items in document_groups if items]
    return render(
        request,
        "plot_applications/detail.html",
        {
            "application": application,
            "outcome": outcome,
            "other_applications": other_applications,
            "document_groups": document_groups,
            "attached_count": len(attached & set(DOCUMENT_LABELS)),
            "sub_view": plot_application_subsection_map(request.user, VIEW),
            "delete_refusal": delete_refusal(application),
            **_email_context(request, application),
        },
    )


@access_required(FUNCTION, DELETE)
def plot_application_delete(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    application = get_object_or_404(PlotApplication, pk=pk)
    refusal = delete_refusal(application)
    if refusal:
        messages.error(request, refusal)
        if has_access(request.user, FUNCTION, VIEW):
            return redirect("plot_applications:detail", pk=application.pk)
        return redirect("plot_applications:list")
    protocol = application.protocol_number
    with transaction.atomic():
        application.delete()
    messages.success(request, f"Διαγράφηκε η αίτηση {protocol}.")
    return redirect("plot_applications:list")


@login_required
def plot_application_email_send(request, pk):
    """Αποστολή email προς το άτομο/αιτητή της αίτησης και καταγραφή στο ιστορικό."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if not _can_send_email(request.user):
        raise PermissionDenied("Δεν έχετε δικαίωμα αποστολής email.")
    application = get_object_or_404(
        PlotApplication.objects.select_related("community", "applicant", "spouse"), pk=pk
    )

    form = PlotApplicationEmailForm(request.POST)
    errors = []
    communication = None
    if form.is_valid():
        recipient = (form.cleaned_data.get("recipient") or application.email or "").strip()
        try:
            communication = send_plot_application_email(
                application,
                form.cleaned_data["subject"],
                form.cleaned_data["body"],
                recipient=recipient,
            )
        except ValidationError as exc:
            errors = exc.messages
    else:
        errors = [error for field_errors in form.errors.values() for error in field_errors]

    if communication:
        message = f"Το email στάλθηκε στο {communication.recipient}."
    if _wants_json(request):
        if not communication:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        log_html = render_to_string(
            "plot_applications/_email_log.html",
            {
                "application": application,
                "communications": plot_application_communications(application),
            },
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                "message": message,
                "log_html": log_html,
            }
        )

    if communication:
        messages.success(request, message)
    else:
        for error in errors:
            messages.error(request, error)
    return redirect("plot_applications:detail", pk=application.pk)


@login_required
def plot_application_communication_detail(request, pk, communication_id):
    """Προβολή ενός απεσταλμένου email αίτησης παραχώρησης οικοπέδου στο modal ιστορικού."""
    if not (
        has_any_access(request.user, FUNCTION, (VIEW, EDIT, SEND))
        or has_access(request.user, "persons", VIEW)
    ):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
    if request.method != "GET" or not _wants_json(request):
        raise Http404("Επιτρέπεται μόνο GET JSON.")
    application = get_object_or_404(PlotApplication, pk=pk)
    communication = get_object_or_404(
        plot_application_communications(application), pk=communication_id
    )
    sent_at = ""
    if communication.sent_at:
        sent_at = formats.date_format(
            timezone.localtime(communication.sent_at), "SHORT_DATETIME_FORMAT"
        )
    return JsonResponse(
        {
            "ok": True,
            "recipient": communication.recipient,
            "subject": communication.subject,
            "body": communication.body,
            "check_label": application.protocol_number,
            "status": communication.status,
            "status_display": CommunicationStatus.label(communication.status),
            "sent_at": sent_at,
        }
    )


@login_required
def plot_application_list(request):
    if not has_any_access(request.user, FUNCTION, FUNCTIONS_BY_CODE[FUNCTION].actions):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
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
