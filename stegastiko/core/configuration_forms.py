from django import forms

from cases.section_labels import (
    CASE_SECTION_LABEL_KEYS,
    form_field_name_for_section_label,
    get_case_section_label,
    save_case_section_label,
)
from core.services import get_setting, set_setting

GENERAL_SETTING_FIELDS = (
    ("applicationFolderPrefix", "Πρόθεμα Αρ. Φακέλου Αιτητή (10.1.1)"),
    ("folderSequenceDigits", "Πλήθος ψηφίων ακολουθίας ανά Κοινότητα"),
)


class SystemConfigurationForm(forms.Form):
    """Administrator-only application parameters."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for section_key in CASE_SECTION_LABEL_KEYS:
            field_name = form_field_name_for_section_label(section_key)
            self.fields[field_name] = forms.CharField(
                label=f"Ενότητα {section_key} — τίτλος εμφάνισης",
                max_length=255,
                widget=forms.TextInput(attrs={"class": "input"}),
            )
        for setting_key, label in GENERAL_SETTING_FIELDS:
            self.fields[f"setting_{setting_key}"] = forms.CharField(
                label=label,
                max_length=512,
                widget=forms.TextInput(attrs={"class": "input"}),
            )
        if not self.is_bound:
            for section_key in CASE_SECTION_LABEL_KEYS:
                fname = form_field_name_for_section_label(section_key)
                self.fields[fname].initial = get_case_section_label(section_key)
            for setting_key, _ in GENERAL_SETTING_FIELDS:
                self.fields[f"setting_{setting_key}"].initial = get_setting(setting_key, "")

    def save(self):
        for section_key in CASE_SECTION_LABEL_KEYS:
            fname = form_field_name_for_section_label(section_key)
            save_case_section_label(section_key, self.cleaned_data[fname])
        for setting_key, description in GENERAL_SETTING_FIELDS:
            set_setting(
                setting_key,
                self.cleaned_data[f"setting_{setting_key}"],
                description,
            )
