import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme

from applications.models import Person
from applications.person_forms import PersonForm
from cases.models import CommunicationStatus
from core.function_catalog import (
    CREATE,
    DELETE,
    EDIT,
    EXPORT,
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
from core.timeline import build_timeline
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
    PlotApplicationDocumentsCompletenessForm,
    PlotApplicationEligibilityOverrideForm,
    PlotApplicationEmailForm,
    PlotApplicationForm,
    PlotApplicationIncompleteRejectionForm,
)
from plot_applications.models import (
    ApplicationCompleteness,
    ApplicationParty,
    ApplicationStage,
    DocumentsCompleteness,
    EligibilityResult,
    IncomeDeclaration,
    Objection,
    PlotAllocationStatus,
    PlotApplication,
)
from plot_applications.prioritization import (
    BENEFICIARIES,
    GROUPS,
    OTHERS,
    PRIORITIZATION_STAGES,
    build_prioritization_list,
    prioritization_history as prioritization_history_entries,
    reset_manual_order,
    save_manual_order,
)
from plot_applications.rules import (
    apply_evaluation,
    evaluate,
    income_evaluation_parameters,
    missing_completeness_fields_for_forms,
    parameter,
    required_documents,
    required_documents_for_forms,
)
from plot_applications.services import (
    missing_documents_email_text,
    missing_documents_for_application,
    plot_application_communications,
    plot_application_email_subject,
    plot_application_history as plot_application_history_entries,
    save_with_new_protocol_number,
    send_plot_application_email,
)
from plot_applications.grid_settings import (
    PLOT_APPLICATION_GRID_COLUMN_CODES,
    PLOT_APPLICATION_GRID_COLUMN_LABELS,
    get_plot_application_grid_columns,
    get_plot_application_grid_locked_columns,
)
from plot_applications.beneficiary_lists import (
    LIST_VIEW_CHANGES,
    LIST_VIEW_FINAL,
    LIST_VIEW_PRELIMINARY,
    LIST_VIEWS,
    PHASE_COMMITTEE,
    PHASE_FINAL,
    PHASE_OBJECTIONS,
    BeneficiaryListError,
    application_list_decisions,
    blocking_applications,
    community_lists,
    final_listing,
    issue_final_list,
    issue_preliminary_list,
    list_changes,
    revoke_final_list,
    revoke_preliminary_list,
    snapshot_listing,
)
from plot_applications.stage_labels import application_stage_choices, application_stage_steps

FUNCTION = "plot_applications"
COUPLE_VALUES = {str(value) for value in PlotApplication.COUPLE_STATUSES}

MAIN_SUBSECTION_FIELDS = {
    "basic": ("announcement", "submitted_on"),
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
        "resides_in_controlled_areas",
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
        "documents_complete_override",
        "documents_complete_reason",
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
        self.is_draft = False
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
        existing_notes = (
            instance.document_notes
            if instance.pk and isinstance(instance.document_notes, dict)
            else {}
        )
        cleaned_existing_notes = {
            str(code): str(val).strip()
            for code, val in existing_notes.items()
            if code in DOCUMENT_LABELS and str(val).strip()
        }
        if (
            bound
            and self._can_edit("documents")
            and any(f"document_note_{code}" in data for code in DOCUMENT_LABELS)
        ):
            self.document_notes = {
                code: (data.get(f"document_note_{code}") or "").strip()
                for code in DOCUMENT_LABELS
                if (data.get(f"document_note_{code}") or "").strip()
            }
        else:
            self.document_notes = cleaned_existing_notes
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
            required=False,
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
        if self._can_edit("section_5") and self.is_couple and self.spouse.is_filled:
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
            application.document_notes = dict(self.document_notes)
        elif self.instance.pk:
            application.attached_documents = list(self.instance.attached_documents or [])
            application.document_notes = dict(self.instance.document_notes or {})
            application.documents_complete_override = self.instance.documents_complete_override
            application.documents_complete_reason = self.instance.documents_complete_reason
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

        if self._can_edit("documents"):
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
                "body": "",
            }
        ),
        "communications": plot_application_communications(application),
    }


def _redirect_after_application_action(request, application: PlotApplication):
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("plot_applications:detail", pk=application.pk)


def _application_actions_context(
    request,
    application: PlotApplication | None,
    sub_view: dict[str, bool],
    sub_edit: dict[str, bool],
) -> dict:
    if application is None or not application.pk:
        return {
            "outcome": None,
            "application_stages": application_stage_steps(),
            "list_decisions": [],
            "can_override_eligibility": False,
            "eligibility_override_form": None,
            "can_reject_incomplete": False,
            "can_revoke_incomplete_rejection": False,
            "incomplete_rejection_form": None,
            "readonly_document_groups": [],
            "attached_count": 0,
            "required_documents_count": 0,
            "satisfied_required_count": 0,
            "missing_documents_count": 0,
            "can_edit_documents": bool(sub_edit.get("documents")),
            "documents_completeness_form": None,
            "delete_refusal": "",
            **_email_context(request, None),
        }
    outcome = evaluate(application)
    attached = set(application.attached_documents)
    raw_notes = application.document_notes if isinstance(application.document_notes, dict) else {}
    applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren")) | attached
    readonly_document_groups = [
        (
            title,
            [
                (code, label, code in attached, str(raw_notes.get(code) or "").strip())
                for code, label in items
                if code in applicable
            ],
        )
        for title, items in DOCUMENT_GROUPS
    ]
    readonly_document_groups = [(title, items) for title, items in readonly_document_groups if items]
    req_list = required_documents(application)
    satisfied_required_count = len(req_list) - len(outcome["missing_documents"])
    can_edit_documents = bool(sub_edit.get("documents"))
    documents_completeness_form = PlotApplicationDocumentsCompletenessForm(
        initial={
            "documents_complete_override": application.documents_complete_override,
            "documents_complete_reason": application.documents_complete_reason,
        }
    )
    can_edit_eligibility = bool(sub_edit.get("eligibility"))
    eligibility_override_form = PlotApplicationEligibilityOverrideForm(
        initial={
            "eligibility_override": application.eligibility_override,
            "eligibility_override_reason": application.eligibility_override_reason,
        }
    )
    incomplete_rejection_form = PlotApplicationIncompleteRejectionForm(
        initial={"incomplete_rejection_reason": application.incomplete_rejection_reason}
    )
    return {
        "outcome": outcome,
        "application_stages": application_stage_steps(outcome["application_stage"]),
        "list_decisions": application_list_decisions(application),
        "can_override_eligibility": can_edit_eligibility and _can_override_eligibility(application),
        "eligibility_override_form": eligibility_override_form,
        "can_reject_incomplete": can_edit_eligibility and _can_reject_incomplete(outcome),
        "can_revoke_incomplete_rejection": can_edit_eligibility and outcome["is_rejected_incomplete"],
        "incomplete_rejection_form": incomplete_rejection_form,
        "readonly_document_groups": readonly_document_groups,
        "attached_count": len(attached & set(DOCUMENT_LABELS)),
        "required_documents_count": len(req_list),
        "satisfied_required_count": satisfied_required_count,
        "missing_documents_count": len(outcome["missing_documents"]),
        "can_edit_documents": can_edit_documents,
        "documents_completeness_form": documents_completeness_form,
        "delete_refusal": delete_refusal(application),
        **_email_context(request, application),
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
            code = choice.data["value"]
            if code not in visible_documents:
                choice.data["attrs"]["disabled"] = True
            choice.note = forms.document_notes.get(code, "")
        group_visible = any(choice.data["value"] in visible_documents for choice in choices)
        document_groups.append((title, choices, group_visible))
    attached_set = set(main["attached_documents"].value() or []) & visible_documents
    req_list = required_documents_for_forms(forms)
    satisfied_count = sum(1 for codes, _ in req_list if attached_set.intersection(codes))
    missing_count = len(req_list) - satisfied_count
    override_checked = bool(main["documents_complete_override"].value())
    is_rejected_incomplete = bool(
        application
        and application.incomplete_rejected
        and application.completeness_result == ApplicationCompleteness.INCOMPLETE
    )
    documents_is_complete = not is_rejected_incomplete and (missing_count == 0 or override_checked)
    missing_completeness_fields = missing_completeness_fields_for_forms(forms)
    missing_required_documents = (
        []
        if (override_checked and not is_rejected_incomplete)
        else [
            (codes[0], label)
            for codes, label in req_list
            if not attached_set.intersection(codes)
        ]
    )
    form_is_complete = (
        not is_rejected_incomplete
        and not missing_completeness_fields
        and documents_is_complete
    )
    sub_view = plot_application_subsection_map(request.user, VIEW)
    sub_edit = plot_application_subsection_map(request.user, EDIT)
    actions_ctx = _application_actions_context(request, application, sub_view, sub_edit)
    return render(
        request,
        "plot_applications/form.html",
        {
            **actions_ctx,
            "forms": forms,
            "form": main,
            "application": application,
            "is_create": application is None,
            "income_parameters": income_params,
            "visible_documents": visible_documents,
            "document_groups": document_groups,
            "documents_required_count": len(req_list),
            "documents_attached_count": satisfied_count,
            "documents_missing_count": missing_count,
            "documents_is_complete": documents_is_complete,
            "missing_completeness_fields": missing_completeness_fields,
            "missing_required_documents": missing_required_documents,
            "form_is_complete": form_is_complete,
            "sub_view": sub_view,
            "sub_edit": sub_edit,
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


def _submission_closed_message(cycle) -> str:
    """Ενότ. 4, 5: μετά τη λήξη της προθεσμίας υποβολής οι αιτήσεις της γνωστοποίησης κλειδώνουν."""
    if cycle is None or not cycle.is_published or cycle.submission_open():
        return ""
    if cycle.submission_closed_early:
        return "Η υποβολή αιτήσεων για τη γνωστοποίηση έκλεισε πρόωρα· οι αιτήσεις δεν προστίθενται ούτε αλλάζουν."
    end = formats.date_format(cycle.submission_end_date, "d/m/Y") if cycle.submission_end_date else ""
    return (
        f"Η προθεσμία υποβολής αιτήσεων της γνωστοποίησης έληξε ({end})· "
        "οι αιτήσεις δεν προστίθενται ούτε αλλάζουν."
    )


@access_required(FUNCTION, CREATE)
def plot_application_create(request):
    if request.method == "POST":
        forms = ApplicationForms(request.POST)
        closed = forms.is_valid() and _submission_closed_message(forms.main.cleaned_data.get("announcement"))
        if closed:
            forms.main.add_error("announcement", closed)
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
        announcement_id = request.GET.get("announcement") or request.GET.get("announcement_id")
        community_id = request.GET.get("community")
        if announcement_id and announcement_id.isdigit():
            forms.main.initial["announcement"] = int(announcement_id)
        elif community_id and community_id.isdigit():
            from cases.models import SubmissionCycle

            cycle = (
                SubmissionCycle.objects.filter(plots__community_id=int(community_id))
                .exclude(stage=SubmissionCycle.Stage.CLOSED)
                .order_by("-published_at", "-announcement_date", "-pk")
                .first()
                or SubmissionCycle.objects.filter(plots__community_id=int(community_id))
                .order_by("-published_at", "-announcement_date", "-pk")
                .first()
            )
            if cycle is not None:
                forms.main.initial["announcement"] = cycle.pk
    return _render_form(request, forms)


@access_required(FUNCTION, EDIT)
def plot_application_edit(request, pk):
    application = get_object_or_404(PlotApplication, pk=pk)
    closed = application.submission_locked and _submission_closed_message(application.announcement)
    if closed:
        messages.error(request, closed)
        if has_access(request.user, FUNCTION, VIEW):
            return redirect("plot_applications:detail", pk=application.pk)
        return redirect("plot_applications:list")
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
            "announcement", "applicant", "spouse"
        ).prefetch_related(
            "announcement__plots__community",
            "parties",
            "children",
            "incomes",
            "allocations",
            "ranking_entries__ranking_list",
            "objections",
            "pending_requirements",
        ),
        pk=pk,
    )
    sub_view = plot_application_subsection_map(request.user, VIEW)
    sub_edit = plot_application_subsection_map(request.user, EDIT)
    actions_ctx = _application_actions_context(request, application, sub_view, sub_edit)
    outcome = actions_ctx["outcome"]
    persons = [p for p in (application.applicant, application.spouse) if p]
    other_applications = (
        PlotApplication.objects.filter(Q(applicant__in=persons) | Q(spouse__in=persons))
        .exclude(pk=application.pk)
        .select_related("announcement", "applicant", "spouse")
        .prefetch_related("announcement__plots__community")
        .order_by(F("preference_order").asc(nulls_last=True), "submitted_on", "id")
    )
    return render(
        request,
        "plot_applications/detail.html",
        {
            **actions_ctx,
            "application": application,
            "is_create": False,
            "other_applications": other_applications,
            "document_groups": actions_ctx["readonly_document_groups"],
            "documents_required_count": actions_ctx["required_documents_count"],
            "documents_attached_count": actions_ctx["satisfied_required_count"],
            "documents_missing_count": actions_ctx["missing_documents_count"],
            "documents_is_complete": outcome["documents_completeness"]
            == DocumentsCompleteness.COMPLETE,
            "sub_view": sub_view,
            "sub_edit": sub_edit,
        },
    )


@access_required(FUNCTION)
def plot_application_eligibility_report_pdf(request, pk):
    """Έκθεση ελέγχου κριτηρίων και επιλεξιμότητας αίτησης παραχώρησης οικοπέδου (PDF)."""
    if not plot_application_subsection_map(request.user, VIEW).get("eligibility"):
        raise PermissionDenied("Δεν έχετε πρόσβαση στον έλεγχο κριτηρίων της αίτησης.")
    from plot_applications.eligibility_report_pdf import (
        eligibility_report_pdf_filename,
        render_eligibility_report_pdf,
    )

    application = get_object_or_404(
        PlotApplication.objects.select_related(
            "announcement", "applicant", "spouse"
        ).prefetch_related(
            "announcement__plots__community",
            "parties",
            "children",
            "incomes",
            "allocations",
            "ranking_entries__ranking_list",
        ),
        pk=pk,
    )
    pdf_bytes = render_eligibility_report_pdf(application)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=eligibility_report_pdf_filename(application)
    )
    return response


@access_required(FUNCTION)
def plot_application_history(request, pk):
    """Χρονολόγιο (timeline) των αλλαγών της αίτησης παραχώρησης οικοπέδου (§Β.1.3)."""
    if not plot_application_subsection_map(request.user, VIEW).get("change_history"):
        raise PermissionDenied("Δεν έχετε πρόσβαση στο ιστορικό αλλαγών της αίτησης.")
    application = get_object_or_404(PlotApplication, pk=pk)
    timeline_events = build_timeline(plot_application_history_entries(application))
    timeline_html = render_to_string(
        "core/_history_timeline.html",
        {"timeline_events": timeline_events},
        request=request,
    )
    return JsonResponse({"ok": True, "timeline_html": timeline_html})


@access_required(FUNCTION, EDIT)
def plot_application_documents_completeness_save(request, pk):
    """Ενημέρωση του χειροκίνητου χαρακτηρισμού ολοκλήρωσης δικαιολογητικών και της αιτιολογίας."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    editable_subsections = editable_plot_application_subsections(request.user)
    if editable_subsections is not None and "documents" not in editable_subsections:
        raise PermissionDenied("Δεν έχετε δικαίωμα επεξεργασίας των δικαιολογητικών.")
    application = get_object_or_404(
        PlotApplication.objects.select_related(
            "announcement", "applicant", "spouse"
        ).prefetch_related("announcement__plots__community", "parties", "children", "incomes"),
        pk=pk,
    )
    form = PlotApplicationDocumentsCompletenessForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            application.documents_complete_override = bool(
                form.cleaned_data.get("documents_complete_override")
            )
            application.documents_complete_reason = form.cleaned_data.get("documents_complete_reason") or ""
            apply_evaluation(application)
        messages.success(
            request,
            "Η κατάσταση πληρότητας δικαιολογητικών της αίτησης ενημερώθηκε.",
        )
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return _redirect_after_application_action(request, application)


def _can_override_eligibility(application: PlotApplication) -> bool:
    """Η χειροκίνητη αλλαγή γίνεται στην πλήρη αίτηση πριν από τον Τελικό Κατάλογο: από την Επιτροπή
    Εξέτασης Αιτήσεων (στάδια 2–3, Ενότ. 6) ή την Επιτροπή Εξέτασης Ενστάσεων (στάδιο ενστάσεων, Ενότ. 7)."""
    return application.application_stage in PRIORITIZATION_STAGES


@access_required(FUNCTION, EDIT)
def plot_application_eligibility_override_save(request, pk):
    """Χειροκίνητη αλλαγή του αποτελέσματος του λογισμικού (δικαιούχος / μη δικαιούχος) με αιτιολογία (Ενότ. 6)."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if not plot_application_subsection_map(request.user, EDIT).get("eligibility"):
        raise PermissionDenied("Δεν έχετε δικαίωμα αλλαγής του αποτελέσματος επιλεξιμότητας.")
    application = get_object_or_404(
        PlotApplication.objects.select_related(
            "announcement", "applicant", "spouse"
        ).prefetch_related("announcement__plots__community", "parties", "children", "incomes", "objections"),
        pk=pk,
    )
    if not _can_override_eligibility(application):
        messages.error(
            request,
            "Το αποτέλεσμα επιλεξιμότητας αλλάζει μόνο σε πλήρη αίτηση που δεν έχει ολοκληρωθεί.",
        )
        return _redirect_after_application_action(request, application)
    if application.application_stage in (
        ApplicationStage.OBJECTIONS,
        ApplicationStage.OBJECTIONS_COMMITTEE,
    ) and not application.has_registered_objection:
        messages.error(
            request,
            "Στην Επιτροπή Εξέτασης Ενστάσεων επιτρέπονται αλλαγές μόνο σε αιτήσεις για τις οποίες έχει υποβληθεί ένσταση (Ενότ. 7).",
        )
        return _redirect_after_application_action(request, application)
    if application.announcement_id:
        locked_reason = community_lists(application.announcement).list_edit_locked_reason
        if locked_reason:
            messages.error(request, locked_reason)
            return _redirect_after_application_action(request, application)
    form = PlotApplicationEligibilityOverrideForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            application.eligibility_override = form.cleaned_data["eligibility_override"]
            application.eligibility_override_reason = form.cleaned_data["eligibility_override_reason"]
            apply_evaluation(application)
        messages.success(request, "Το αποτέλεσμα επιλεξιμότητας της αίτησης ενημερώθηκε.")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return _redirect_after_application_action(request, application)


OFFICER_REJECTION_STAGES = (
    ApplicationStage.COLLECTION,
    ApplicationStage.EXAMINATION,
    ApplicationStage.PRIORITIZATION,
)


def _can_reject_incomplete(outcome: dict) -> bool:
    """Ο λειτουργός απορρίπτει αίτηση σε αρχικό στάδιο, πριν από τον Προκαταρκτικό Κατάλογο (Ενότ. 5(β), 20)·
    μετά, η απόρριψη των μη δικαιούχων γίνεται από την Επιτροπή με τους καταλόγους (Ενότ. 6, 7)."""
    return (
        not outcome["is_rejected_incomplete"]
        and outcome["application_stage"] in OFFICER_REJECTION_STAGES
    )


def _incomplete_decision_application(request, pk) -> PlotApplication:
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if not plot_application_subsection_map(request.user, EDIT).get("eligibility"):
        raise PermissionDenied("Δεν έχετε δικαίωμα απόρριψης αίτησης.")
    return get_object_or_404(
        PlotApplication.objects.select_related(
            "announcement", "applicant", "spouse"
        ).prefetch_related("announcement__plots__community", "parties", "children", "incomes"),
        pk=pk,
    )


@access_required(FUNCTION, EDIT)
def plot_application_incomplete_reject(request, pk):
    """Απόρριψη αίτησης από τον λειτουργό με υποχρεωτικό λόγο."""
    application = _incomplete_decision_application(request, pk)
    outcome = evaluate(application)
    if not _can_reject_incomplete(outcome):
        messages.error(
            request,
            "Η αίτηση έχει ήδη απορριφθεί."
            if outcome["is_rejected_incomplete"]
            else "Μετά την έκδοση του Προκαταρκτικού Καταλόγου η αίτηση δεν απορρίπτεται από τον "
            "λειτουργό· την απόφαση παίρνει η Επιτροπή (Ενότ. 6, 7).",
        )
        return _redirect_after_application_action(request, application)
    form = PlotApplicationIncompleteRejectionForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            application.incomplete_rejected = True
            application.incomplete_rejection_reason = form.cleaned_data["incomplete_rejection_reason"]
            application.incomplete_rejected_on = timezone.localdate()
            apply_evaluation(application)
        messages.success(request, "Η αίτηση απορρίφθηκε.")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return _redirect_after_application_action(request, application)


@access_required(FUNCTION, EDIT)
def plot_application_incomplete_reject_revoke(request, pk):
    """Ανάκληση της απόρριψης της αίτησης."""
    application = _incomplete_decision_application(request, pk)
    if not application.incomplete_rejected:
        messages.error(request, "Η αίτηση δεν έχει απορριφθεί.")
        return _redirect_after_application_action(request, application)
    with transaction.atomic():
        application.incomplete_rejected = False
        application.incomplete_rejection_reason = ""
        application.incomplete_rejected_on = None
        apply_evaluation(application)
    messages.success(request, "Η απόρριψη της αίτησης ανακλήθηκε.")
    return _redirect_after_application_action(request, application)


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
        PlotApplication.objects.select_related("announcement", "applicant", "spouse").prefetch_related(
            "announcement__plots__community"
        ),
        pk=pk,
    )

    if any(f"document_note_{code}" in request.POST for code in DOCUMENT_LABELS):
        updated_notes = dict(
            application.document_notes if isinstance(application.document_notes, dict) else {}
        )
        notes_changed = False
        for code in DOCUMENT_LABELS:
            key = f"document_note_{code}"
            if key not in request.POST:
                continue
            val = (request.POST.get(key) or "").strip()
            if val:
                if updated_notes.get(code) != val:
                    updated_notes[code] = val
                    notes_changed = True
            elif code in updated_notes:
                updated_notes.pop(code, None)
                notes_changed = True
        if notes_changed:
            application.document_notes = updated_notes
            application.save()

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
                user=request.user,
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
        or has_access(request.user, "announcements", VIEW)
        or has_access(request.user, "announcement_committee", VIEW)
        or has_access(request.user, "announcement_objections", VIEW)
        or has_access(request.user, "announcement_lottery", VIEW)
        or has_access(request.user, "announcement_agreements", VIEW)
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
            "sender": communication.sender_label,
            "stage_label": communication.stage_label,
            "subject": communication.subject,
            "body": communication.body,
            "check_label": application.protocol_number,
            "status": communication.status,
            "status_display": CommunicationStatus.label(communication.status),
            "sent_at": sent_at,
        }
    )


def _plot_application_sort_key(app: PlotApplication, sort_col: str):
    if sort_col == "protocol_number":
        return (app.protocol_number or "").lower()
    if sort_col == "submitted_on":
        return app.submitted_on.isoformat() if app.submitted_on else ""
    if sort_col == "community":
        return (app.community.name if app.community_id else "").lower()
    if sort_col == "applicant":
        return f"{app.applicant.last_name} {app.applicant.first_name} {app.applicant.identity_number}".lower()
    if sort_col == "spouse":
        if not app.spouse_id:
            return ""
        return f"{app.spouse.last_name} {app.spouse.first_name} {app.spouse.identity_number}".lower()
    if sort_col == "family_status":
        return (app.get_family_status_display() or "").lower()
    if sort_col == "children":
        return int(app.recognized_children_count or 0)
    if sort_col == "stage":
        return (app.application_stage_label or "").lower()
    if sort_col == "completeness":
        return (app.get_completeness_result_display() or "").lower()
    if sort_col == "documents_completeness":
        return (app.get_documents_completeness_display() or "").lower()
    if sort_col == "eligibility":
        return (app.eligibility_label or "").lower()
    if sort_col == "beneficiary":
        return (app.beneficiary_label or "").lower()
    if sort_col == "plot_allocation":
        return (app.plot_allocation_label or "").lower()
    return app.pk or 0


@login_required
def plot_application_list(request):
    from cases.models import SubmissionCycle

    if not has_any_access(request.user, FUNCTION, FUNCTIONS_BY_CODE[FUNCTION].actions):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
    applications = PlotApplication.objects.select_related(
        "announcement", "applicant", "spouse"
    ).prefetch_related("announcement__plots__community", "pending_requirements", "objections")
    announcement_id = request.GET.get("announcement_id") or ""
    community_id = request.GET.get("community_id") or ""
    stage = request.GET.get("stage") or ""
    beneficiary = request.GET.get("beneficiary") or ""
    plot_allocation = request.GET.get("plot_allocation") or ""
    result = request.GET.get("result") or ""
    completeness = request.GET.get("completeness") or ""
    documents_completeness = request.GET.get("documents_completeness") or ""
    q = (request.GET.get("q") or "").strip()
    if announcement_id and announcement_id.isdigit():
        applications = applications.filter(announcement_id=int(announcement_id))
    if community_id and community_id.isdigit():
        applications = applications.filter(
            announcement__plots__community_id=int(community_id)
        ).distinct()
    if stage in ApplicationStage.values:
        applications = applications.filter(application_stage=stage)
    # Η απόρριψη από τον λειτουργό δεν έχει Επιλεξιμότητα / Δικαιούχο / Παραχώρηση οικοπέδου.
    officer_rejected = Q(incomplete_rejected=True) | Q(application_stage=ApplicationStage.REJECTED)
    if beneficiary in ("pass", "yes", "True", "1"):
        applications = applications.filter(
            completeness_result=ApplicationCompleteness.COMPLETE,
            documents_completeness=DocumentsCompleteness.COMPLETE,
            eligibility_result=EligibilityResult.PASS,
        ).exclude(officer_rejected)
        beneficiary = "pass"
    elif beneficiary in ("fail", "no", "False", "0"):
        applications = applications.filter(eligibility_result=EligibilityResult.FAIL).exclude(
            officer_rejected
        )
        beneficiary = "fail"
    elif beneficiary == "pending":
        applications = (
            applications.filter(eligibility_result=EligibilityResult.PASS)
            .exclude(officer_rejected)
            .exclude(
                completeness_result=ApplicationCompleteness.COMPLETE,
                documents_completeness=DocumentsCompleteness.COMPLETE,
            )
        )
    if plot_allocation in PlotAllocationStatus.values:
        applications = (
            applications.filter(plot_allocation_status=plot_allocation)
            .exclude(eligibility_result=EligibilityResult.PENDING)
            .exclude(officer_rejected)
        )
    if result in EligibilityResult.values:
        applications = applications.filter(eligibility_result=result).exclude(officer_rejected)
    if completeness in ApplicationCompleteness.values:
        applications = applications.filter(completeness_result=completeness)
    if documents_completeness in DocumentsCompleteness.values:
        applications = applications.filter(documents_completeness=documents_completeness)
    if q:
        applications = applications.filter(
            Q(protocol_number__icontains=q)
            | Q(applicant__identity_number__icontains=q)
            | Q(spouse__identity_number__icontains=q)
            | Q(applicant__last_name__icontains=q)
            | Q(spouse__last_name__icontains=q)
        )
    sort_col = (request.GET.get("sort") or "").strip()
    sort_dir = "desc" if (request.GET.get("dir") or "").strip() == "desc" else "asc"
    if sort_col not in PLOT_APPLICATION_GRID_COLUMN_CODES:
        sort_col = ""
        sort_dir = "asc"
    if sort_col:
        applications = sorted(
            applications,
            key=lambda app: _plot_application_sort_key(app, sort_col),
            reverse=(sort_dir == "desc"),
        )
    visible_columns = get_plot_application_grid_columns()
    locked_columns_setting = get_plot_application_grid_locked_columns()
    locked_columns_count = min(locked_columns_setting, len(visible_columns))
    grid_columns = [
        {
            "key": code,
            "label": PLOT_APPLICATION_GRID_COLUMN_LABELS[code],
            "position": idx,
            "is_locked": idx <= locked_columns_count,
            "is_locked_last": locked_columns_count > 0 and idx == locked_columns_count,
        }
        for idx, code in enumerate(visible_columns, start=1)
    ]
    return render(
        request,
        "plot_applications/list.html",
        {
            "applications": applications,
            "announcements": SubmissionCycle.objects.prefetch_related("plots__community").order_by(
                "-announcement_date", "-id"
            ),
            "communities": Community.objects.filter(is_active=True).order_by("name"),
            "stage_choices": application_stage_choices(),
            "plot_allocation_choices": PlotAllocationStatus.choices,
            "results": EligibilityResult.choices,
            "completeness_choices": ApplicationCompleteness.choices,
            "documents_completeness_choices": DocumentsCompleteness.choices,
            "announcement_id": announcement_id,
            "community_id": community_id,
            "stage": stage,
            "beneficiary": beneficiary,
            "plot_allocation": plot_allocation,
            "result": result,
            "completeness": completeness,
            "documents_completeness": documents_completeness,
            "q": q,
            "grid_columns": grid_columns,
            "visible_columns": visible_columns,
            "locked_columns_count": locked_columns_count,
            "grid_colspan": len(grid_columns) + 1,
            "sort_col": sort_col,
            "sort_dir": sort_dir,
        },
    )


def _prioritization_communities():
    """Κοινότητες με πλήρεις αιτήσεις στον κατάλογο ή με εκδομένο Τελικό Κατάλογο, για την επιλογή καταλόγου."""
    return (
        Community.objects.filter(
            plots__submission_cycles__applications__application_stage__in=(
                *PRIORITIZATION_STAGES,
                ApplicationStage.LOTTERY,
                ApplicationStage.AGREEMENT,
                ApplicationStage.COMPLETED,
                ApplicationStage.COMMITTEE_REJECTED,
                ApplicationStage.FORFEITED,
            )
        )
        .distinct()
        .order_by("name")
    )


def _community_or_404(raw) -> Community:
    raw = str(raw or "")
    if not raw.isdigit():
        raise Http404("Δεν βρέθηκε η Κοινότητα.")
    return get_object_or_404(Community, pk=int(raw))


def _selected_community(request, communities):
    raw = request.GET.get("community_id") or ""
    if raw:
        return _community_or_404(raw)
    return communities[0] if communities else None


@access_required("plot_prioritization")
def plot_application_prioritization(request):
    """Κατάλογος προτεραιοποίησης όλων των πλήρων ανοικτών αιτήσεων μιας Κοινότητας (Ενότ. 6, 11)."""
    communities = list(_prioritization_communities())
    community = _selected_community(request, communities)
    if community is not None and community not in communities:
        communities = sorted([*communities, community], key=lambda item: item.name)
    lists = community_lists(community) if community else None
    is_final = bool(lists and lists.phase == PHASE_FINAL)
    list_view = ""
    changes = []
    if lists is not None and lists.preliminary is not None:
        list_view = request.GET.get("list")
        if list_view not in LIST_VIEWS:
            list_view = LIST_VIEW_FINAL
        changes = list_changes(lists)
    if list_view == LIST_VIEW_PRELIMINARY:
        prioritization = snapshot_listing(lists.preliminary)
    elif lists is not None and lists.preliminary is not None:
        prioritization = final_listing(lists)
    else:
        prioritization = build_prioritization_list(community) if community else None
    can_edit_lists = has_access(request.user, "plot_prioritization", EDIT)
    list_edit_locked_reason = lists.list_edit_locked_reason if lists else ""
    can_reorder = (
        can_edit_lists
        and not is_final
        and not list_edit_locked_reason
        and list_view in ("", LIST_VIEW_FINAL)
    )
    objections = (
        list(
            Objection.objects.filter(application__announcement=lists.cycle)
            .select_related("application", "application__applicant", "preliminary_entry")
            .order_by("application__protocol_number", "submitted_on", "id")
        )
        if lists is not None and lists.cycle is not None and lists.preliminary is not None
        else []
    )
    can_view_app_history = bool(
        plot_application_subsection_map(request.user, VIEW).get("change_history")
    )
    blockers = list(blocking_applications(community)) if community and not is_final else []
    return render(
        request,
        "plot_applications/prioritization.html",
        {
            "communities": communities,
            "community": community,
            "prioritization": prioritization,
            "lists": lists,
            "phase": lists.phase if lists else PHASE_COMMITTEE,
            "phases": {
                "committee": PHASE_COMMITTEE,
                "objections": PHASE_OBJECTIONS,
                "final": PHASE_FINAL,
            },
            "objections_open": bool(lists and lists.objections_open()),
            "is_final": is_final,
            "list_view": list_view,
            "list_views": {
                "preliminary": LIST_VIEW_PRELIMINARY,
                "final": LIST_VIEW_FINAL,
                "changes": LIST_VIEW_CHANGES,
            },
            "changes": changes,
            "objections": objections,
            "list_edit_locked_reason": list_edit_locked_reason,
            "blockers": blockers,
            "can_edit_lists": can_edit_lists,
            "can_reorder": can_reorder,
            "movable_beneficiaries": bool(
                can_reorder and prioritization and len(prioritization.beneficiaries) > 1
            ),
            "movable_others": bool(can_reorder and prioritization and len(prioritization.others) > 1),
            "can_export": has_access(request.user, "plot_prioritization", EXPORT),
            "can_view_app_history": can_view_app_history,
            "groups": {"beneficiaries": BENEFICIARIES, "others": OTHERS},
        },
    )


def _prioritization_redirect(community):
    return redirect(f"{reverse('plot_applications:prioritization')}?community_id={community.pk}")


def _list_action(request, action, success_message):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    community = _community_or_404(request.POST.get("community_id"))
    try:
        action(community)
    except BeneficiaryListError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, success_message)
    return _prioritization_redirect(community)


@access_required("plot_prioritization", EDIT)
def plot_application_preliminary_list_issue(request):
    """Έκδοση του Προκαταρκτικού Καταλόγου Δικαιούχων από την Επιτροπή Εξέτασης Αιτήσεων (Ενότ. 6)."""
    return _list_action(
        request,
        lambda community: issue_preliminary_list(community, request.user),
        "Εκδόθηκε ο Προκαταρκτικός Κατάλογος Δικαιούχων· ξεκίνησε η περίοδος ενστάσεων (Ενότ. 7).",
    )


@access_required("plot_prioritization", EDIT)
def plot_application_preliminary_list_revoke(request):
    return _list_action(
        request,
        revoke_preliminary_list,
        "Ο Προκαταρκτικός Κατάλογος ανακλήθηκε· οι αιτήσεις επανήλθαν στο στάδιο «Επιλογή και προτεραιοποίηση».",
    )


@access_required("plot_prioritization", EDIT)
def plot_application_final_list_issue(request):
    """Έκδοση του Τελικού Καταλόγου Δικαιούχων μετά την περίοδο ενστάσεων (Ενότ. 7, 8)."""
    return _list_action(
        request,
        lambda community: issue_final_list(community, request.user),
        "Εκδόθηκε ο Τελικός Κατάλογος Δικαιούχων.",
    )


@access_required("plot_prioritization", EDIT)
def plot_application_final_list_revoke(request):
    return _list_action(
        request,
        revoke_final_list,
        "Ο Τελικός Κατάλογος ανακλήθηκε· οι αιτήσεις επανήλθαν στην περίοδο ενστάσεων.",
    )


@access_required("plot_prioritization")
def plot_application_prioritization_history(request):
    """Χρονολόγιο (timeline) των αλλαγών στον πίνακα προτεραιοποίησης της Κοινότητας (§Β.1.3)."""
    community = _community_or_404(request.GET.get("community_id"))
    timeline_events = build_timeline(prioritization_history_entries(community))
    timeline_html = render_to_string(
        "core/_history_timeline.html",
        {"timeline_events": timeline_events},
        request=request,
    )
    return JsonResponse({"ok": True, "timeline_html": timeline_html})


@access_required("plot_prioritization", EDIT)
def plot_application_prioritization_reorder(request):
    """Αποθήκευση της σειράς μιας ομάδας (δικαιούχοι / μη δικαιούχοι) μετά από drag and drop."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        payload = {}
    group = payload.get("group")
    if group not in GROUPS:
        return JsonResponse({"ok": False, "message": "Μη έγκυρο αίτημα αλλαγής σειράς."}, status=400)
    community = _community_or_404(payload.get("community_id"))
    requested_ids = []
    for item in payload.get("order") or []:
        try:
            requested_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    try:
        ordered = save_manual_order(community, group, requested_ids)
    except BeneficiaryListError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    has_manual_order = build_prioritization_list(community).has_manual_order
    return JsonResponse(
        {
            "ok": True,
            "order": [app.pk for app in ordered],
            "has_manual_order": has_manual_order,
        }
    )


@access_required("plot_prioritization", EDIT)
def plot_application_prioritization_reset(request):
    """Επαναφορά του καταλόγου της Κοινότητας στη σειρά του λογισμικού."""
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    community = _community_or_404(request.POST.get("community_id"))
    try:
        reset_manual_order(community)
    except BeneficiaryListError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Ο κατάλογος επανήλθε στη σειρά του λογισμικού (Ενότ. 11).")
    return _prioritization_redirect(community)


@access_required("plot_prioritization", EXPORT)
def plot_application_prioritization_report_pdf(request):
    """Εξαγωγή του καταλόγου προτεραιοποίησης της Κοινότητας σε PDF (A4 landscape)."""
    from plot_applications.prioritization_report_pdf import (
        prioritization_report_pdf_filename,
        render_prioritization_report_pdf,
    )

    community = _community_or_404(request.GET.get("community_id"))
    list_view = request.GET.get("list") or ""
    response = HttpResponse(
        render_prioritization_report_pdf(community, list_view), content_type="application/pdf"
    )
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=prioritization_report_pdf_filename(community, list_view)
    )
    return response
