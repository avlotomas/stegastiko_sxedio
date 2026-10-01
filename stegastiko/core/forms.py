"""Shared form widgets and helpers."""

import re

from django import forms

# Greek locale renders dates as d/m/Y, but <input type="date"> only accepts ISO, so an
# unformatted widget shows an empty picker and silently clears the stored date on save.
ISO_DATE_FORMAT = "%Y-%m-%d"

# Model help_text carries the specification wording prefixed by its section number,
# e.g. "8.1 Ημερομηνία ανάθεσης μελέτης". Shared fields may list several refs:
# "5 / 8.4 Τμήμα / Υπηρεσία".
SECTION_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$", re.DOTALL)
COMPOUND_SECTION_PREFIX = re.compile(
    r"^(?:(?:\d+(?:\.\d+)*)\s*(?:/\s*)?)+\s*(?P<label>\S.*)$",
    re.DOTALL,
)


class IsoDateInput(forms.DateInput):
    """Native date picker that round-trips values correctly."""

    input_type = "date"

    def __init__(self, attrs=None, format=None):
        merged = {"type": "date"}
        if attrs:
            merged.update(attrs)
        super().__init__(attrs=merged, format=format or ISO_DATE_FORMAT)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Several uploads in one input; cleans to a list (empty when nothing was chosen)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)] if data else []

    def has_changed(self, initial, data):
        # The widget returns [] when nothing is chosen; that must not make an
        # untouched extra formset row count as filled in.
        return not self.disabled and bool(data)


def split_section_reference(help_text):
    """Split a prefixed help_text into (section_ref, greek_label).

    Handles a single ref ("8.1 Ημερομηνία…") and compound refs ("5 / 8.4 Τμήμα…").
    """
    text = (help_text or "").strip()
    compound = COMPOUND_SECTION_PREFIX.match(text)
    if compound:
        prefix = text[: compound.start("label")].strip()
        refs = re.findall(r"\d+(?:\.\d+)*", prefix)
        return (refs[-1] if refs else ""), compound.group("label").strip()
    match = SECTION_PREFIX.match(text)
    if not match:
        return "", text
    return match.group(1), match.group(2).strip()


def label_without_section_reference(label):
    """Return the Greek wording only, e.g. "1.2 Foo" → "Foo"."""
    _, text = split_section_reference(label or "")
    return text or (label or "").strip()


def apply_greek_labels(form):
    """Promote the Greek help_text to the field label (wording only, no § number).

    Model help_text carries the specification reference plus Greek text
    (e.g. "8.1 Ημερομηνία ανάθεσης μελέτης"); subsection headings keep the number.
    Using help_text as the label avoids a second source of truth and stops Django
    falling back to a humanised English field name. Labels set explicitly on the form
    win, because this runs before the subclass gets a chance to override them.
    """
    for field in form.fields.values():
        section_ref, text = split_section_reference(field.help_text)
        if not section_ref or not text:
            continue
        field.label = text
        field.help_text = ""
