from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from plot_applications.parameters import INCOME_LIMIT_SETTINGS, income_limit_setting

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
from cases.services import (
    CASE_NUMBER_PREFIX_DEFAULT,
    CASE_NUMBER_PREFIX_KEY,
    DEFICIENCY_EMAIL_SUBJECT_DEFAULT,
    DEFICIENCY_EMAIL_SUBJECT_KEY,
    LAND_PLOT_EMAIL_SUBJECT_DEFAULT,
    LAND_PLOT_EMAIL_SUBJECT_KEY,
)
from core.branding import APP_TITLE_DEFAULT, APP_TITLE_SETTING_KEY
from core.docx_merge import (
    AGREEMENT_DISTRICT_OFFICER_DEFAULT,
    AGREEMENT_DISTRICT_OFFICER_KEY,
)
from core.menu_labels import MENU_LABEL_FIELDS, get_menu_labels, save_menu_label
from core.reminders import (
    CONSULTATION_DUE_REMINDER_DAYS_DEFAULT,
    CONSULTATION_DUE_REMINDER_DAYS_KEY,
)
from core.services import SMTP_SECURITY_CHOICES, SMTP_SETTING_DEFAULTS, get_setting, set_setting
from plot_applications.announcement_workflow import (
    WORKFLOW_EMAIL_DEFAULTS,
    WORKFLOW_EMAIL_TEMPLATES,
)
from plot_applications.grid_settings import (
    PLOT_APPLICATION_GRID_COLUMNS,
    get_plot_application_grid_columns,
    get_plot_application_grid_locked_columns,
    save_plot_application_grid_columns,
    save_plot_application_grid_locked_columns,
)
from plot_applications.stage_labels import (
    DEFAULT_APPLICATION_STAGE_LABELS,
    get_application_stage_label,
    save_application_stage_label,
)

BRANDING_SETTING_FIELDS = (
    (APP_TITLE_SETTING_KEY, "Τίτλος εφαρμογής (κεφαλίδα, πάνω αριστερά)"),
)
WORKFLOW_SETTING_FIELDS = (
    ("applicationFolderPrefix", "Πρόθεμα Αρ. Φακέλου Αιτητή (10.1.1)"),
    ("folderSequenceDigits", "Πλήθος ψηφίων ακολουθίας ανά Κοινότητα"),
    (CASE_NUMBER_PREFIX_KEY, "Πρόθεμα αριθμού υπόθεσης (1.1)"),
    (
        AGREEMENT_DISTRICT_OFFICER_KEY,
        "Έπαρχος στη Συμφωνία Παραχώρησης (Παράρτημα 4, Ενότ. 12)",
    ),
)
SETTING_FIELD_DEFAULTS = {
    APP_TITLE_SETTING_KEY: APP_TITLE_DEFAULT,
    CASE_NUMBER_PREFIX_KEY: CASE_NUMBER_PREFIX_DEFAULT,
    AGREEMENT_DISTRICT_OFFICER_KEY: AGREEMENT_DISTRICT_OFFICER_DEFAULT,
}
SETTING_FIELD_HELP_TEXTS = {
    CASE_NUMBER_PREFIX_KEY: (
        "Ο αριθμός υπόθεσης σχηματίζεται αυτόματα ως "
        "«πρόθεμα.αριθμός φακέλου Κοινότητας.αύξων αριθμός ανά Κοινότητα»."
    ),
    AGREEMENT_DISTRICT_OFFICER_KEY: (
        "Κείμενο που αντικαθιστά τα πεδία «του Επάρχου» και «ΕΠΕΙΔΗ ο/η Έπαρχος» "
        "στη Συμφωνία Παραχώρησης Οικοπέδου (Παράρτημα 4, Ενότ. 12)."
    ),
}
GENERAL_SETTING_FIELDS = (*BRANDING_SETTING_FIELDS, *WORKFLOW_SETTING_FIELDS)
EMAIL_SETTING_DEFAULTS = {
    **SMTP_SETTING_DEFAULTS,
    DEFICIENCY_EMAIL_SUBJECT_KEY: DEFICIENCY_EMAIL_SUBJECT_DEFAULT,
    LAND_PLOT_EMAIL_SUBJECT_KEY: LAND_PLOT_EMAIL_SUBJECT_DEFAULT,
    **WORKFLOW_EMAIL_DEFAULTS,
}


def _email_setting_fields():
    """SMTP server and email texts; keyed by the SystemSetting key."""
    fields = {
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
        LAND_PLOT_EMAIL_SUBJECT_KEY: forms.CharField(
            label="Θέμα email τεμαχίου (3.1)",
            max_length=255,
            help_text=(
                "Μπορεί να περιέχει {parcel_number} (αρ. τεμαχίου), {case_number} "
                "(αριθμός υπόθεσης) και {community} (Κοινότητα)."
            ),
        ),
    }
    for key, label, _default, help_text in WORKFLOW_EMAIL_TEMPLATES:
        is_body = key.endswith("Body")
        fields[key] = forms.CharField(
            label=label,
            max_length=4000 if is_body else 255,
            required=False,
            help_text=help_text,
            widget=forms.Textarea(attrs={"class": "input", "rows": 3})
            if is_body
            else forms.TextInput(attrs={"class": "input"}),
        )
    return fields


def income_limit_field_name(setting_key):
    return f"setting_{setting_key}"


def _add_income_limit_fields(form):
    """10.4.6 income limits per family size (positive amounts in €)."""
    for setting_key, default, label in INCOME_LIMIT_SETTINGS:
        field_name = income_limit_field_name(setting_key)
        form.fields[field_name] = forms.DecimalField(
            label=label,
            max_digits=12,
            decimal_places=2,
            validators=[
                MinValueValidator(
                    Decimal("0.01"), message="Το όριο εισοδήματος πρέπει να είναι θετικό ποσό."
                )
            ],
            help_text=f"Προεπιλογή: {default} €.",
            widget=forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0.01"}),
        )
        if not form.is_bound:
            form.fields[field_name].initial = income_limit_setting(setting_key)


def _save_income_limit_fields(form):
    for setting_key, _default, label in INCOME_LIMIT_SETTINGS:
        field_name = income_limit_field_name(setting_key)
        if field_name in form.cleaned_data:
            set_setting(setting_key, str(form.cleaned_data[field_name]), label)


def email_field_name(setting_key):
    return f"email_{setting_key}"


def _add_section_label_fields(form, *, compact=False):
    for section_key in CASE_SECTION_LABEL_KEYS:
        field_name = form_field_name_for_section_label(section_key)
        default = DEFAULT_CASE_SECTION_LABELS.get(section_key, section_key)
        if compact:
            label = f"Ενότητα {case_section_number(section_key)}"
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


class SystemPlotApplicationGridSettingsForm(forms.Form):
    """Ρυθμίσεις πίνακα αιτήσεων παραχώρησης οικοπέδου (ορατές στήλες και κλειδωμένες στήλες)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_locked = len(PLOT_APPLICATION_GRID_COLUMNS)
        self.fields["grid_columns"] = forms.MultipleChoiceField(
            label="Ορατές στήλες πίνακα",
            choices=PLOT_APPLICATION_GRID_COLUMNS,
            required=True,
            initial=None if self.is_bound else get_plot_application_grid_columns(),
            error_messages={
                "required": "Επιλέξτε τουλάχιστον μία στήλη για εμφάνιση στον πίνακα.",
            },
            help_text="Επιλέξτε ποιες στήλες εμφανίζονται στον πίνακα των αιτήσεων παραχώρησης οικοπέδου.",
            widget=forms.CheckboxSelectMultiple(attrs={"class": "checkbox-list"}),
        )
        self.fields["locked_columns"] = forms.IntegerField(
            label="Κλειδωμένες στήλες από την αρχή (για οριζόντια κύλιση)",
            min_value=0,
            max_value=max_locked,
            required=True,
            initial=None if self.is_bound else get_plot_application_grid_locked_columns(),
            help_text=(
                "Πόσες από τις πρώτες ορατές στήλες παραμένουν σταθερές (locked) "
                "κατά την οριζόντια κύλιση του πίνακα (0 = καμία)."
            ),
            widget=forms.NumberInput(
                attrs={"class": "input", "min": "0", "max": str(max_locked)}
            ),
        )

    def save(self):
        save_plot_application_grid_columns(self.cleaned_data["grid_columns"])
        save_plot_application_grid_locked_columns(self.cleaned_data["locked_columns"])


class SystemPlotApplicationLabelSettingsForm(forms.Form):
    """Τίτλοι εμφάνισης των σταδίων και ρυθμίσεις πίνακα της αίτησης παραχώρησης οικοπέδου."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for number, (stage, default) in enumerate(DEFAULT_APPLICATION_STAGE_LABELS.items(), start=1):
            self.fields[f"stage_{stage}"] = forms.CharField(
                label=f"Στάδιο {number}",
                max_length=128,
                initial=None if self.is_bound else get_application_stage_label(stage),
                help_text=f"Προεπιλογή: «{default}».",
                widget=forms.TextInput(attrs={"class": "input"}),
            )
        self._has_grid_payload = bool(
            self.is_bound
            and ("locked_columns" in self.data or "grid_columns" in self.data)
        )
        max_locked = len(PLOT_APPLICATION_GRID_COLUMNS)
        self.fields["grid_columns"] = forms.MultipleChoiceField(
            label="Ορατές στήλες πίνακα",
            choices=PLOT_APPLICATION_GRID_COLUMNS,
            required=self._has_grid_payload,
            initial=None if self.is_bound else get_plot_application_grid_columns(),
            error_messages={
                "required": "Επιλέξτε τουλάχιστον μία στήλη για εμφάνιση στον πίνακα.",
            },
            help_text="Επιλέξτε ποιες στήλες εμφανίζονται στον πίνακα των αιτήσεων παραχώρησης οικοπέδου.",
            widget=forms.CheckboxSelectMultiple(attrs={"class": "checkbox-list"}),
        )
        self.fields["locked_columns"] = forms.IntegerField(
            label="Κλειδωμένες στήλες από την αρχή (για οριζόντια κύλιση)",
            min_value=0,
            max_value=max_locked,
            required=self._has_grid_payload,
            initial=None if self.is_bound else get_plot_application_grid_locked_columns(),
            help_text=(
                "Πόσες από τις πρώτες ορατές στήλες παραμένουν σταθερές (locked) "
                "κατά την οριζόντια κύλιση του πίνακα (0 = καμία)."
            ),
            widget=forms.NumberInput(
                attrs={"class": "input", "min": "0", "max": str(max_locked)}
            ),
        )

    def save(self):
        for stage in DEFAULT_APPLICATION_STAGE_LABELS:
            save_application_stage_label(stage, self.cleaned_data[f"stage_{stage}"])
        if self._has_grid_payload:
            save_plot_application_grid_columns(self.cleaned_data["grid_columns"])
            if self.cleaned_data.get("locked_columns") is not None:
                save_plot_application_grid_locked_columns(self.cleaned_data["locked_columns"])


class SystemWorkflowSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for setting_key, label in WORKFLOW_SETTING_FIELDS:
            self.fields[f"setting_{setting_key}"] = forms.CharField(
                label=label,
                max_length=512,
                help_text=SETTING_FIELD_HELP_TEXTS.get(setting_key, ""),
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
                self.fields[f"setting_{setting_key}"].initial = get_setting(
                    setting_key, SETTING_FIELD_DEFAULTS.get(setting_key, "")
                )
            self.fields[f"setting_{CONSULTATION_DUE_REMINDER_DAYS_KEY}"].initial = get_setting(
                CONSULTATION_DUE_REMINDER_DAYS_KEY,
                str(CONSULTATION_DUE_REMINDER_DAYS_DEFAULT),
            )
        _add_income_limit_fields(self)

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
        _save_income_limit_fields(self)


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
            value = self.cleaned_data.get(field_name)
            if setting_key == "smtpPassword" and not value:
                continue
            if setting_key in WORKFLOW_EMAIL_DEFAULTS and not value:
                if field_name not in self.data:
                    continue
                value = WORKFLOW_EMAIL_DEFAULTS[setting_key]
            set_setting(setting_key, str(value), str(self.fields[field_name].label))


class AgreementTemplateUploadForm(forms.Form):
    """Μεταφόρτωση προτύπου Συμφωνίας Παραχώρησης (.docx, Παράρτημα 4)."""

    name = forms.CharField(
        label="Ονομασία προτύπου",
        max_length=255,
        initial="Συμφωνία Παραχώρησης Οικοπέδου (Παράρτημα 4)",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    version = forms.CharField(
        label="Έκδοση",
        max_length=64,
        required=False,
        initial="v1",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    template_file = forms.FileField(
        label="Αρχείο Word (.docx)",
        help_text="Αρχείο .docx με πεδία {{placeholders}} (π.χ. {{applicant_name}}, {{plot_number}}, {{disposal_price}}).",
    )
    is_active = forms.BooleanField(
        label="Ορισμός ως ενεργό πρότυπο",
        required=False,
        initial=True,
    )

    def clean_template_file(self):
        from core.docx_merge import validate_agreement_template_file

        uploaded = self.cleaned_data["template_file"]
        name = (getattr(uploaded, "name", "") or "").lower()
        if not name.endswith(".docx"):
            raise forms.ValidationError("Επιτρέπονται μόνο αρχεία Word (.docx).")
        validate_agreement_template_file(uploaded)
        return uploaded

    def save(self):
        from allocation.models import AgreementTemplate

        is_active = bool(self.cleaned_data.get("is_active", True))
        if is_active:
            for existing in AgreementTemplate.objects.filter(is_active=True):
                existing.is_active = False
                existing.save(update_fields=["is_active", "updated_at"])
        return AgreementTemplate.objects.create(
            name=self.cleaned_data["name"].strip(),
            version=(self.cleaned_data.get("version") or "").strip(),
            template_file=self.cleaned_data["template_file"],
            is_active=is_active,
        )


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
                help_text=SETTING_FIELD_HELP_TEXTS.get(setting_key, ""),
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
        _add_income_limit_fields(self)
        if not self.is_bound:
            for setting_key, _ in GENERAL_SETTING_FIELDS:
                self.fields[f"setting_{setting_key}"].initial = get_setting(
                    setting_key, SETTING_FIELD_DEFAULTS.get(setting_key, "")
                )
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
        _save_income_limit_fields(self)
        for setting_key in EMAIL_SETTING_DEFAULTS:
            field_name = email_field_name(setting_key)
            value = self.cleaned_data.get(field_name)
            if setting_key == "smtpPassword" and not value:
                continue
            if setting_key in WORKFLOW_EMAIL_DEFAULTS and not value:
                if field_name not in self.data:
                    continue
                value = WORKFLOW_EMAIL_DEFAULTS[setting_key]
            set_setting(setting_key, str(value), str(self.fields[field_name].label))
