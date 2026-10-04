"""Group Κ.Σ./Δ.Δ. section and subsection label fields for the settings screen."""

from cases.section_labels import (
    CASE_SECTION_LABEL_KEYS,
    case_section_number,
    form_field_name_for_section_label,
)
from cases.subsection_labels import (
    CASE_SUBSECTION_LABEL_KEYS,
    SUBSECTION_HEADING_NUMBERS,
    form_field_name_for_subsection_label,
)


def parent_section_key_for_subsection(subsection_key: str) -> str:
    """Map a subsection setting key to its parent section key (incl. 7-plots)."""
    if subsection_key.startswith(("7.8", "7.9")):
        return "7-plots"
    if "." not in subsection_key:
        return subsection_key
    return subsection_key.split(".", 1)[0]


def _subsections_by_section() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {key: [] for key in CASE_SECTION_LABEL_KEYS}
    for subsection_key in CASE_SUBSECTION_LABEL_KEYS:
        parent = parent_section_key_for_subsection(subsection_key)
        grouped.setdefault(parent, []).append(subsection_key)
    return grouped


def case_label_groups():
    """Ordered groups: each section with its subsection label fields."""
    by_section = _subsections_by_section()
    groups = []
    for section_key in CASE_SECTION_LABEL_KEYS:
        subsections = []
        for subsection_key in by_section.get(section_key, ()):
            subsections.append(
                {
                    "key": subsection_key,
                    "number": SUBSECTION_HEADING_NUMBERS.get(subsection_key, subsection_key),
                    "field_name": form_field_name_for_subsection_label(subsection_key),
                }
            )
        groups.append(
            {
                "section_key": section_key,
                "section_number": case_section_number(section_key),
                "section_anchor": "section-" + section_key.replace("-", "_"),
                "section_field_name": form_field_name_for_section_label(section_key),
                "subsections": subsections,
            }
        )
    return groups


def section_toc_label(section_key: str, section_number: str) -> str:
    """Short label for the table of contents (distinguish 7 vs 7-plots)."""
    if section_key == "7-plots":
        return f"{section_number} (οικόπεδα)"
    return section_number
