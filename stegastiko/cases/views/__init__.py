"""Views of the Κ.Σ./Δ.Δ. application, split by area.

Every view stays importable as `cases.views.<name>` (cases/urls.py and the tests use it).
"""

from cases.views.announcements import (
    announcement_create,
    announcement_detail,
    announcement_publish,
    announcement_regenerate,
)
from cases.views.attachments import case_attachment_download
from cases.views.common import (
    SECTION_ORDER,
    SECTIONS,
    case_nav_items,
    section_screens_for,
)
from cases.views.communications import case_communication_detail, case_deficiency_email_send
from cases.views.folder import case_create, case_detail, case_history, case_list
from cases.views.grids import (
    CONSULTATION_GRIDS,
    approved_design_plot_bulk_create,
    approved_design_plot_delete,
    approved_design_plot_form,
    approved_design_plot_grid,
    approved_design_plot_inline_edit,
    completeness_check_delete,
    completeness_check_form,
    consultation_delete,
    consultation_form,
    infrastructure_check_delete,
    infrastructure_check_form,
    land_plot_delete,
    land_plot_evaluation_form,
    land_plot_form,
    ministry_decision_round_delete,
    ministry_decision_round_form,
    utility_service_delete,
    utility_service_form,
)
from cases.views.sections import case_section_edit, section_4_blank_pdf, section_6_report_pdf

__all__ = [
    "CONSULTATION_GRIDS",
    "SECTIONS",
    "SECTION_ORDER",
    "announcement_create",
    "announcement_detail",
    "announcement_publish",
    "announcement_regenerate",
    "approved_design_plot_bulk_create",
    "approved_design_plot_delete",
    "approved_design_plot_form",
    "approved_design_plot_grid",
    "approved_design_plot_inline_edit",
    "case_attachment_download",
    "case_communication_detail",
    "case_create",
    "case_deficiency_email_send",
    "case_detail",
    "case_history",
    "case_list",
    "case_nav_items",
    "case_section_edit",
    "completeness_check_delete",
    "completeness_check_form",
    "consultation_delete",
    "consultation_form",
    "infrastructure_check_delete",
    "infrastructure_check_form",
    "land_plot_delete",
    "land_plot_evaluation_form",
    "land_plot_form",
    "ministry_decision_round_delete",
    "ministry_decision_round_form",
    "section_4_blank_pdf",
    "section_6_report_pdf",
    "section_screens_for",
    "utility_service_delete",
    "utility_service_form",
]
