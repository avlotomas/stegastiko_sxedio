from django import template

from cases.detail_display import case_field_rows
from cases.section_labels import case_section_heading as build_case_section_heading
from cases.subsection_labels import (
    case_subsection_heading as build_case_subsection_heading,
    get_case_subsection_label,
)

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
