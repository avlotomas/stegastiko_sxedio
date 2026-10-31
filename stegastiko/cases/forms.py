from django import forms
from django.db.models import Q

from applications.models import Person
from cases import section_refs as refs
from cases.models import (
    ApprovedDesignPlot,
    Case,
    CompletenessCheck,
    Consultation,
    Field,
    InfrastructureCheck,
    LandPlot,
    UtilityService,
    MinistryDecisionRound,
    UtilityServiceType,
    ValuationReferral,
    YesNo,
)
from core.forms import IsoDateInput, MultipleFileField, apply_greek_labels
from core.models import Attachment, Community


class StyledFormMixin:
    """Apply the shared input styling and Greek labels used across the case forms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "checkbox")
            elif isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
                # A list of choices must not get the full-width text-input styling.
                field.widget.attrs.setdefault("class", "checkbox-list")
            elif not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", "input")
        apply_greek_labels(self)


class OtherChoiceFieldsMixin:
    """«Άλλο» choices whose description is written in the same cell (§Α.5).

    The description is required while "other" is selected and cleared otherwise; the
    previous value stays in the action history.
    """

    # choice field name -> (description field name, message when it is missing)
    OTHER_TEXT_FIELDS = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for other_name, _ in self.OTHER_TEXT_FIELDS.values():
            field = self.fields[other_name]
            field.widget.attrs["aria-label"] = field.label

    def clean(self):
        cleaned_data = super().clean()
        for choice_name, (other_name, message) in self.OTHER_TEXT_FIELDS.items():
            if cleaned_data.get(choice_name) == "other":
                if not (cleaned_data.get(other_name) or "").strip():
                    self.add_error(other_name, message)
            else:
                cleaned_data[other_name] = ""
        return cleaned_data


class AttachmentsFormMixin:
    """Files kept on the form's instance: add new ones and remove existing ones.

    Must come after StyledFormMixin in the bases so the added fields get styled too.
    """

    attachment_section_ref = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_files"] = MultipleFileField(required=False, label="Επισύναψη αρχείων")
        if self.instance.pk:
            remove = forms.ModelMultipleChoiceField(
                queryset=self.existing_attachments(),
                required=False,
                widget=forms.CheckboxSelectMultiple,
                label="Αφαίρεση αρχείων",
            )
            remove.label_from_instance = lambda attachment: attachment.filename
            self.fields["remove_attachments"] = remove

    def existing_attachments(self):
        return self.instance.attachments.filter(section_ref=self.attachment_section_ref)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            self.save_attachments()
        return instance

    def save_attachments(self):
        for attachment in self.cleaned_data.get("remove_attachments") or []:
            attachment._section_ref = self.attachment_section_ref
            attachment.delete()
        for upload in self.cleaned_data.get("new_files") or []:
            Attachment(
                content_object=self.instance,
                section_ref=self.attachment_section_ref,
                filename=upload.name,
                content_type_name=upload.content_type or "application/octet-stream",
                data=upload.read(),
            ).save()


class AttachmentSlotsMixin:
    """Several separate file slots on the form's instance, told apart by section_ref.

    Placed before StyledFormMixin in the bases, the added file fields stay unstyled.
    """

    # section_ref -> (new files field, remove field, label of the new files field)
    ATTACHMENT_SLOTS = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for section_ref, (new_field, remove_field, label) in self.ATTACHMENT_SLOTS.items():
            self.fields[new_field] = MultipleFileField(required=False, label=label)
            if self.instance.pk:
                remove = forms.ModelMultipleChoiceField(
                    queryset=self.instance.attachments.filter(section_ref=section_ref),
                    required=False,
                    widget=forms.CheckboxSelectMultiple,
                    label="Αφαίρεση αρχείων",
                )
                remove.label_from_instance = lambda attachment: attachment.filename
                self.fields[remove_field] = remove

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            for section_ref, (new_field, remove_field, _) in self.ATTACHMENT_SLOTS.items():
                self._save_attachment_slot(section_ref, new_field, remove_field)
        return instance

    def _save_attachment_slot(self, section_ref, new_field, remove_field):
        for attachment in self.cleaned_data.get(remove_field) or []:
            attachment._section_ref = section_ref
            attachment.delete()
        for upload in self.cleaned_data.get(new_field) or []:
            Attachment(
                content_object=self.instance,
                section_ref=section_ref,
                filename=upload.name,
                content_type_name=upload.content_type or "application/octet-stream",
                data=upload.read(),
            ).save()


class CaseCreateForm(StyledFormMixin, forms.ModelForm):
    """§1.1–1.2 on create; case number and start date are automatic."""

    class Meta:
        model = Case
        fields = [
            "community",
            "submitted_at",
            "contact_email",
            "priority_turkish_cypriot_properties",
            "priority_protection_zones",
            "priority_nuisance_developments",
            "priority_limited_private_land",
            "priority_other",
            "priority_documentation",
        ]
        widgets = {
            "submitted_at": IsoDateInput(),
            "priority_documentation": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["community"].queryset = Community.objects.filter(is_active=True)
        self.fields["community"].label = "Κοινότητα / Δ.Δ."
        self.fields["submitted_at"].required = True

    def _apply_community_contact_email_default(self):
        """Pre-fill from community before required-field validation (create screen JS does the same)."""
        if not self.is_bound:
            return
        email = (self.data.get("contact_email") or "").strip()
        community_id = self.data.get("community")
        if email or not community_id:
            return
        community = Community.objects.filter(pk=community_id, is_active=True).first()
        if not community or not (community.contact_email or "").strip():
            return
        data = self.data.copy()
        data["contact_email"] = community.contact_email
        self.data = data

    def full_clean(self):
        self._apply_community_contact_email_default()
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        if not (cleaned_data.get("contact_email") or "").strip():
            self.add_error(
                "contact_email",
                "Απαιτείται ηλεκτρονική διεύθυνση επικοινωνίας Κ.Σ./Δ.Δ. (1.1).",
            )
        return cleaned_data


class Section1Form(StyledFormMixin, forms.ModelForm):
    """§1.1–1.3: editable operator fields; basic 1.1 identifiers are shown read-only in the template."""

    class Meta:
        model = Case
        fields = [
            "submitted_at",
            "contact_email",
            "priority_turkish_cypriot_properties",
            "priority_protection_zones",
            "priority_nuisance_developments",
            "priority_limited_private_land",
            "priority_other",
            "priority_documentation",
            "comments",
        ]
        widgets = {
            "submitted_at": IsoDateInput(),
            "priority_documentation": forms.Textarea(attrs={"rows": 3}),
            "comments": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact_email"].required = True
        self.fields["submitted_at"].required = True


class Section2Form(StyledFormMixin, forms.ModelForm):
    """2 Only the section comments; the checks themselves are a repeating table."""

    class Meta:
        model = Case
        fields = ["section2_comments"]
        widgets = {"section2_comments": forms.Textarea(attrs={"rows": 3})}


class CompletenessCheckForm(StyledFormMixin, forms.ModelForm):
    """2.1 One dated check row, edited from the section 2 modal."""

    class Meta:
        model = CompletenessCheck
        fields = ["check_date", "result", "deficiencies"]
        widgets = {
            "check_date": IsoDateInput(),
            "result": forms.Select(attrs={"data-completeness-result": ""}),
            "deficiencies": forms.Textarea(attrs={"rows": 5}),
        }

    def clean(self):
        cleaned_data = super().clean()
        result = cleaned_data.get("result")
        if result == YesNo.NO and not (cleaned_data.get("deficiencies") or "").strip():
            self.add_error(
                "deficiencies",
                "Για αποτέλεσμα ΟΧΙ πρέπει να καταχωριστούν οι ελλείψεις (Ενότητα 2).",
            )
        elif result == YesNo.YES:
            # 2.2 applies only to ΟΧΙ; earlier deficiencies stay in the action history.
            cleaned_data["deficiencies"] = ""
        return cleaned_data


class DeficiencyEmailForm(forms.Form):
    """2.2 Email of the deficiencies; the recipient is always the 1.1 contact address."""

    subject = forms.CharField(
        label="Θέμα",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    body = forms.CharField(
        label="Κείμενο",
        required=False,
        widget=forms.Textarea(attrs={"class": "input", "rows": 10, "data-email-body": ""}),
    )


class Section3Form(StyledFormMixin, forms.ModelForm):
    """3.2 State-land check and 3.3 comments; the 3.1 plots are the inline formset."""

    class Meta:
        model = Case
        fields = ["state_land_remains_sufficient", "section3_comments"]
        widgets = {
            "section3_comments": forms.Textarea(attrs={"rows": 3}),
        }


class Section4Form(StyledFormMixin, AttachmentsFormMixin, forms.ModelForm):
    """4.3 access, 4.4 files, 4.5 comments and 4.6 visit details.

    4.1 and 4.2 rows are edited one at a time from their grid modals.
    """

    attachment_section_ref = refs.REF_TECHNICAL_FILES

    class Meta:
        model = Case
        fields = [
            "access_technical_evaluation",
            "section4_comments",
            "engineer_full_name",
            "technical_visit_date",
        ]
        widgets = {
            "access_technical_evaluation": forms.Textarea(attrs={"rows": 3}),
            "section4_comments": forms.Textarea(attrs={"rows": 3}),
            "technical_visit_date": IsoDateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["access_technical_evaluation"].label = ""
        self.fields["section4_comments"].label = ""


class Section6Form(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Case
        fields = []


class MinistryDecisionRoundForm(
    OtherChoiceFieldsMixin, AttachmentSlotsMixin, StyledFormMixin, forms.ModelForm
):
    """6.7 One ministry decision row in the grid modal."""

    ATTACHMENT_SLOTS = {
        MinistryDecisionRound.ATTACHMENT_SECTION_RECOMMENDATION: (
            "new_recommendation_files",
            "remove_recommendation_attachments",
            "Επισυναπτόμενο έγγραφο σύστασης",
        ),
        MinistryDecisionRound.ATTACHMENT_SECTION_RESPONSE: (
            "new_response_files",
            "remove_response_attachments",
            "Επισυναπτόμενο έγγραφο απάντησης",
        ),
    }

    OTHER_TEXT_FIELDS = {
        "recommendation": (
            "recommendation_other",
            "Συμπληρώστε τη σύσταση όταν επιλέγετε «Άλλο» (6.7).",
        ),
        "ministry_decision": (
            "ministry_decision_other",
            "Συμπληρώστε την απόφαση όταν επιλέγετε «Άλλο» (6.7).",
        ),
    }

    class Meta:
        model = MinistryDecisionRound
        fields = [
            "letter_sent_date",
            "recommendation",
            "recommendation_other",
            "ministry_response_date",
            "ministry_decision",
            "ministry_decision_other",
            "comments",
        ]
        widgets = {
            "letter_sent_date": IsoDateInput(),
            "ministry_response_date": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 3}),
            "recommendation_other": forms.TextInput(
                attrs={"placeholder": "Περιγραφή σύστασης", "data-other-input": ""}
            ),
            "ministry_decision_other": forms.TextInput(
                attrs={"placeholder": "Περιγραφή απόφασης", "data-other-input": ""}
            ),
        }


class Section7Form(AttachmentSlotsMixin, StyledFormMixin, forms.ModelForm):
    """7.1-7.7 single-row blocks of the division workflow; 7.2, 7.3 and 7.7 keep their own files."""

    ATTACHMENT_SLOTS = {
        Case.ATTACHMENT_SECTION_DIVISION_DESIGN: (
            "new_division_design_files",
            "remove_division_design_attachments",
            "Επισυναπτόμενα έγγραφα",
        ),
        Case.ATTACHMENT_SECTION_TPO_APPLICATION: (
            "new_tpo_application_files",
            "remove_tpo_application_attachments",
            "Επισυναπτόμενα έγγραφα",
        ),
        Case.ATTACHMENT_SECTION_DLS_APPLICATION: (
            "new_dls_application_files",
            "remove_dls_application_attachments",
            "Επισυναπτόμενα έγγραφα",
        ),
    }

    class Meta:
        model = Case
        fields = [
            "survey_assignment_date",
            "surveyor_name",
            "surveyor_phone",
            "surveyor_email",
            "survey_assignment_comments",
            "division_design_status",
            "division_design_completed_on",
            "division_design_plots_count",
            "division_design_comments",
            "tpo_application_date",
            "tpo_application_number",
            "tpo_response",
            "tpo_response_date",
            "tpo_comments",
            "construction_plans_stage",
            "land_expropriation_required",
            "tender_announcement_date",
            "tender_award_date",
            "contractor_name",
            "contractor_phone",
            "contractor_email",
            "contract_duration_value",
            "tender_comments",
            "dls_application_date",
            "dls_file_number",
            "dls_response_date",
            "dls_comments",
        ]
        widgets = {
            "survey_assignment_date": IsoDateInput(),
            "division_design_completed_on": IsoDateInput(),
            "tpo_application_date": IsoDateInput(),
            "tpo_response_date": IsoDateInput(),
            "tender_announcement_date": IsoDateInput(),
            "tender_award_date": IsoDateInput(),
            "dls_application_date": IsoDateInput(),
            "dls_response_date": IsoDateInput(),
            "survey_assignment_comments": forms.Textarea(attrs={"rows": 2}),
            "division_design_comments": forms.Textarea(attrs={"rows": 2}),
            "tpo_comments": forms.Textarea(attrs={"rows": 2}),
            "construction_plans_stage": forms.Textarea(attrs={"rows": 3}),
            "tender_comments": forms.Textarea(attrs={"rows": 2}),
            "dls_comments": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        # 7.5 uses a single duration field and the unit is fixed to months.
        self.instance.contract_duration_unit = Case.ContractDurationUnit.MONTHS
        return cleaned_data


class ApprovedDesignPlotForm(OtherChoiceFieldsMixin, StyledFormMixin, forms.ModelForm):
    """7.3 One row of «Στοιχεία Εγκεκριμένου Σχεδιασμού Οικοπέδων» in the grid modal."""

    OTHER_TEXT_FIELDS = {
        "plot_type": ("plot_type_other", "Συμπληρώστε τον τύπο όταν επιλέγετε «Άλλο» (7.3)."),
    }

    class Meta:
        model = ApprovedDesignPlot
        fields = [
            "plot_type",
            "plot_type_other",
            "design_number",
            "source_land_plots",
        ]
        widgets = {
            "plot_type_other": forms.TextInput(
                attrs={"placeholder": "Περιγραφή τύπου", "data-other-input": ""}
            ),
            "source_land_plots": forms.CheckboxSelectMultiple,
        }

    PLOT_TYPE_LOCKED_MESSAGE = (
        "Το οικόπεδο έχει ήδη καταχωριστεί στα Οικόπεδα με την ολοκλήρωση της αίτησης· "
        "ο τύπος του δεν μπορεί να αλλάξει (7.3)."
    )

    def __init__(self, *args, land_plots=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plot_type"].choices = [
            ("", "— Επιλέξτε τύπο —"),
            *ApprovedDesignPlot.PlotType.choices,
        ]
        # Only the parcels of the same case (3.1) can be the origin; none, one or many.
        # The grid passes `land_plots` once for all its rows.
        if land_plots is None:
            land_plots = list(self.instance.case.land_plots.all()) if self.instance.case_id else []
        if land_plots:
            field = self.fields["source_land_plots"]
            field.queryset = LandPlot.objects.filter(case_id=self.instance.case_id)
            field.choices = [(plot.pk, plot.short_label) for plot in land_plots]
            field.help_text = ""
        else:
            del self.fields["source_land_plots"]
        # A row that already became a completed plot must stay a "division plot".
        self.plot_type_locked = self.instance.generated_plot is not None
        if self.plot_type_locked:
            self.fields["plot_type"].help_text = self.PLOT_TYPE_LOCKED_MESSAGE

    def clean(self):
        cleaned_data = super().clean()
        new_type = cleaned_data.get("plot_type")
        if self.plot_type_locked and new_type and new_type != self.instance.plot_type:
            self.add_error("plot_type", self.PLOT_TYPE_LOCKED_MESSAGE)
        return cleaned_data


class ApprovedDesignPlotInlineForm(ApprovedDesignPlotForm):
    """Editable columns of the persistent approved-design-plots workspace."""

    class Meta(ApprovedDesignPlotForm.Meta):
        fields = [
            "plot_type",
            "plot_type_other",
            "design_number",
            "tkx_number",
            "title_deed_number",
            "parcel_number",
            "sheet_plan",
            "final_area_sqm",
            "numbering_status",
            "valuation_amount",
            "disposal_price",
            "source_land_plots",
        ]
        widgets = {
            **ApprovedDesignPlotForm.Meta.widgets,
            "final_area_sqm": forms.NumberInput(attrs={"step": "0.01"}),
            "valuation_amount": forms.NumberInput(attrs={"step": "0.01"}),
            "disposal_price": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_id = f"approved-design-plot-row-{self.instance.pk}"
        for name, field in self.fields.items():
            field.widget.attrs["form"] = form_id
            if name != "source_land_plots":  # each checkbox has its own label
                field.widget.attrs.setdefault("aria-label", field.label)

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("numbering_status") == ApprovedDesignPlot.NumberingStatus.TKX
            and not (cleaned_data.get("tkx_number") or "").strip()
        ):
            self.add_error("tkx_number", "Η Αρίθμηση ΤΚΧ απαιτείται για αυτή την κατάσταση.")
        return cleaned_data


def approved_design_plot_inline_rows(case, bound_form=None, plots=None):
    """Pair every plot with its row form, preserving one bound form after validation errors."""
    rows = []
    plot_rows = (
        plots
        if plots is not None
        else case.approved_design_plots.select_related("plot").prefetch_related(
            "source_land_plots"
        )
    )
    land_plots = list(case.land_plots.all())
    for plot in plot_rows:
        form = (
            bound_form
            if bound_form is not None and bound_form.instance.pk == plot.pk
            else ApprovedDesignPlotInlineForm(
                instance=plot, prefix=f"plot-{plot.pk}", land_plots=land_plots
            )
        )
        rows.append({"plot": plot, "form": form})
    return rows


def _numeric_design_number(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


class ApprovedDesignPlotBulkForm(OtherChoiceFieldsMixin, StyledFormMixin, forms.Form):
    """7.3 «Μαζική προσθήκη»: many rows of one type, numbered serially or by hand.

    Serial numbering continues after the highest numeric design number the case already
    has for the type; hand-typed numbers must not repeat an existing one.

    The hand-typed numbers arrive as repeated `manual_numbers` inputs (one per row).
    """

    MAX_COUNT = 500
    SERIAL = "serial"
    MANUAL = "manual"
    NUMBERING_MODE_CHOICES = [
        (SERIAL, "Σειριακή (συνέχεια μετά τον τελευταίο αριθμό)"),
        (MANUAL, "Χειροκίνητη"),
    ]

    OTHER_TEXT_FIELDS = {
        "plot_type": ("plot_type_other", "Συμπληρώστε τον τύπο όταν επιλέγετε «Άλλο» (7.3)."),
    }

    plot_type = forms.ChoiceField(label="Τύπος")
    plot_type_other = forms.CharField(
        label="Τύπος — Άλλο",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Περιγραφή τύπου", "data-other-input": ""}),
    )
    count = forms.IntegerField(
        label="Αριθμός εγγραφών",
        min_value=1,
        max_value=MAX_COUNT,
        widget=forms.NumberInput(attrs={"data-bulk-count": ""}),
    )
    numbering_mode = forms.ChoiceField(
        label="Αρίθμηση",
        choices=NUMBERING_MODE_CHOICES,
        initial=SERIAL,
        widget=forms.RadioSelect(attrs={"data-bulk-numbering-mode": ""}),
    )

    def __init__(self, *args, case=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Numbers continue after the rows the case already has (for the same type).
        self.case = case
        self.fields["plot_type"].choices = [
            ("", "— Επιλέξτε τύπο —"),
            *ApprovedDesignPlot.PlotType.choices,
        ]
        self.manual_numbers = (
            [value.strip() for value in self.data.getlist("manual_numbers")]
            if self.is_bound
            else []
        )

    @property
    def is_manual(self):
        return self.is_bound and self.data.get("numbering_mode") == self.MANUAL

    def existing_design_numbers(self, plot_type):
        if self.case is None or self.case.pk is None or not plot_type:
            return set()
        return set(
            ApprovedDesignPlot.objects.filter(case=self.case, plot_type=plot_type)
            .exclude(design_number="")
            .values_list("design_number", flat=True)
        )

    def clean(self):
        cleaned_data = super().clean()
        count = cleaned_data.get("count")
        if not count:
            return cleaned_data
        existing = self.existing_design_numbers(cleaned_data.get("plot_type"))
        if cleaned_data.get("numbering_mode") != self.MANUAL:
            numeric = [_numeric_design_number(number) for number in existing]
            self.serial_start = max((n for n in numeric if n is not None), default=0) + 1
            return cleaned_data
        numbers = self.manual_numbers
        max_length = ApprovedDesignPlot._meta.get_field("design_number").max_length
        if len(numbers) != count or not all(numbers):
            raise forms.ValidationError("Συμπληρώστε την αρίθμηση σε όλες τις γραμμές (7.3).")
        if any(len(number) > max_length for number in numbers):
            raise forms.ValidationError(
                f"Η αρίθμηση δεν μπορεί να υπερβαίνει τους {max_length} χαρακτήρες (7.3)."
            )
        if len(set(numbers)) != len(numbers):
            raise forms.ValidationError("Η αρίθμηση δεν μπορεί να επαναλαμβάνεται (7.3).")
        taken = sorted(set(numbers) & existing)
        if taken:
            raise forms.ValidationError(
                "Η αρίθμηση υπάρχει ήδη στην υπόθεση για αυτόν τον τύπο (7.3): "
                + ", ".join(taken)
            )
        return cleaned_data

    def design_numbers(self):
        if self.cleaned_data["numbering_mode"] == self.MANUAL:
            return list(self.manual_numbers)
        start = getattr(self, "serial_start", 1)
        return [str(number) for number in range(start, start + self.cleaned_data["count"])]

    def build_plots(self, case):
        return [
            ApprovedDesignPlot(
                case=case,
                plot_type=self.cleaned_data["plot_type"],
                plot_type_other=self.cleaned_data["plot_type_other"],
                design_number=number,
            )
            for number in self.design_numbers()
        ]


class SurveyingForm(StyledFormMixin, forms.ModelForm):
    """8.1 header block of the survey request sent to the Land Registry (ΤΚΧ)."""

    class Meta:
        model = Case
        fields = ["dls_application_date", "dls_file_number", "dls_response_date", "dls_comments"]
        widgets = {
            "dls_application_date": IsoDateInput(),
            "dls_response_date": IsoDateInput(),
            "dls_comments": forms.Textarea(attrs={"rows": 2}),
        }


class LandPlotForm(OtherChoiceFieldsMixin, StyledFormMixin, AttachmentsFormMixin, forms.ModelForm):
    """3.1 One row per land plot; «Άλλο» is written in the same cell and files stay on the plot."""

    attachment_section_ref = refs.REF_LAND_PLOTS
    OTHER_TEXT_FIELDS = {
        "ownership_status": ("ownership_other", "Συμπληρώστε το είδος της άλλης ιδιοκτησίας (3.1)."),
        "access": ("access_other", "Συμπληρώστε τη διευκρίνιση της πρόσβασης (3.1)."),
    }

    class Meta:
        model = LandPlot
        fields = [
            "parcel_number",
            "sheet_plan",
            "location",
            "ownership_status",
            "ownership_other",
            "area_sqm",
            "zone",
            "inside_development_zone",
            "access",
            "access_other",
            "rejected",
            "comments",
        ]
        widgets = {
            "ownership_other": forms.TextInput(
                attrs={"placeholder": "Είδος άλλης ιδιοκτησίας", "data-other-input": ""}
            ),
            "access_other": forms.TextInput(
                attrs={"placeholder": "Διευκρίνιση", "data-other-input": ""}
            ),
            "comments": forms.Textarea(attrs={"rows": 2}),
        }


class LandPlotEvaluationForm(OtherChoiceFieldsMixin, StyledFormMixin, forms.ModelForm):
    """4.1 Technical evaluation of one 3.1 plot; the plot itself is not editable here."""

    OTHER_TEXT_FIELDS = {
        "morphology": (
            "morphology_other",
            "Συμπληρώστε την περιγραφή της άλλης τεχνικής ιδιαιτερότητας (4.1).",
        ),
    }

    class Meta:
        model = LandPlot
        fields = list(LandPlot.TECHNICAL_EVALUATION_FIELDS)
        widgets = {
            "morphology_other": forms.TextInput(
                attrs={"placeholder": "Περιγραφή τεχνικής ιδιαιτερότητας", "data-other-input": ""}
            ),
            "morphology_comments": forms.Textarea(attrs={"rows": 2}),
        }


class LandPlotDecisionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LandPlot
        fields = ["suitability_decision", "suitability_justification"]
        widgets = {"suitability_justification": forms.Textarea(attrs={"rows": 2})}


class UtilityServiceForm(StyledFormMixin, forms.ModelForm):
    """4.2 One service row, edited from the grid modal."""

    class Meta:
        model = UtilityService
        fields = ["service_type", "proximity", "comments"]
        widgets = {"comments": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A deactivated value stays selectable on the rows that already use it.
        available = Q(is_active=True)
        if self.instance.service_type_id:
            available |= Q(pk=self.instance.service_type_id)
        field = self.fields["service_type"]
        field.queryset = UtilityServiceType.objects.filter(available)
        field.empty_label = "— Επιλέξτε υπηρεσία —"


class UtilityServiceTypeForm(StyledFormMixin, forms.ModelForm):
    """One row of the 4.2 service catalog; the column headers carry the labels."""

    class Meta:
        model = UtilityServiceType
        fields = ["name", "display_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["aria-label"] = field.label


class BaseUtilityServiceTypeFormSet(forms.BaseModelFormSet):
    def clean(self):
        super().clean()
        in_use = [
            form.instance.name
            for form in self.deleted_forms
            if form.instance.pk and form.instance.is_in_use
        ]
        if in_use:
            raise forms.ValidationError(
                [
                    f"Η υπηρεσία «{name}» χρησιμοποιείται σε υποθέσεις και δεν διαγράφεται· "
                    "απενεργοποιήστε την."
                    for name in in_use
                ]
            )


UtilityServiceTypeFormSet = forms.modelformset_factory(
    UtilityServiceType,
    form=UtilityServiceTypeForm,
    formset=BaseUtilityServiceTypeFormSet,
    extra=2,
    can_delete=True,
)


class ConsultationForm(
    OtherChoiceFieldsMixin, StyledFormMixin, AttachmentsFormMixin, forms.ModelForm
):
    """Ενότητα 5 / 7.4 — one consultation row in the grid modal.

    Status is derived from the response date, so it is not editable here.
    """

    OTHER_TEXT_FIELDS = {
        "department": ("department_other", "Δώστε περιγραφή για «Άλλο»."),
    }

    @property
    def attachment_section_ref(self):
        return self.instance.section_ref

    class Meta:
        model = Consultation
        fields = [
            "department",
            "department_other",
            "topic",
            "sent_date",
            "due_date",
            "response_date",
            "response_text",
            "comments",
        ]
        widgets = {
            "sent_date": IsoDateInput(),
            "due_date": IsoDateInput(),
            "response_date": IsoDateInput(),
            "topic": forms.Textarea(attrs={"rows": 3}),
            "response_text": forms.Textarea(attrs={"rows": 3}),
            "comments": forms.Textarea(attrs={"rows": 2}),
            "department_other": forms.TextInput(
                attrs={"placeholder": "Περιγραφή τμήματος / υπηρεσίας", "data-other-input": ""}
            ),
        }


YES_NO_BOOLEAN_CHOICES = ((True, "ΝΑΙ"), (False, "ΟΧΙ"))


class InfrastructureCheckForm(StyledFormMixin, forms.ModelForm):
    """7.6 One row of «Παρακολούθηση κατασκευαστικών εργασιών» in the grid modal."""

    class Meta:
        model = InfrastructureCheck
        fields = ["stage", "check_date", *InfrastructureCheck.WORK_FIELDS, "comments"]
        widgets = {
            "check_date": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 3}),
            **{
                name: forms.Select(choices=YES_NO_BOOLEAN_CHOICES)
                for name in InfrastructureCheck.WORK_FIELDS
            },
        }


class FieldForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Field
        fields = ["code", "description"]


class ValuationReferralForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ValuationReferral
        fields = ["letter_date", "reference_number", "response_date", "comments"]
        widgets = {
            "letter_date": IsoDateInput(),
            "response_date": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 2}),
        }


class PlotTkxNumberingForm(StyledFormMixin, forms.ModelForm):
    """8.1 inline ΤΚΧ numbering for an existing approved-design plot."""

    class Meta:
        model = ApprovedDesignPlot
        fields = ["tkx_number", "numbering_status"]

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("numbering_status") == ApprovedDesignPlot.NumberingStatus.TKX
            and not (cleaned_data.get("tkx_number") or "").strip()
        ):
            self.add_error("tkx_number", "Η Αρίθμηση ΤΚΧ απαιτείται για αυτή την κατάσταση.")
        return cleaned_data

    def save(self, commit=True):
        self.instance._section_ref = refs.REF_TKX_NUMBERING
        instance = super().save(commit=False)
        if commit:
            instance.save(update_fields=self.changed_data)
        return instance


class PlotMappingForm(StyledFormMixin, forms.ModelForm):
    """8.2 inline mapping, title and valuation fields for the same plot row."""

    owner = forms.ModelChoiceField(
        queryset=Person.objects.all(),
        required=False,
        help_text="8.2 Ιδιοκτήτης οικοπέδου",
    )

    class Meta:
        model = ApprovedDesignPlot
        fields = [
            "numbering_status",
            "design_number",
            "tkx_number",
            "field",
            "lot_number_in_field",
            "title_deed_number",
            "parcel_number",
            "sheet_plan",
            "kotsiani_number",
            "final_area_sqm",
            "has_separate_title",
            "valuation_amount",
            "valuation_referral",
            "comments",
            "owner",
        ]
        widgets = {"comments": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("numbering_status") == ApprovedDesignPlot.NumberingStatus.TKX
            and not (cleaned_data.get("tkx_number") or "").strip()
        ):
            self.add_error("tkx_number", "Η Αρίθμηση ΤΚΧ απαιτείται για αυτή την κατάσταση.")
        # 8.2 Without a separate title the value has to come from a ΤΚΧ referral.
        if (
            cleaned_data.get("has_separate_title") == YesNo.NO
            and cleaned_data.get("valuation_amount") is not None
            and not cleaned_data.get("valuation_referral")
        ):
            self.add_error(
                "valuation_referral",
                "Χωρίς ξεχωριστό τίτλο, η αξία προκύπτει από παραπομπή προς ΤΚΧ (8.2).",
            )
        return cleaned_data

    def save(self, commit=True):
        self.instance._section_ref = refs.REF_PLOT_MAPPING
        instance = super().save(commit=False)
        if commit:
            instance.save(update_fields=self.changed_data)
        return instance


class BasePlotFormSet(forms.BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        if "field" in form.fields:
            form.fields["field"].queryset = Field.objects.filter(case=self.instance)
        if "valuation_referral" in form.fields:
            form.fields["valuation_referral"].queryset = ValuationReferral.objects.filter(
                case=self.instance
            )


LandPlotDecisionFormSet = forms.inlineformset_factory(
    Case, LandPlot, form=LandPlotDecisionForm, extra=0, can_delete=False
)
FieldFormSet = forms.inlineformset_factory(Case, Field, form=FieldForm, extra=1, can_delete=True)
ValuationReferralFormSet = forms.inlineformset_factory(
    Case, ValuationReferral, form=ValuationReferralForm, extra=1, can_delete=True
)
PlotTkxNumberingFormSet = forms.inlineformset_factory(
    Case,
    ApprovedDesignPlot,
    form=PlotTkxNumberingForm,
    extra=0,
    can_delete=False,
)
PlotMappingFormSet = forms.inlineformset_factory(
    Case,
    ApprovedDesignPlot,
    form=PlotMappingForm,
    formset=BasePlotFormSet,
    extra=0,
    can_delete=False,
)
