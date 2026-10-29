from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cases.case_label_groups import case_label_groups, section_toc_label
from core.configuration_forms import (
    AgreementTemplateUploadForm,
    SystemBrandingSettingsForm,
    SystemCaseLabelSettingsForm,
    SystemEmailSettingsForm,
    SystemMenuLabelSettingsForm,
    SystemPlotApplicationGridSettingsForm,
    SystemPlotApplicationLabelSettingsForm,
    SystemSectionLabelSettingsForm,
    SystemSubsectionLabelSettingsForm,
    SystemWorkflowSettingsForm,
)
from core.docx_merge import (
    AGREEMENT_DISTRICT_OFFICER_DEFAULT,
    AGREEMENT_DISTRICT_OFFICER_KEY,
    AGREEMENT_PLACEHOLDERS,
)
from core.function_catalog import EDIT, IMPORT, VIEW
from core.permissions import access_required, has_access
from core.services import get_setting, set_setting
from core.settings_navigation import settings_nav
from core.ui_texts import (
    UI_EDIT_MODE_SESSION_KEY,
    require_ui_text_edit_access,
    save_ui_text_entry,
)

CASE_LABEL_SECTION_FUNCTION = "settings_section_labels"
CASE_LABEL_SUBSECTION_FUNCTION = "settings_subsection_labels"


def _settings_form_view(
    request, *, section_key, function_code, form_class, template_name, page_title, page_lead=""
):
    can_edit = has_access(request.user, function_code, EDIT)
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Οι ρυθμίσεις αποθηκεύτηκαν.")
            return redirect(request.resolver_match.url_name)
    else:
        form = form_class()
    if not can_edit:
        for field in form.fields.values():
            field.disabled = True
    return render(
        request,
        template_name,
        {
            "form": form,
            "can_edit": can_edit,
            "settings_nav": settings_nav(request.user, section_key),
            "page_title": page_title,
            "page_lead": page_lead,
        },
    )


@access_required("settings")
def system_configuration(request):
    nav = settings_nav(request.user, "")
    if not nav:
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
    return redirect(nav[0]["url_name"])


@access_required("settings_branding", post_action=EDIT)
def system_settings_branding(request):
    return _settings_form_view(
        request,
        section_key="branding",
        function_code="settings_branding",
        form_class=SystemBrandingSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Εμφάνιση εφαρμογής",
        page_lead="Κείμενο στην κεφαλίδα (πάνω αριστερά) και ως προεπιλεγμένος τίτλος καρτέλας browser.",
    )


@access_required("settings_menu_labels", post_action=EDIT)
def system_settings_menu_labels(request):
    return _settings_form_view(
        request,
        section_key="menu_labels",
        function_code="settings_menu_labels",
        form_class=SystemMenuLabelSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Ονόματα μενού",
        page_lead="Ονόματα των επιλογών του κύριου μενού στην κεφαλίδα.",
    )


@access_required("settings_workflow", post_action=EDIT)
def system_settings_workflow(request):
    return _settings_form_view(
        request,
        section_key="workflow",
        function_code="settings_workflow",
        form_class=SystemWorkflowSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Αριθμοδότηση, υπενθυμίσεις και όρια εισοδήματος",
        page_lead="Παράμετροι αρίθμησης υποθέσεων και φακέλων αιτητών, υπενθυμίσεων διαβουλεύσεων στο dashboard και ορίων εισοδήματος (10.4).",
    )


def _case_label_access(request):
    can_view_sections = has_access(request.user, CASE_LABEL_SECTION_FUNCTION, VIEW)
    can_view_subsections = has_access(request.user, CASE_LABEL_SUBSECTION_FUNCTION, VIEW)
    if not (can_view_sections or can_view_subsections):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
    can_edit_sections = has_access(request.user, CASE_LABEL_SECTION_FUNCTION, EDIT)
    can_edit_subsections = has_access(request.user, CASE_LABEL_SUBSECTION_FUNCTION, EDIT)
    return can_view_sections, can_view_subsections, can_edit_sections, can_edit_subsections


@login_required
def system_settings_case_labels(request):
    (
        can_view_sections,
        can_view_subsections,
        can_edit_sections,
        can_edit_subsections,
    ) = _case_label_access(request)

    if request.method == "POST":
        if not (can_edit_sections or can_edit_subsections):
            raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")
        form = SystemCaseLabelSettingsForm(
            request.POST,
            include_sections=can_view_sections,
            include_subsections=can_view_subsections,
        )
        if form.is_valid():
            form.save(
                save_sections=can_edit_sections,
                save_subsections=can_edit_subsections,
            )
            messages.success(request, "Οι τίτλοι αποθηκεύτηκαν.")
            return redirect("system_settings_case_labels")
    else:
        form = SystemCaseLabelSettingsForm(
            include_sections=can_view_sections,
            include_subsections=can_view_subsections,
        )

    if not can_edit_sections:
        for group in case_label_groups():
            field = form.fields.get(group["section_field_name"])
            if field is not None:
                field.disabled = True
    if not can_edit_subsections:
        for group in case_label_groups():
            for item in group["subsections"]:
                field = form.fields.get(item["field_name"])
                if field is not None:
                    field.disabled = True

    label_groups = []
    for group in case_label_groups():
        if not can_view_sections and not group["subsections"]:
            continue
        subsections = group["subsections"] if can_view_subsections else []
        section_field = None
        if can_view_sections and group["section_field_name"] in form.fields:
            section_field = form[group["section_field_name"]]
        subsection_rows = []
        for item in subsections:
            if item["field_name"] in form.fields:
                subsection_rows.append({**item, "field": form[item["field_name"]]})
        if section_field is not None or subsection_rows:
            label_groups.append(
                {
                    **group,
                    "subsections": subsection_rows,
                    "section_field": section_field,
                    "toc_label": section_toc_label(
                        group["section_key"], group["section_number"]
                    ),
                }
            )

    can_edit = can_edit_sections or can_edit_subsections
    return render(
        request,
        "core/settings/case_labels.html",
        {
            "form": form,
            "can_edit": can_edit,
            "can_edit_sections": can_edit_sections,
            "can_edit_subsections": can_edit_subsections,
            "label_groups": label_groups,
            "settings_nav": settings_nav(request.user, "case_labels"),
            "page_title": "Τίτλοι αίτησης διαχωρισμού",
            "page_lead": (
                "Τίτλοι ενοτήτων και υποενοτήτων όπως εμφανίζονται στην πλοήγηση, "
                "στις οθόνες επεξεργασίας και στην προβολή φακέλου."
            ),
        },
    )


@access_required("settings_plot_application_labels", post_action=EDIT)
def system_settings_plot_application_labels(request):
    return _settings_form_view(
        request,
        section_key="plot_application_labels",
        function_code="settings_plot_application_labels",
        form_class=SystemPlotApplicationLabelSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Τίτλοι αίτησης παραχώρησης οικοπέδου",
        page_lead=(
            "Τίτλοι των σταδίων της αίτησης παραχώρησης οικοπέδου, όπως εμφανίζονται στον κατάλογο "
            "αιτήσεων, στην προβολή της αίτησης, στα φίλτρα, στην καρτέλα Ατόμου και στις εκθέσεις PDF."
        ),
    )


@access_required("settings_plot_application_labels", post_action=EDIT)
def system_settings_plot_application_grid(request):
    return _settings_form_view(
        request,
        section_key="plot_application_grid",
        function_code="settings_plot_application_labels",
        form_class=SystemPlotApplicationGridSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Πίνακας αιτήσεων παραχώρησης οικοπέδου",
        page_lead=(
            "Επιλογή των ορατών στηλών στον πίνακα των αιτήσεων παραχώρησης οικοπέδου "
            "και πλήθος σταθερών (locked) στηλών από την αρχή κατά την οριζόντια κύλιση."
        ),
    )


@access_required("settings_section_labels", post_action=EDIT)
def system_settings_section_labels(request):
    return redirect("system_settings_case_labels")


@access_required("settings_subsection_labels", post_action=EDIT)
def system_settings_subsection_labels(request):
    return redirect("system_settings_case_labels")


@access_required("settings_email", post_action=EDIT)
def system_settings_email(request):
    return _settings_form_view(
        request,
        section_key="email",
        function_code="settings_email",
        form_class=SystemEmailSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Αποστολή email (SMTP)",
        page_lead="Διακομιστής SMTP και πρότυπα θεμάτων/κειμένων email (ελλείψεις, Προκαταρκτικός/Τελικός Κατάλογος, ενστάσεις, κλήρωση, Συμφωνία, επιλαχόντες).",
    )


@access_required("settings_agreement_templates")
def system_settings_agreement_templates(request):
    from allocation.models import AgreementTemplate

    can_upload = has_access(request.user, "settings_agreement_templates", IMPORT) or has_access(
        request.user, "settings_agreement_templates", EDIT
    )
    if request.method == "POST":
        if not can_upload:
            raise PermissionDenied("Δεν έχετε δικαίωμα μεταφόρτωσης προτύπου Συμφωνίας.")
        if "save_agreement_settings" in request.POST or (
            f"setting_{AGREEMENT_DISTRICT_OFFICER_KEY}" in request.POST
            and "template_file" not in request.FILES
        ):
            raw_officer = (
                request.POST.get(f"setting_{AGREEMENT_DISTRICT_OFFICER_KEY}")
                or request.POST.get(AGREEMENT_DISTRICT_OFFICER_KEY)
                or ""
            ).strip()
            set_setting(
                AGREEMENT_DISTRICT_OFFICER_KEY,
                raw_officer,
                "Έπαρχος στη Συμφωνία Παραχώρησης (Παράρτημα 4, Ενότ. 12)",
            )
            messages.success(request, "Οι ρυθμίσεις αποθηκεύτηκαν.")
            return redirect("system_settings_agreement_templates")
        form = AgreementTemplateUploadForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Το πρότυπο Συμφωνίας Παραχώρησης αποθηκεύτηκε.")
            return redirect("system_settings_agreement_templates")
    else:
        form = AgreementTemplateUploadForm()
    if not can_upload:
        for field in form.fields.values():
            field.disabled = True
    templates = AgreementTemplate.objects.order_by("-is_active", "-id")
    district_officer = get_setting(
        AGREEMENT_DISTRICT_OFFICER_KEY, AGREEMENT_DISTRICT_OFFICER_DEFAULT
    )
    return render(
        request,
        "core/settings/agreement_templates.html",
        {
            "form": form,
            "can_edit": can_upload,
            "templates": templates,
            "placeholders": AGREEMENT_PLACEHOLDERS,
            "district_officer": district_officer,
            "settings_nav": settings_nav(request.user, "agreement_templates"),
            "page_title": "Πρότυπο Συμφωνίας Παραχώρησης (Παράρτημα 4)",
            "page_lead": (
                "Παράμετροι και πρότυπο αρχείου Word (.docx) για την αυτόματη συμπλήρωση των στοιχείων της αίτησης "
                "και του οικοπέδου κατά την υπογραφή της Συμφωνίας Παραχώρησης (Ενότ. 12, 15)."
            ),
        },
    )


@login_required
@require_POST
def ui_edit_mode_toggle(request):
    try:
        require_ui_text_edit_access(request.user)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=403)
    explicit = request.POST.get("enabled")
    if explicit is not None:
        active = explicit in ("1", "true", "True", "on")
    else:
        active = not bool(request.session.get(UI_EDIT_MODE_SESSION_KEY))
    request.session[UI_EDIT_MODE_SESSION_KEY] = active
    return JsonResponse({"ok": True, "ui_edit_mode": active})


@login_required
@require_POST
def ui_text_save(request):
    key = request.POST.get("key", "")
    value = request.POST.get("value", "")
    description = request.POST.get("description", "")
    reset = request.POST.get("reset") in ("1", "true", "True", "on")
    try:
        saved = save_ui_text_entry(
            request.user,
            key=key,
            value=value,
            description=description,
            reset=reset,
        )
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=403)
    except ValidationError as exc:
        msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        return JsonResponse({"ok": False, "message": msg}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "key": key.strip(),
            "value": saved,
            "reset": reset,
            "message": "Το κείμενο αποθηκεύτηκε.",
        }
    )
