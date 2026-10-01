from django import forms

from cases.section_labels import (
    CASE_SECTION_LABEL_KEYS,
    form_field_name_for_section_label,
    get_case_section_label,
    save_case_section_label,
)
from cases.services import DEFICIENCY_EMAIL_SUBJECT_DEFAULT, DEFICIENCY_EMAIL_SUBJECT_KEY
from core.services import SMTP_SECURITY_CHOICES, SMTP_SETTING_DEFAULTS, get_setting, set_setting

GENERAL_SETTING_FIELDS = (
    ("applicationFolderPrefix", "Πρόθεμα Αρ. Φακέλου Αιτητή (10.1.1)"),
    ("folderSequenceDigits", "Πλήθος ψηφίων ακολουθίας ανά Κοινότητα"),
)
EMAIL_SETTING_DEFAULTS = {
    **SMTP_SETTING_DEFAULTS,
    DEFICIENCY_EMAIL_SUBJECT_KEY: DEFICIENCY_EMAIL_SUBJECT_DEFAULT,
}


def _email_setting_fields():
    """SMTP server and email texts; keyed by the SystemSetting key."""
    return {
        "smtpHost": forms.CharField(label="Διακομιστής SMTP", max_length=255, required=False),
        "smtpPort": forms.IntegerField(label="Θύρα SMTP", min_value=1, max_value=65535),
        "smtpSecurity": forms.ChoiceField(
            label="Κρυπτογράφηση σύνδεσης", choices=SMTP_SECURITY_CHOICES
        ),
        "smtpUsername": forms.CharField(
            label="Όνομα χρήστη SMTP", max_length=255, required=False
        ),
        "smtpPassword": forms.CharField(
            label="Κωδικός πρόσβασης SMTP",
            max_length=512,
            required=False,
            widget=forms.PasswordInput(render_value=False),
            help_text="Αφήστε κενό για να διατηρηθεί ο αποθηκευμένος κωδικός.",
        ),
        "smtpFromEmail": forms.EmailField(
            label="Διεύθυνση αποστολέα", max_length=255, required=False
        ),
        DEFICIENCY_EMAIL_SUBJECT_KEY: forms.CharField(
            label="Θέμα email ελλείψεων (2.2)",
            max_length=255,
            help_text="Μπορεί να περιέχει {case_number} (αριθμός υπόθεσης) και {community} (Κοινότητα).",
        ),
    }


def email_field_name(setting_key):
    return f"email_{setting_key}"


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
        for setting_key, field in _email_setting_fields().items():
            field.widget.attrs.setdefault("class", "input")
            self.fields[email_field_name(setting_key)] = field
        if not self.is_bound:
            for section_key in CASE_SECTION_LABEL_KEYS:
                fname = form_field_name_for_section_label(section_key)
                self.fields[fname].initial = get_case_section_label(section_key)
            for setting_key, _ in GENERAL_SETTING_FIELDS:
                self.fields[f"setting_{setting_key}"].initial = get_setting(setting_key, "")
            for setting_key, default in EMAIL_SETTING_DEFAULTS.items():
                if setting_key != "smtpPassword":
                    self.fields[email_field_name(setting_key)].initial = get_setting(
                        setting_key, default
                    )

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
        for setting_key in EMAIL_SETTING_DEFAULTS:
            field_name = email_field_name(setting_key)
            value = self.cleaned_data[field_name]
            if setting_key == "smtpPassword" and not value:
                continue
            set_setting(setting_key, str(value), str(self.fields[field_name].label))
