"""Read-only labels and values for case fields on the detail screen."""

from django.db import models

from core.forms import label_without_section_reference


def case_field_label(case, field_name):
    field = case._meta.get_field(field_name)
    text = label_without_section_reference(field.help_text or "")
    if text:
        return text
    return field.verbose_name


def case_field_value(case, field_name):
    """Plain-text display value; empty strings and null become None (show — in template)."""
    field = case._meta.get_field(field_name)
    value = getattr(case, field_name)
    if isinstance(field, models.BooleanField):
        return "ΝΑΙ" if value else "ΟΧΙ"
    if value is None or value == "":
        return None
    if field.choices:
        display = getattr(case, f"get_{field_name}_display", None)
        if callable(display):
            return display()
    return value


def case_field_rows(case, field_names):
    return [
        {"label": case_field_label(case, name), "value": case_field_value(case, name)}
        for name in field_names
    ]
