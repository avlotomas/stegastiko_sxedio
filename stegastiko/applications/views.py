from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from applications.forms import ApplicationForm, DependentChildFormSet
from applications.models import Application, EligibilityCheck
from applications.rules import evaluate_eligibility
from applications.import_reader import ParsedImport, parse_import_workbook
from applications.import_services import save_import, validate_import
from applications.person_identity import compare_person_with_payload, person_payload_from_form_prefix
from applications.services import (
    application_form_initial,
    ensure_person,
    generate_folder_number,
    previous_applications_for_identity,
    upsert_eligibility_checks,
)
from cases.models import SubmissionCycle
from core.function_catalog import CREATE, EDIT, IMPORT
from core.models import Community
from core.permissions import access_required, has_access, has_any_access


def _person_to_json(person):
    return {
        "identity_number": person.identity_number,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "refugee_identity_number": person.refugee_identity_number,
        "citizenship_cypriot": person.citizenship_cypriot,
        "citizenship_repatriated": person.citizenship_repatriated,
        "citizenship_eu": person.citizenship_eu,
        "citizenship_other": person.citizenship_other,
        "date_of_birth": person.date_of_birth.isoformat(),
        "birth_place": person.birth_place,
        "birth_country": person.birth_country,
        "parents_birth_place": person.parents_birth_place,
        "parents_birth_country": person.parents_birth_country,
    }


@access_required("applications")
def application_list(request):
    applications = Application.objects.select_related(
        "submission_cycle", "submission_cycle__community", "person", "person2"
    ).order_by("-submitted_on", "-id")
    communities = Community.objects.filter(is_active=True).order_by("name")
    cycles = SubmissionCycle.objects.select_related("community").order_by("-announcement_date")
    community_id = request.GET.get("community_id") or ""
    cycle_id = request.GET.get("cycle_id") or ""
    q = (request.GET.get("q") or "").strip()
    if community_id:
        applications = applications.filter(submission_cycle__community_id=community_id)
    if cycle_id:
        applications = applications.filter(submission_cycle_id=cycle_id)
    if q:
        applications = applications.filter(folder_number__icontains=q)
    return render(
        request,
        "applications/list.html",
        {
            "applications": applications,
            "communities": communities,
            "cycles": cycles,
            "community_id": str(community_id),
            "cycle_id": str(cycle_id),
            "q": q,
        },
    )


def _save_application_from_form(form, formset, existing: Application | None = None) -> Application:
    p1 = ensure_person(
        form.cleaned_data["person1_identity_number"],
        person_payload_from_form_prefix(form, "person1"),
    )
    p2 = None
    person2_identity = form.cleaned_data.get("person2_identity_number") or ""
    if person2_identity.strip():
        p2 = ensure_person(
            person2_identity.strip(),
            person_payload_from_form_prefix(form, "person2"),
        )

    application = form.save(commit=False)
    if existing:
        application.folder_number = existing.folder_number
    else:
        if application.submission_cycle.published_at is None:
            raise ValidationError("Δεν επιτρέπεται αίτηση πριν τη δημοσίευση του κύκλου υποβολής.")
        application.folder_number = generate_folder_number(application.submission_cycle)

    application.person = p1
    application.person2 = p2
    application.completeness_updated_at = timezone.now()
    application.save()

    formset.instance = application
    formset.save()

    recognized_children = application.dependent_children.filter(is_recognized_dependent=True).count()
    application.recognized_dependent_children_count = recognized_children
    application.declared_children_count = application.dependent_children.count()
    application.family_members_count = 1 + (1 if application.person2_id else 0) + recognized_children

    results, *_ = evaluate_eligibility(application)
    application.save()
    upsert_eligibility_checks(application, results)
    return application


@access_required("applications", CREATE)
def application_create(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST)
        temp_application = Application()
        formset = DependentChildFormSet(request.POST, instance=temp_application, prefix="children")
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    application = _save_application_from_form(form, formset)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0] if exc.messages else str(exc))
            else:
                messages.success(request, "Η αίτηση αποθηκεύτηκε.")
                return redirect("applications:detail", pk=application.pk)
    else:
        form = ApplicationForm()
        formset = DependentChildFormSet(prefix="children")
    return render(
        request,
        "applications/form.html",
        {
            "form": form,
            "formset": formset,
            "is_create": True,
            "application": None,
        },
    )


@access_required("applications", EDIT)
def application_edit(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("person", "person2", "submission_cycle__community"), pk=pk
    )
    if request.method == "POST":
        form = ApplicationForm(request.POST, instance=application)
        formset = DependentChildFormSet(request.POST, instance=application, prefix="children")
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    application = _save_application_from_form(form, formset, existing=application)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0] if exc.messages else str(exc))
            else:
                messages.success(request, "Η αίτηση ενημερώθηκε.")
                return redirect("applications:detail", pk=application.pk)
    else:
        form = ApplicationForm(instance=application, initial=application_form_initial(application))
        formset = DependentChildFormSet(instance=application, prefix="children")
    return render(
        request,
        "applications/form.html",
        {
            "form": form,
            "formset": formset,
            "is_create": False,
            "application": application,
        },
    )


@access_required("applications")
def application_detail(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("person", "person2", "submission_cycle__community"), pk=pk
    )
    checks = application.eligibility_checks.order_by("criterion")
    return render(
        request,
        "applications/detail.html",
        {"application": application, "checks": checks},
    )


def _require_person_check_access(user, *, allow_import=False):
    """Person lookup / compare serve the application form (and the Excel import preview)."""
    allowed = has_any_access(user, "applications", (CREATE, EDIT)) or (
        allow_import and has_access(user, "application_import", IMPORT)
    )
    if not allowed:
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")


@login_required
def person_lookup(request):
    _require_person_check_access(request.user)
    identity = (request.GET.get("identity") or "").strip()
    if not identity:
        return JsonResponse({"found": False})
    person, apps = previous_applications_for_identity(identity)
    if not person:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "person": _person_to_json(person),
            "applications_count": len(apps),
            "latest_prefill": (
                {
                    "family_type": apps[0].family_type,
                    "person1_relationship": apps[0].person1_relationship,
                    "person2_relationship": apps[0].person2_relationship,
                    "person1_residence_community": apps[0].person1_residence_community,
                    "person2_residence_community": apps[0].person2_residence_community,
                    "person1_residence_address": apps[0].person1_residence_address,
                    "person2_residence_address": apps[0].person2_residence_address,
                    "residence_category": apps[0].residence_category,
                    "person1_has_property": apps[0].person1_has_property,
                    "person2_has_property": apps[0].person2_has_property,
                    "person1_non_alienation_clear": apps[0].person1_non_alienation_clear,
                    "person2_non_alienation_clear": apps[0].person2_non_alienation_clear,
                    "person1_previous_aid_clear": apps[0].person1_previous_aid_clear,
                    "person2_previous_aid_clear": apps[0].person2_previous_aid_clear,
                    "person1_income": str(apps[0].person1_income),
                    "person2_income": str(apps[0].person2_income),
                    "children_income": str(apps[0].children_income),
                }
                if apps
                else {}
            ),
            "applications": [
                {
                    "id": item.id,
                    "folder_number": item.folder_number,
                    "submitted_on": item.submitted_on.isoformat(),
                    "community": item.submission_cycle.community.name,
                }
                for item in apps[:10]
            ],
        }
    )


@login_required
def person_compare(request):
    """Compare submitted Person fields (form/import) with stored Person by ΑΔΤ."""
    import json

    _require_person_check_access(request.user, allow_import=True)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    identity = (body.get("identity_number") or "").strip()
    payload = body.get("payload") or {}
    if not identity:
        return JsonResponse({"error": "identity_number required"}, status=400)

    result = compare_person_with_payload(identity, payload)
    return JsonResponse(
        {
            "exists": result.exists,
            "identity_number": result.identity_number,
            "person_id": result.person_id,
            "has_differences": result.has_differences,
            "differences": [
                {
                    "field": d.field,
                    "label": d.label,
                    "stored_value": d.stored_value,
                    "incoming_value": d.incoming_value,
                }
                for d in result.differences
            ],
            "message": (
                "Το ΑΔΤ αντιστοιχεί σε υπάρχον άτομο. "
                + "Τα πεδία "
                + ", ".join(d.label for d in result.differences)
                + " διαφέρουν από την καταχωρημένη εγγραφή."
                if result.exists and result.has_differences
                else ""
            ),
        }
    )


IMPORT_SESSION_KEY = "application_import_payload"


def _parsed_to_session(parsed: ParsedImport) -> dict:
    return {
        "metadata": parsed.metadata,
        "fields": {k: ("" if v is None else v) for k, v in parsed.fields.items()},
        "children": parsed.children,
        "income_rows": parsed.income_rows,
        "supporting_documents": parsed.supporting_documents,
    }


def _parsed_from_session(data: dict) -> ParsedImport:
    return ParsedImport(
        metadata=data.get("metadata") or {},
        fields=data.get("fields") or {},
        children=data.get("children") or [],
        income_rows=data.get("income_rows") or [],
        supporting_documents=data.get("supporting_documents") or [],
    )


@access_required("application_import", IMPORT)
def application_import(request):
    if request.method == "POST" and request.POST.get("action") == "confirm":
        payload = request.session.get(IMPORT_SESSION_KEY)
        if not payload:
            messages.error(request, "Η προεπισκόπηση έληξε. Ανεβάστε ξανά το αρχείο.")
            return redirect("applications:import")
        try:
            parsed = _parsed_from_session(payload)
            application = save_import(parsed)
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            validation = validate_import(parsed)
            return render(
                request,
                "applications/import_preview.html",
                {
                    "parsed": parsed,
                    "validation": validation,
                    "can_save": False,
                },
            )
        del request.session[IMPORT_SESSION_KEY]
        messages.success(request, f"Η αίτηση {application.folder_number} αποθηκεύτηκε.")
        return redirect("applications:detail", pk=application.pk)

    if request.method == "POST":
        upload = request.FILES.get("import_file")
        if not upload:
            messages.error(request, "Επιλέξτε αρχείο .xlsx.")
            return render(request, "applications/import.html")
        try:
            parsed = parse_import_workbook(upload)
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            return render(request, "applications/import.html")
        validation = validate_import(parsed)
        request.session[IMPORT_SESSION_KEY] = _parsed_to_session(parsed)
        return render(
            request,
            "applications/import_preview.html",
            {
                "parsed": parsed,
                "validation": validation,
                "can_save": not validation.errors,
            },
        )

    return render(request, "applications/import.html")
