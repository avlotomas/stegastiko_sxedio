from django.contrib import messages
from django.shortcuts import redirect, render

from core.configuration_forms import (
    SystemBrandingSettingsForm,
    SystemEmailSettingsForm,
    SystemMenuLabelSettingsForm,
    SystemSectionLabelSettingsForm,
    SystemSubsectionLabelSettingsForm,
    SystemWorkflowSettingsForm,
)
from core.function_catalog import EDIT
from core.permissions import access_required, has_access
from core.settings_navigation import settings_nav


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


@access_required("settings_section_labels", post_action=EDIT)
def system_settings_section_labels(request):
    return _settings_form_view(
        request,
        section_key="section_labels",
        function_code="settings_section_labels",
        form_class=SystemSectionLabelSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Τίτλοι ενοτήτων αίτησης Κ.Σ. / Δ.Δ.",
        page_lead="Πλοήγηση δεξιά, κεφαλίδα οθόνης επεξεργασίας και κάρτες προβολής φακέλου.",
    )


@access_required("settings_subsection_labels", post_action=EDIT)
def system_settings_subsection_labels(request):
    return _settings_form_view(
        request,
        section_key="subsection_labels",
        function_code="settings_subsection_labels",
        form_class=SystemSubsectionLabelSettingsForm,
        template_name="core/settings/form_page.html",
        page_title="Τίτλοι υποενοτήτων αίτησης Κ.Σ. / Δ.Δ.",
        page_lead="Υποενότητες στις οθόνες επεξεργασίας και στην προβολή φακέλου (π.χ. 3.1, 3.2).",
    )


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
