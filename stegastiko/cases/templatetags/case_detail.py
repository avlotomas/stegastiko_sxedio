from django import template

from cases.detail_display import case_field_rows
from cases.services import approved_design_plot_section, completion_readiness
from cases.section_labels import case_section_heading as build_case_section_heading
from cases.subsection_labels import (
    case_subsection_heading as build_case_subsection_heading,
    get_case_subsection_label,
)
from core.function_catalog import EDIT, VIEW, case_section_function
from core.permissions import has_access

register = template.Library()


@register.inclusion_tag("cases/_detail_field_grid.html")
def case_detail_fields(case, *field_names):
    return {"rows": case_field_rows(case, field_names)}


@register.simple_tag
def case_section_heading(section_key):
    return build_case_section_heading(section_key)


@register.simple_tag
def case_subsection_heading(subsection_key):
    return build_case_subsection_heading(subsection_key)


@register.simple_tag
def case_subsection_label(subsection_key):
    return get_case_subsection_label(subsection_key)


@register.inclusion_tag("cases/_approved_design_plot_workspace.html", takes_context=True)
def approved_design_plot_workspace(context, case):
    """Persistent floating launcher and modal for the plots owned by section 7."""
    request = context["request"]
    section = approved_design_plot_section(case)
    function = case_section_function(section)
    if not has_access(request.user, function, VIEW):
        return {"show_approved_design_plot_workspace": False}
    can_edit = has_access(request.user, function, EDIT)
    return {
        "show_approved_design_plot_workspace": True,
        "case": case,
        "plot_section": section,
        "can_edit_approved_design_plots": can_edit,
    }


@register.inclusion_tag("cases/_case_completion_panel.html", takes_context=True)
def case_completion_panel(context, case):
    """«Ολοκλήρωση αίτησης» in the case actions sidebar of every case screen."""
    user = context["request"].user
    if not has_access(user, "case_completion", VIEW):
        return {"show_case_completion": False}
    readiness = completion_readiness(case)
    return {
        "show_case_completion": True,
        "case": case,
        "readiness": readiness,
        "missing": [label for label, ready in readiness["rows"] if not ready],
        "can_complete": has_access(user, "case_completion", EDIT),
        "plots_count": case.plots.count(),
        "csrf_token": context.get("csrf_token"),
    }
