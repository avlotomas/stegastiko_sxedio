"""Generic section screen (Ενότητες 1–8) and the section PDFs."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import content_disposition_header

from cases import section_refs as refs
from cases.forms import DeficiencyEmailForm
from cases.models import Consultation
from cases.section4_blank_pdf import render_section4_blank_pdf, section4_blank_pdf_filename
from cases.section6_report_pdf import (
    parse_section6_report_includes,
    render_section6_report_pdf,
    section6_report_pdf_filename,
)
from cases.section_labels import get_case_section_label
from cases.services import (
    case_communications,
    deficiency_email_subject,
    land_plot_communications,
    save_case_section,
    suitability_summary,
)
from cases.views.common import (
    SECTIONS,
    build_formsets,
    case_for_section,
    case_nav_items,
    disable_fields,
)
from cases.views.grids import case_utility_services, consultation_grid, land_plot_grid_context
from core.function_catalog import EDIT, EXPORT, VIEW, case_section_function
from core.permissions import has_access
from core.services import smtp_is_configured


def _section_context(request, case, section, formsets):
    """Grids and summaries shown on a section screen next to its main form."""
    context = {}
    if section == refs.SECTION_2:
        context.update(
            {
                "completeness_checks": case.completeness_checks.all(),
                "communications": case_communications(case),
                "deficiency_email_form": DeficiencyEmailForm(
                    initial={"subject": deficiency_email_subject(case), "body": ""}
                ),
                "smtp_ready": smtp_is_configured(),
            }
        )
    elif section == refs.SECTION_3:
        context.update(land_plot_grid_context(case))
        context.update(
            {
                "land_plot_communications": land_plot_communications(case),
                "land_plot_email_form": DeficiencyEmailForm(initial={"body": ""}),
            }
        )
    elif section == refs.SECTION_4:
        context["land_plots"] = case.land_plots.all()
        context["utility_services"] = case_utility_services(case)
    elif section == refs.SECTION_5:
        context["consultation_grid"] = consultation_grid(
            request.user, case, Consultation.Stage.SUITABILITY
        )
    elif section == refs.SECTION_6:
        context["ministry_decision_rounds"] = case.ministry_decision_rounds.prefetch_related(
            "attachments"
        )
    elif section == refs.SECTION_7:
        context["approved_design_plots"] = case.approved_design_plots.all()
        context["infrastructure_checks"] = case.infrastructure_checks.all()
        context["consultation_grid"] = consultation_grid(
            request.user, case, Consultation.Stage.DIVISION
        )
    return context


@login_required
def case_section_edit(request, pk, section):
    if section not in SECTIONS:
        raise Http404("Άγνωστη ενότητα.")
    case = case_for_section(request, pk, section, EDIT if request.method == "POST" else VIEW)
    can_edit = has_access(request.user, case_section_function(section), EDIT)
    form_class = SECTIONS[section]["form"]

    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=case) if form_class else None
        formsets = build_formsets(section, case, request.POST, request.FILES)
        form_valid = form.is_valid() if form else True
        formsets_valid = all(formset.is_valid() for _, formset in formsets)
        if form_valid and formsets_valid:
            save_case_section(section, form, [formset for _, formset in formsets])
            messages.success(request, "Οι αλλαγές αποθηκεύτηκαν.")
            return redirect("cases:detail", pk=case.pk)
    else:
        form = form_class(instance=case) if form_class else None
        formsets = build_formsets(section, case)
    if not can_edit:
        if form:
            disable_fields(form)
        for _, formset in formsets:
            for child in formset:
                disable_fields(child)

    context = {
        "case": case,
        "section": section,
        "section_title": get_case_section_label(section),
        "form": form,
        "formsets": formsets,
        "can_edit": can_edit,
        "summary": suitability_summary(case) if section == refs.SECTION_6 else None,
        "case_nav": case_nav_items(case, request.user, active_key=section),
        **_section_context(request, case, section, formsets),
    }
    return render(request, "cases/section_form.html", context)


def _pdf_response(pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=filename
    )
    return response


@login_required
def section_4_blank_pdf(request, pk):
    """Blank Ενότητα 4 form for printing / field completion (PDF)."""
    case = case_for_section(request, pk, refs.SECTION_4, EXPORT)
    return _pdf_response(render_section4_blank_pdf(case), section4_blank_pdf_filename(case))


@login_required
def section_6_report_pdf(request, pk):
    """Ενότητα 6 report «Πίνακες αξιολόγησης καταλληλότητας κρατικής γης» (PDF)."""
    case = case_for_section(request, pk, refs.SECTION_6, EXPORT)
    includes = parse_section6_report_includes(request.GET)
    return _pdf_response(
        render_section6_report_pdf(case, includes=includes), section6_report_pdf_filename(case)
    )
