"""Ενότητα 6 report «Πίνακες αξιολόγησης καταλληλότητας κρατικής γης» (PDF).

Layout follows the Word template `report_pinakes_aksiologisis.docx`: Cyprus coat of arms,
issuing authority and report title on the first page, then the 6.1–6.6 tables.
"""

from __future__ import annotations

from django.utils import timezone

from cases.models import Case
from cases.pdf_rendering import render_pdf, safe_case_number
from cases.services import suitability_summary
from cases.subsection_labels import case_subsection_heading, get_case_subsection_label

REPORT_TITLE = "ΠΙΝΑΚΕΣ ΑΞΙΟΛΟΓΗΣΗΣ ΚΑΤΑΛΛΗΛΟΤΗΤΑΣ ΚΡΑΤΙΚΗΣ ΓΗΣ"

SECTION6_REPORT_SUBSECTION_KEYS = ("6.1", "6.2", "6.3", "6.4", "6.5", "6.6")


def default_section6_report_includes() -> dict[str, bool]:
    return {key: True for key in SECTION6_REPORT_SUBSECTION_KEYS}


def parse_section6_report_includes(query_params) -> dict[str, bool]:
    """Map ?include=6.1&include=6.2… to flags; omit query → all subsections."""
    if hasattr(query_params, "getlist"):
        raw = query_params.getlist("include")
    else:
        values = query_params.get("include", [])
        raw = values if isinstance(values, list) else [values]
    includes = [value for value in raw if value in SECTION6_REPORT_SUBSECTION_KEYS]
    if not includes:
        return default_section6_report_includes()
    selected = set(includes)
    return {key: key in selected for key in SECTION6_REPORT_SUBSECTION_KEYS}


def section6_report_context(case: Case, includes: dict[str, bool] | None = None) -> dict:
    if includes is None:
        includes = default_section6_report_includes()
    state_land_question = Case._meta.get_field("state_land_remains_sufficient").help_text
    inc = {key.replace(".", "_"): includes[key] for key in SECTION6_REPORT_SUBSECTION_KEYS}
    return {
        "case": case,
        "report_title": REPORT_TITLE,
        "issued_at": timezone.localtime(),
        "summary": suitability_summary(case),
        "land_plots": list(case.land_plots.all()),
        "state_land_question": state_land_question.removeprefix("3.2 "),
        "inc": inc,
        "heading_62": case_subsection_heading("6.2"),
        "heading_access": get_case_subsection_label("4.3"),
        "heading_61": case_subsection_heading("6.1"),
        "heading_63": case_subsection_heading("6.3"),
        "heading_64": case_subsection_heading("6.4"),
        "heading_65": case_subsection_heading("6.5"),
        "heading_66": case_subsection_heading("6.6"),
    }


def render_section6_report_pdf(case: Case, includes: dict[str, bool] | None = None) -> bytes:
    return render_pdf(
        "cases/pdf/section_6_report.html",
        section6_report_context(case, includes=includes),
    )


def section6_report_pdf_filename(case: Case) -> str:
    return f"pinakes_aksiologisis_{safe_case_number(case.case_number)}.pdf"
