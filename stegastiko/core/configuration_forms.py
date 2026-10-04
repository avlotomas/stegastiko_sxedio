from django import forms

from cases.section_labels import (
    CASE_SECTION_LABEL_KEYS,
    DEFAULT_CASE_SECTION_LABELS,
    case_section_number,
    form_field_name_for_section_label,
    get_case_section_label,
    save_case_section_label,
)
from cases.subsection_labels import (
    CASE_SUBSECTION_LABEL_KEYS,
    DEFAULT_CASE_SUBSECTION_LABELS,
    SUBSECTION_HEADING_NUMBERS,
    form_field_name_for_subsection_label,
    get_case_subsection_label,
    save_case_subsection_label,
)
from cases.services import DEFICIENCY_EMAIL_SUBJECT_DEFAULT, DEFICIENCY_EMAIL_SUBJECT_KEY
from core.branding import APP_TITLE_DEFAULT, APP_TITLE_SETTING_KEY
from core.menu_labels import MENU_LABEL_FIELDS, get_menu_labels, save_menu_label
from core.reminders import (
    CONSULTATION_DUE_REMINDER_DAYS_DEFAULT,
    CONSULTATION_DUE_REMINDER_DAYS_KEY,
)
from core.services import SMTP_SECURITY_CHOICES, SMTP_SETTING_DEFAULTS, get_setting, set_setting

BRANDING_SETTING_FIELDS = (
    (APP_TITLE_SETTING_KEY, "Τίτλος εφαρμογής (κεφαλίδα, πάνω αριστερά)"),
)
WORKFLOW_SETTING_FIELDS = (
    ("applicationFolderPrefix", "Πρόθεμα Αρ. Φακέλου Αιτητή (10.1.1)"),
    ("folderSequenceDigits", "Πλήθος ψηφίων ακολουθίας ανά Κοινότητα"),
)
GENERAL_SETTING_FIELDS = (*BRANDING_SETTING_FIELDS, *WORKFLOW_SETTING_FIELDS)
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


def _add_section_label_fields(form, *, compact=False):
    for section_key in CASE_SECTION_LABEL_KEYS:
        field_name = form_field_name_for_section_label(section_key)
        default = DEFAULT_CASE_SECTION_LABELS.get(section_key, section_key)
        if compact:
            label = f"Ενότητα {case_section_number(section_key)}"
            if section_key == "7-plots":
                label = "Ενότητα 7 (οικόπεδα)"
        else:
            label = f"Ενότητα {section_key} — τίτλος εμφάνισης"
        form.fields[field_name] = forms.CharField(
            label=label,
            max_length=255,
            help_text=f"Προεπιλογή: «{default}».",
            widget=forms.TextInput(attrs={"class": "input"}),
        )
    if not form.is_bound:
        for section_key in CASE_SECTION_LABEL_KEYS:
            fname = form_field_name_for_section_label(section_key)
            form.fields[fname].initial = get_case_section_label(section_key)


def _add_subsection_label_fields(form, *, compact=False):
    for subsection_key in CASE_SUBSECTION_LABEL_KEYS:
        field_name = form_field_name_for_subsection_label(subsection_key)
        default = DEFAULT_CASE_SUBSECTION_LABELS.get(subsection_key, subsection_key)
        number = SUBSECTION_HEADING_NUMBERS.get(subsection_key, subsection_key)
        label = (
            f"Υποενότητα {number}"
            if compact
            else f"Υποενότητα {subsection_key} — τίτλος εμφάνισης"
        )
        form.fields[field_name] = forms.CharField(
            label=label,
            max_length=255,
            help_text=f"Προεπιλογή: «{default}».",
            widget=forms.TextInput(attrs={"class": "input"}),
        )
    if not form.is_bound:
        for subsection_key in CASE_SUBSECTION_LABEL_KEYS:
            fname = form_field_name_for_subsection_label(subsection_key)
            form.fields[fname].initial = get_case_subsection_label(subsection_key)


class SystemBrandingSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for setting_key, label in BRANDING_SETTING_FIELDS:
            self.fields[f"setting_{setting_key}"] = forms.CharField(
                label=label,
                max_length=512,
                widget=forms.TextInput(attrs={"class": "input"}),
            )
        if not self.is_bound:
            for setting_key, _ in BRANDING_SETTING_FIELDS:
                default = APP_TITLE_DEFAULT if setting_key == APP_TITLE_SETTING_KEY else ""
                self.fields[f"setting_{setting_key}"].initial = get_setting(setting_key, default)

    def save(self):
        for setting_key, description in BRANDING_SETTING_FIELDS:
            set_setting(
                setting_key,
                self.cleaned_data[f"setting_{setting_key}"],
                description,
            )


class SystemMenuLabelSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = {} if self.is_bound else get_menu_labels()
        for key, default, description in MENU_LABEL_FIELDS:
            self.fields[f"menu_{key}"] = forms.CharField(
                label=description,
                max_length=64,
                initial=current.get(key),
                help_text=f"Προεπιλογή: «{default}».",
                widget=forms.TextInput(attrs={"class": "input"}),
            )

    def save(self):
        for key, _, description in MENU_LABEL_FIELDS:
            save_menu_label(key, self.cleaned_data[f"menu_{key}"], description)


class SystemWorkflowSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for setting_key, label in WORKFLOW_SETTING_FIELDS:
            self.fields[f"setting_{setting_key}"] = forms.CharField(
                label=label,
                max_length=512,
                widget=forms.TextInput(attrs={"class": "input"}),
            )
        self.fields[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"] = forms.IntegerField(
            label="Ημέρες υπενθύμισης προθεσμίας διαβουλεύσεων (Dashboard)",
            min_value=0,
            widget=forms.NumberInput(attrs={"class": "input"}),
            help_text="Πόσες ημέρες πριν από την προθεσμία απάντησης εμφανίζεται υπενθύμιση.",
        )
        if not self.is_bound:
            for setting_key, _ in WORKFLOW_SETTING_FIELDS:
                self.fields[f"setting_{setting_key}"].initial = get_setting(setting_key, "")
            self.fields[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"].initial = get_setting(
                CONSULTATION_DUE_REMINDER_DAYS_KEY,
                str(CONSULTATION_DUE_REMINDER_DAYS_DEFAULT),
            )

    def save(self):
        for setting_key, description in WORKFLOW_SETTING_FIELDS:
            set_setting(
                setting_key,
                self.cleaned_data[f"setting_{setting_key}"],
                description,
            )
        set_setting(
            CONSULTATION_DUE_REMINDER_DAYS_KEY,
            str(self.cleaned_data[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"]),
            "Ημέρες υπενθύμισης προθεσμίας διαβουλεύσεων (Dashboard)",
        )


class SystemSectionLabelSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_section_label_fields(self)

    def save(self):
        for section_key in CASE_SECTION_LABEL_KEYS:
            fname = form_field_name_for_section_label(section_key)
            save_case_section_label(section_key, self.cleaned_data[fname])


class SystemSubsectionLabelSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_subsection_label_fields(self)

    def save(self):
        for subsection_key in CASE_SUBSECTION_LABEL_KEYS:
            fname = form_field_name_for_subsection_label(subsection_key)
            save_case_subsection_label(subsection_key, self.cleaned_data[fname])


class SystemCaseLabelSettingsForm(forms.Form):
    """Section and subsection display titles on one screen (grouped by section)."""

    def __init__(self, *args, include_sections=True, include_subsections=True, **kwargs):
        super().__init__(*args, **kwargs)
        if include_sections:
            _add_section_label_fields(self, compact=True)
        if include_subsections:
            _add_subsection_label_fields(self, compact=True)

    def save(self, *, save_sections=True, save_subsections=True):
        if save_sections:
            for section_key in CASE_SECTION_LABEL_KEYS:
                fname = form_field_name_for_section_label(section_key)
                if fname in self.cleaned_data:
                    save_case_section_label(section_key, self.cleaned_data[fname])
        if save_subsections:
            for subsection_key in CASE_SUBSECTION_LABEL_KEYS:
                fname = form_field_name_for_subsection_label(subsection_key)
                if fname in self.cleaned_data:
                    save_case_subsection_label(subsection_key, self.cleaned_data[fname])


class SystemEmailSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for setting_key, field in _email_setting_fields().items():
            field.widget.attrs.setdefault("class", "input")
            self.fields[email_field_name(setting_key)] = field
        if not self.is_bound:
            for setting_key, default in EMAIL_SETTING_DEFAULTS.items():
                if setting_key != "smtpPassword":
                    self.fields[email_field_name(setting_key)].initial = get_setting(
                        setting_key, default
                    )

    def save(self):
        for setting_key in EMAIL_SETTING_DEFAULTS:
            field_name = email_field_name(setting_key)
            value = self.cleaned_data[field_name]
            if setting_key == "smtpPassword" and not value:
                continue
            set_setting(setting_key, str(value), str(self.fields[field_name].label))


class SystemConfigurationForm(forms.Form):
    """All settings fields (used in tests and bulk scenarios)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_section_label_fields(self)
        _add_subsection_label_fields(self)
        for setting_key, label in GENERAL_SETTING_FIELDS:
            self.fields[f"setting_{setting_key}"] = forms.CharField(
                label=label,
                max_length=512,
                widget=forms.TextInput(attrs={"class": "input"}),
            )
        self.fields[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"] = forms.IntegerField(
            label="Ημέρες υπενθύμισης προθεσμίας διαβουλεύσεων (Dashboard)",
            min_value=0,
            widget=forms.NumberInput(attrs={"class": "input"}),
            help_text="Πόσες ημέρες πριν από την προθεσμία απάντησης εμφανίζεται υπενθύμιση.",
        )
        for setting_key, field in _email_setting_fields().items():
            field.widget.attrs.setdefault("class", "input")
            self.fields[email_field_name(setting_key)] = field
        if not self.is_bound:
            for setting_key, _ in GENERAL_SETTING_FIELDS:
                default = APP_TITLE_DEFAULT if setting_key == APP_TITLE_SETTING_KEY else ""
                self.fields[f"setting_{setting_key}"].initial = get_setting(setting_key, default)
            self.fields[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"].initial = get_setting(
                CONSULTATION_DUE_REMINDER_DAYS_KEY,
                str(CONSULTATION_DUE_REMINDER_DAYS_DEFAULT),
            )
            for setting_key, default in EMAIL_SETTING_DEFAULTS.items():
                if setting_key != "smtpPassword":
                    self.fields[email_field_name(setting_key)].initial = get_setting(
                        setting_key, default
                    )

    def save(self):
        for section_key in CASE_SECTION_LABEL_KEYS:
            fname = form_field_name_for_section_label(section_key)
            save_case_section_label(section_key, self.cleaned_data[fname])
        for subsection_key in CASE_SUBSECTION_LABEL_KEYS:
            fname = form_field_name_for_subsection_label(subsection_key)
            save_case_subsection_label(subsection_key, self.cleaned_data[fname])
        for setting_key, description in GENERAL_SETTING_FIELDS:
            set_setting(
                setting_key,
                self.cleaned_data[f"setting_{setting_key}"],
                description,
            )
        set_setting(
            CONSULTATION_DUE_REMINDER_DAYS_KEY,
            str(self.cleaned_data[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"]),
            "Ημέρες υπενθύμισης προθεσμίας διαβουλεύσεων (Dashboard)",
        )
        for setting_key in EMAIL_SETTING_DEFAULTS:
            field_name = email_field_name(setting_key)
            value = self.cleaned_data[field_name]
            if setting_key == "smtpPassword" and not value:
                continue
            set_setting(setting_key, str(value), str(self.fields[field_name].label))
