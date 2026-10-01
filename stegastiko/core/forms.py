"""Shared form widgets and helpers."""

import re

from django import forms

# Greek locale renders dates as d/m/Y, but <input type="date"> only accepts ISO, so an
# unformatted widget shows an empty picker and silently clears the stored date on save.
ISO_DATE_FORMAT = "%Y-%m-%d"

# Model help_text carries the specification wording prefixed by its section number,
# e.g. "8.1 Ημερομηνία ανάθεσης μελέτης".
SECTION_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$", re.DOTALL)


class IsoDateInput(forms.DateInput):
    """Native date picker that round-trips values correctly."""

    input_type = "date"

    def __init__(self, attrs=None, format=None):
        merged = {"type": "date"}
        if attrs:
            merged.update(attrs)
        super().__init__(attrs=merged, format=format or ISO_DATE_FORMAT)


def split_section_reference(help_text):
    """Split "10.4.6 Ετήσιο εισόδημα" into ("10.4.6", "Ετήσιο εισόδημα")."""
    match = SECTION_PREFIX.match((help_text or "").strip())
    if not match:
        return "", (help_text or "").strip()
    return match.group(1), match.group(2).strip()


def label_without_section_reference(label):
    """Return the Greek wording only, e.g. "1.2 Foo" → "Foo"."""
    _, text = split_section_reference(label or "")
    return text or (label or "").strip()


def apply_greek_labels(form):
    """Promote the Greek help_text to the field label, section number included.

    The UI must be Greek and screens must keep the specification numbering visible, and
    the model help_text already carries both (e.g. "8.1 Ημερομηνία ανάθεσης μελέτης").
    Using it as the label avoids a second source of truth and stops Django falling back
    to a humanised English field name. Labels set explicitly on the form win, because
    this runs before the subclass gets a chance to override them.
    """
    for field in form.fields.values():
        section_ref, text = split_section_reference(field.help_text)
        if not section_ref or not text:
            continue
        field.label = f"{section_ref} {text}"
        field.help_text = ""
