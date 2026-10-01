"""Blank printable PDF for Ενότητα 4 (field use with pen)."""

from __future__ import annotations

from cases.models import Case, LandPlot, UtilityService, UtilityServiceType
from cases.pdf_rendering import render_pdf, safe_case_number
from cases.subsection_labels import case_subsection_heading
from core.forms import label_without_section_reference

UTILITY_SERVICE_BLANK_ROWS = 5


def _field_label(model, field_name: str) -> str:
    field = model._meta.get_field(field_name)
    raw = field.help_text or field.verbose_name
    return label_without_section_reference(raw) or raw


def section4_blank_pdf_context(case: Case) -> dict:
    plots = list(case.land_plots.all())
    service_types = list(
        UtilityServiceType.objects.filter(is_active=True).order_by("display_order", "name")
    )
    return {
        "case": case,
        "section_title": "Ενότητα 4 — Τεχνική αξιολόγηση καταλληλότητας",
        "heading_41": case_subsection_heading("4.1"),
        "heading_42": case_subsection_heading("4.2"),
        "heading_43": case_subsection_heading("4.3"),
        "heading_45": case_subsection_heading("4.5"),
        "heading_46": case_subsection_heading("4.6"),
        "plots": plots,
        "morphology_choices": list(LandPlot.Morphology.choices),
        "suitability_choices": list(LandPlot.SuitabilityDecision.choices),
        "utility_service_types": service_types,
        "utility_blank_rows": range(UTILITY_SERVICE_BLANK_ROWS),
        "labels": {
            "location": _field_label(LandPlot, "location"),
            "area_sqm": _field_label(LandPlot, "area_sqm"),
            "zone": _field_label(LandPlot, "zone"),
            "inside_development_zone": _field_label(LandPlot, "inside_development_zone"),
            "morphology": _field_label(LandPlot, "morphology"),
            "morphology_other": _field_label(LandPlot, "morphology_other"),
            "morphology_comments": _field_label(LandPlot, "morphology_comments"),
            "usable_area_sqm": _field_label(LandPlot, "usable_area_sqm"),
            "estimated_cost": _field_label(LandPlot, "estimated_cost"),
            "estimated_plots_count": _field_label(LandPlot, "estimated_plots_count"),
            "technical_suitability": _field_label(LandPlot, "technical_suitability"),
            "section4_comments": _field_label(Case, "section4_comments"),
            "utility_service": "Υπηρεσία",
            "utility_proximity": _field_label(UtilityService, "proximity"),
            "utility_comments": _field_label(UtilityService, "comments"),
            "engineer_full_name": _field_label(Case, "engineer_full_name"),
            "technical_visit_date": _field_label(Case, "technical_visit_date"),
        },
    }


def render_section4_blank_pdf(case: Case) -> bytes:
    return render_pdf("cases/pdf/section_4_blank.html", section4_blank_pdf_context(case))


def section4_blank_pdf_filename(case: Case) -> str:
    return f"technical_evaluation_{safe_case_number(case.case_number)}.pdf"
