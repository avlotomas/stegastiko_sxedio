from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from cases.case_label_groups import case_label_groups, section_toc_label
from core.configuration_forms import (
    SystemBrandingSettingsForm,
    SystemCaseLabelSettingsForm,
    SystemEmailSettingsForm,
    SystemMenuLabelSettingsForm,
    SystemSectionLabelSettingsForm,
    SystemSubsectionLabelSettingsForm,
    SystemWorkflowSettingsForm,
)
from core.function_catalog import EDIT, VIEW
from core.permissions import access_required, has_access
from core.settings_navigation import settings_nav

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
    return render(
        request,
        "core/settings/overview.html",
        {"settings_nav": settings_nav(request.user, "overview")},
    )


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
        page_title="Αριθμοδότηση και υπενθυμίσεις",
        page_lead="Παράμετροι αρίθμησης φακέλων αιτητών και υπενθυμίσεων διαβουλεύσεων στο dashboard.",
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
        page_lead="Διακομιστής για το email ελλείψεων (2.2) και προεπιλεγμένο θέμα.",
    )
