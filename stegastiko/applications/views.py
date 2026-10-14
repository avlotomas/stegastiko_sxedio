from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from applications.forms import ApplicationForm, DependentChildFormSet
from applications.models import Application, EligibilityCheck
from applications.rules import evaluate_eligibility
from applications.import_reader import MAX_IMPORT_FILE_SIZE, ParsedImport, parse_import_workbook
from applications.import_services import save_import, validate_import
from applications.person_identity import compare_person_with_payload, person_payload_from_form_prefix
from applications.services import (
    application_form_initial,
    application_prefill,
    ensure_person,
    previous_applications_for_identity,
    save_with_new_folder_number,
    search_persons,
    upsert_eligibility_checks,
)
from cases.models import SubmissionCycle
from core.function_catalog import CREATE, EDIT, IMPORT
from core.models import Community
from core.permissions import access_required, has_access, has_any_access


CONCURRENT_SAVE_MESSAGE = (
    "Η αποθήκευση δεν ολοκληρώθηκε λόγω ταυτόχρονης καταχώρισης. Δοκιμάστε ξανά."
)


def _person_to_json(person):
    return {
        "identity_number": person.identity_number,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "date_of_birth": person.date_of_birth.isoformat(),
        "birth_place": person.birth_place,
        "birth_country": person.birth_country,
        "parents_birth_place": person.parents_birth_place,
        "parents_birth_country": person.parents_birth_country,
    }


def _application_summary_json(application, person):
    is_person1 = application.person_id == person.id
    partner = application.person2 if is_person1 else application.person
    return {
        "id": application.id,
        "url": reverse("applications:detail", args=[application.id]),
        "folder_number": application.folder_number,
        "submitted_on": application.submitted_on.isoformat(),
        "community": application.community.name,
        "role": "Πρόσωπο 1" if is_person1 else "Πρόσωπο 2",
        "partner": f"{partner.first_name} {partner.last_name}" if partner else "",
        "family_type": application.get_family_type_display(),
        "children_count": application.declared_children_count,
    }


@access_required("applications")
def application_list(request):
    applications = Application.objects.select_related("community", "person", "person2").order_by(
        "-submitted_on", "-id"
    )
    communities = Community.objects.filter(is_active=True).order_by("name")
    community_id = request.GET.get("community_id") or ""
    q = (request.GET.get("q") or "").strip()
    if community_id:
        applications = applications.filter(community_id=community_id)
    if q:
        applications = applications.filter(
            Q(folder_number__icontains=q)
            | Q(person__identity_number__icontains=q)
            | Q(person2__identity_number__icontains=q)
            | Q(person__last_name__icontains=q)
            | Q(person2__last_name__icontains=q)
        )
    return render(
        request,
        "applications/list.html",
        {
            "applications": applications,
            "communities": communities,
            "community_id": str(community_id),
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
    application.person = p1
    application.person2 = p2
    application.completeness_updated_at = timezone.now()
    if existing:
        # The form rejects community changes on edit (10.1.1); keep the issued folder number.
        stored_community_id = (
            Application.objects.filter(pk=existing.pk).values_list("community_id", flat=True).first()
        )
        if application.community_id != stored_community_id:
            raise ValidationError("Η Κοινότητα δεν μπορεί να αλλάξει μετά τη δημιουργία της αίτησης.")
        application.folder_number = existing.folder_number
        application.save()
    else:
        if not SubmissionCycle.for_community(application.community).exists():
            raise ValidationError("Δεν επιτρέπεται αίτηση πριν την έκδοση Γνωστοποίησης για την Κοινότητα (Ενότ. 4).")
        save_with_new_folder_number(application, application.community)

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


def _render_form(request, form, formset, application: Application | None):
    return render(
        request,
        "applications/form.html",
        {
            "form": form,
            "formset": formset,
            "is_create": application is None,
            "application": application,
            "person_form_config": {
                "searchUrl": reverse("applications:person_search"),
                "lookupUrl": reverse("applications:person_lookup"),
                "applicationId": application.pk if application else None,
                "isCreate": application is None,
            },
        },
    )


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
            except IntegrityError:
                form.add_error(None, CONCURRENT_SAVE_MESSAGE)
            else:
                messages.success(request, "Η αίτηση αποθηκεύτηκε.")
                return redirect("applications:detail", pk=application.pk)
    else:
        form = ApplicationForm()
        formset = DependentChildFormSet(prefix="children")
    return _render_form(request, form, formset, None)


@access_required("applications", EDIT)
def application_edit(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("person", "person2", "community"), pk=pk
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
            except IntegrityError:
                form.add_error(None, CONCURRENT_SAVE_MESSAGE)
            else:
                messages.success(request, "Η αίτηση ενημερώθηκε.")
                return redirect("applications:detail", pk=application.pk)
    else:
        form = ApplicationForm(instance=application, initial=application_form_initial(application))
        formset = DependentChildFormSet(instance=application, prefix="children")
    return _render_form(request, form, formset, application)


@access_required("applications")
def application_detail(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("person", "person2", "community"), pk=pk
    )
    checks = application.eligibility_checks.order_by("criterion")
    persons = [person for person in (application.person, application.person2) if person]
    other_applications = (
        Application.objects.filter(Q(person__in=persons) | Q(person2__in=persons))
        .exclude(pk=application.pk)
        .select_related("community", "person", "person2")
        .order_by("-submitted_on", "-id")
    )
    return render(
        request,
        "applications/detail.html",
        {"application": application, "checks": checks, "other_applications": other_applications},
    )


def _require_person_check_access(user, *, allow_import=False):
    """Person lookup / compare serve the application form (and the Excel import preview)."""
    allowed = has_any_access(user, "applications", (CREATE, EDIT)) or (
        allow_import and has_access(user, "application_import", IMPORT)
    )
    if not allowed:
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")


@login_required
def person_search(request):
    """Suggestions while typing an ΑΔΤ (or name) on the application form."""
    _require_person_check_access(request.user)
    persons = search_persons(request.GET.get("q"))
    return JsonResponse(
        {
            "results": [
                {
                    "identity_number": person.identity_number,
                    "label": f"{person.identity_number} — {person.first_name} {person.last_name} "
                    f"({person.date_of_birth.isoformat()})",
                }
                for person in persons
            ]
        }
    )


@login_required
def person_lookup(request):
    """Existing Person by exact ΑΔΤ: fixed fields, previous applications and a prefill.

    The prefill comes from the latest application, or from `source` (an application id of
    that person) when the clerk picks a specific one. `prefix` is the form slot being filled.
    """
    _require_person_check_access(request.user)
    identity = (request.GET.get("identity") or "").strip()
    prefix = request.GET.get("prefix") if request.GET.get("prefix") in ("person1", "person2") else "person1"
    exclude_id = request.GET.get("exclude") or ""
    if not identity:
        return JsonResponse({"found": False})
    person, apps = previous_applications_for_identity(identity)
    if not person:
        return JsonResponse({"found": False})
    if exclude_id.isdigit():
        apps = [item for item in apps if item.id != int(exclude_id)]

    source = apps[0] if apps else None
    source_id = request.GET.get("source") or ""
    if source_id.isdigit():
        source = next((item for item in apps if item.id == int(source_id)), source)

    return JsonResponse(
        {
            "found": True,
            "person": _person_to_json(person),
            "applications_count": len(apps),
            "prefill_source": (
                {"id": source.id, "folder_number": source.folder_number} if source else None
            ),
            "prefill": application_prefill(source, person, prefix) if source else None,
            "applications": [_application_summary_json(item, person) for item in apps[:20]],
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
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    identity = str(body.get("identity_number") or "").strip()
    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        return JsonResponse({"error": "payload must be an object"}, status=400)
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
        parsed = _parsed_from_session(payload)
        try:
            application = save_import(parsed)
        except (ValidationError, IntegrityError) as exc:
            if isinstance(exc, ValidationError):
                messages.error(request, exc.messages[0] if exc.messages else str(exc))
            else:
                messages.error(request, CONCURRENT_SAVE_MESSAGE)
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
        if upload.size > MAX_IMPORT_FILE_SIZE:
            messages.error(
                request,
                f"Το αρχείο υπερβαίνει το μέγιστο επιτρεπτό μέγεθος "
                f"({MAX_IMPORT_FILE_SIZE // (1024 * 1024)} MB).",
            )
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
