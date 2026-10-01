from django import forms

from applications.models import Person
from cases.models import (
    Case,
    CompletenessCheck,
    Consultation,
    Field,
    InfrastructureCheck,
    LandPlot,
    Parcel,
    SubmissionCycle,
    SubmissionCyclePublication,
    UtilityService,
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


class CaseCreateForm(StyledFormMixin, forms.ModelForm):
    """§1.1–1.2 on create; case number and start date are automatic."""

    class Meta:
        model = Case
        fields = [
            "community",
            "case_type",
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
        self.fields["case_type"].label = "Τύπος διαδικασίας"
        self.fields["submitted_at"].required = False

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
        case_type = cleaned_data.get("case_type")
        if not (cleaned_data.get("contact_email") or "").strip():
            self.add_error(
                "contact_email",
                "Απαιτείται ηλεκτρονική διεύθυνση επικοινωνίας Κ.Σ./Δ.Δ. (1.1).",
            )
        if case_type == Case.CaseType.UNALLOCATED_PLOTS:
            cleaned_data["submitted_at"] = None
            cleaned_data["priority_turkish_cypriot_properties"] = False
            cleaned_data["priority_protection_zones"] = False
            cleaned_data["priority_nuisance_developments"] = False
            cleaned_data["priority_limited_private_land"] = False
            cleaned_data["priority_other"] = ""
            cleaned_data["priority_documentation"] = ""
        elif case_type == Case.CaseType.NEW_DIVISION and not cleaned_data.get("submitted_at"):
            self.add_error(
                "submitted_at",
                "Για νέο αίτημα διαχωρισμού απαιτείται η ημερομηνία υποβολής (1.1).",
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
        case = self.instance
        self.fields["contact_email"].required = True
        self.fields["submitted_at"].required = case.is_new_division
        if not case.is_new_division:
            self.fields.pop("submitted_at", None)
            for name in (
                "priority_turkish_cypriot_properties",
                "priority_protection_zones",
                "priority_nuisance_developments",
                "priority_limited_private_land",
                "priority_other",
                "priority_documentation",
            ):
                self.fields.pop(name, None)

    def clean(self):
        cleaned_data = super().clean()
        case = self.instance
        if case.is_new_division and not cleaned_data.get("submitted_at"):
            self.add_error(
                "submitted_at",
                "Για νέο αίτημα διαχωρισμού απαιτείται η ημερομηνία υποβολής (1.1).",
            )
        return cleaned_data


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
        fields = ["state_land_remains_sufficient", "state_land_comments", "section3_comments"]
        widgets = {
            "state_land_comments": forms.Textarea(attrs={"rows": 3}),
            "section3_comments": forms.Textarea(attrs={"rows": 3}),
        }


class Section4Form(StyledFormMixin, AttachmentsFormMixin, forms.ModelForm):
    """4.3 access, 4.4 files of the evaluation as a whole and 4.5 comments.

    4.1 rows are edited one at a time from the grid modal; 4.2 is the inline formset.
    """

    attachment_section_ref = "4.4"

    class Meta:
        model = Case
        fields = ["access_technical_evaluation", "section4_comments"]
        widgets = {
            "access_technical_evaluation": forms.Textarea(attrs={"rows": 3}),
            "section4_comments": forms.Textarea(attrs={"rows": 3}),
        }


class Section6Form(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Case
        fields = ["section6_comments"]
        widgets = {"section6_comments": forms.Textarea(attrs={"rows": 3})}


class Section7Form(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Case
        fields = [
            "recommendation_letter_date",
            "recommendation",
            "ministry_response_date",
            "ministry_decision",
            "section7_comments",
        ]
        widgets = {
            "recommendation_letter_date": IsoDateInput(),
            "ministry_response_date": IsoDateInput(),
            "section7_comments": forms.Textarea(attrs={"rows": 3}),
        }


class Section8Form(StyledFormMixin, forms.ModelForm):
    """8.1-8.6 single-row blocks of the division workflow."""

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
            "tender_announcement_date",
            "tender_award_date",
            "contractor_name",
            "contractor_phone",
            "contractor_email",
            "contract_duration_value",
            "contract_duration_unit",
            "tender_comments",
            "works_progress_stage",
            "works_progress_updated_on",
            "works_progress_comments",
            "section8_comments",
        ]
        widgets = {
            "survey_assignment_date": IsoDateInput(),
            "division_design_completed_on": IsoDateInput(),
            "tpo_application_date": IsoDateInput(),
            "tpo_response_date": IsoDateInput(),
            "tender_announcement_date": IsoDateInput(),
            "tender_award_date": IsoDateInput(),
            "works_progress_updated_on": IsoDateInput(),
            "survey_assignment_comments": forms.Textarea(attrs={"rows": 2}),
            "division_design_comments": forms.Textarea(attrs={"rows": 2}),
            "tpo_comments": forms.Textarea(attrs={"rows": 2}),
            "tender_comments": forms.Textarea(attrs={"rows": 2}),
            "works_progress_comments": forms.Textarea(attrs={"rows": 2}),
            "section8_comments": forms.Textarea(attrs={"rows": 3}),
        }


class Section8PlotsForm(StyledFormMixin, forms.ModelForm):
    """8.7 header block of the survey request sent to the Land Registry (ΤΚΧ)."""

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

    attachment_section_ref = "3.1"
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
    class Meta:
        model = UtilityService
        fields = ["service_name", "proximity", "comments"]
        widgets = {"comments": forms.Textarea(attrs={"rows": 2})}


class ConsultationForm(StyledFormMixin, forms.ModelForm):
    """Status is derived from the response date, so it is not editable here."""

    class Meta:
        model = Consultation
        fields = ["department", "topic", "sent_date", "due_date", "response_date", "response_text", "comments"]
        widgets = {
            "sent_date": IsoDateInput(),
            "due_date": IsoDateInput(),
            "response_date": IsoDateInput(),
            "topic": forms.Textarea(attrs={"rows": 2}),
            "response_text": forms.Textarea(attrs={"rows": 2}),
            "comments": forms.Textarea(attrs={"rows": 2}),
        }


class BaseStageConsultationFormSet(forms.BaseInlineFormSet):
    """Keeps sections 5 and 8.4 as separate tables over the same entity."""

    stage = ""

    def save_new(self, form, commit=True):
        form.instance.stage = self.stage
        return super().save_new(form, commit=commit)


class BaseSuitabilityConsultationFormSet(BaseStageConsultationFormSet):
    stage = Consultation.Stage.SUITABILITY


class BaseDivisionConsultationFormSet(BaseStageConsultationFormSet):
    stage = Consultation.Stage.DIVISION


class InfrastructureCheckForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = InfrastructureCheck
        fields = [
            "check_date",
            "curbs_ready",
            "curbs_comments",
            "pavements_ready",
            "pavements_comments",
            "asphalt_ready",
            "asphalt_comments",
            "pavement_fill_ready",
            "pavement_fill_comments",
            "water_ready",
            "water_comments",
            "telecom_ready",
            "telecom_comments",
            "electricity_ready",
            "electricity_comments",
            "street_light_ready",
            "street_light_comments",
            "comments",
        ]
        widgets = {
            "check_date": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 2}),
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


class ParcelForm(StyledFormMixin, forms.ModelForm):
    """8.7 mapping table plus the 8.8 valuation; the disposal price is computed."""

    owner = forms.ModelChoiceField(
        queryset=Person.objects.all(),
        required=False,
        help_text="8.7 Ιδιοκτήτης οικοπέδου",
    )

    class Meta:
        model = Parcel
        fields = [
            "field",
            "lot_number_in_field",
            "design_lot_number",
            "tkx_lot_number",
            "sheet_plan",
            "kotsiani_number",
            "final_area_sqm",
            "has_separate_title",
            "valuation_amount",
            "valuation_referral",
            "comments",
        ]
        widgets = {"comments": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.owner_person_id:
            self.initial["owner"] = self.instance.owner_person_id

    def clean(self):
        cleaned_data = super().clean()
        # 8.8.1 Without a separate title the value has to come from a ΤΚΧ referral.
        if (
            cleaned_data.get("has_separate_title") == YesNo.NO
            and cleaned_data.get("valuation_amount") is not None
            and not cleaned_data.get("valuation_referral")
        ):
            self.add_error(
                "valuation_referral",
                "Χωρίς ξεχωριστό τίτλο, η αξία προκύπτει από παραπομπή προς ΤΚΧ (8.8.1).",
            )
        return cleaned_data

    def save(self, commit=True):
        owner = self.cleaned_data.get("owner")
        self.instance.owner_person_id = owner.pk if owner else None
        return super().save(commit=commit)


class BaseParcelFormSet(forms.BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        if "field" in form.fields:
            form.fields["field"].queryset = Field.objects.filter(case=self.instance)
        if "valuation_referral" in form.fields:
            form.fields["valuation_referral"].queryset = ValuationReferral.objects.filter(
                case=self.instance
            )


class SubmissionCycleForm(StyledFormMixin, forms.ModelForm):
    """9.1 Announcement of the submission period, at community level."""

    class Meta:
        model = SubmissionCycle
        fields = [
            "cases",
            "announcement_date",
            "submission_start_date",
            "submission_end_date",
            "comments",
        ]
        widgets = {
            "cases": forms.CheckboxSelectMultiple(),
            "announcement_date": IsoDateInput(),
            "submission_start_date": IsoDateInput(),
            "submission_end_date": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, community=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.community = community or getattr(self.instance, "community", None)
        # 9.1 An announcement may only group cases of its own community.
        self.fields["cases"].queryset = Case.objects.filter(community=self.community)
        self.fields["cases"].label = "Υποθέσεις της γνωστοποίησης (9.1)"

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("submission_start_date")
        end = cleaned_data.get("submission_end_date")
        if start and end and end < start:
            self.add_error(
                "submission_end_date", "Η λήξη υποβολής δεν μπορεί να προηγείται της έναρξης."
            )
        return cleaned_data


class AnnouncementTextForm(StyledFormMixin, forms.ModelForm):
    """9.3 Preview and edit the generated announcement before finalising it."""

    class Meta:
        model = SubmissionCycle
        fields = ["announcement_text"]
        widgets = {"announcement_text": forms.Textarea(attrs={"rows": 18})}


class SubmissionCyclePublicationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SubmissionCyclePublication
        fields = ["method", "published_on", "notes"]
        widgets = {"published_on": IsoDateInput()}


SubmissionCyclePublicationFormSet = forms.inlineformset_factory(
    SubmissionCycle,
    SubmissionCyclePublication,
    form=SubmissionCyclePublicationForm,
    extra=1,
    can_delete=True,
)
LandPlotDecisionFormSet = forms.inlineformset_factory(
    Case, LandPlot, form=LandPlotDecisionForm, extra=0, can_delete=False
)
UtilityServiceFormSet = forms.inlineformset_factory(
    Case, UtilityService, form=UtilityServiceForm, extra=1, can_delete=True
)
SuitabilityConsultationFormSet = forms.inlineformset_factory(
    Case,
    Consultation,
    form=ConsultationForm,
    formset=BaseSuitabilityConsultationFormSet,
    extra=1,
    can_delete=True,
)
DivisionConsultationFormSet = forms.inlineformset_factory(
    Case,
    Consultation,
    form=ConsultationForm,
    formset=BaseDivisionConsultationFormSet,
    extra=1,
    can_delete=True,
)
InfrastructureCheckFormSet = forms.inlineformset_factory(
    Case, InfrastructureCheck, form=InfrastructureCheckForm, extra=1, can_delete=True
)
FieldFormSet = forms.inlineformset_factory(Case, Field, form=FieldForm, extra=1, can_delete=True)
ValuationReferralFormSet = forms.inlineformset_factory(
    Case, ValuationReferral, form=ValuationReferralForm, extra=1, can_delete=True
)
ParcelFormSet = forms.inlineformset_factory(
    Case, Parcel, form=ParcelForm, formset=BaseParcelFormSet, extra=1, can_delete=True
)
