from django import forms

from applications.models import Application, DependentChild
from core.forms import IsoDateInput


class ApplicationForm(forms.ModelForm):
    person1_identity_number = forms.CharField(label="ΑΔΤ Προσώπου 1")
    person1_first_name = forms.CharField(label="Όνομα Προσώπου 1")
    person1_last_name = forms.CharField(label="Επίθετο Προσώπου 1")
    person1_date_of_birth = forms.DateField(
        label="Ημερομηνία γέννησης Προσώπου 1",
        widget=IsoDateInput(),
    )
    person1_birth_place = forms.CharField(label="Τόπος γέννησης Προσώπου 1")
    person1_birth_country = forms.CharField(label="Χώρα γέννησης Προσώπου 1")
    person1_parents_birth_place = forms.CharField(label="Τόπος γέννησης γονέων Π1")
    person1_parents_birth_country = forms.CharField(label="Χώρα γέννησης γονέων Π1")
    person1_refugee_identity_number = forms.CharField(
        label="Αρ. Προσφυγικής Ταυτότητας Π1", required=False
    )
    person1_citizenship_cypriot = forms.BooleanField(
        label="Κύπριος Πολίτης (Π1)", required=False
    )
    person1_citizenship_repatriated = forms.BooleanField(
        label="Επαναπατρισθείς/είσα Κύπριος/α (Π1)", required=False
    )
    person1_citizenship_eu = forms.BooleanField(
        label="Πολίτης κράτους μέλους ΕΕ (Π1)", required=False
    )
    person1_citizenship_other = forms.CharField(
        label="Άλλη υπηκοότητα (Π1)", required=False
    )

    person2_identity_number = forms.CharField(label="ΑΔΤ Προσώπου 2", required=False)
    person2_first_name = forms.CharField(label="Όνομα Προσώπου 2", required=False)
    person2_last_name = forms.CharField(label="Επίθετο Προσώπου 2", required=False)
    person2_date_of_birth = forms.DateField(
        label="Ημερομηνία γέννησης Προσώπου 2",
        required=False,
        widget=IsoDateInput(),
    )
    person2_birth_place = forms.CharField(label="Τόπος γέννησης Προσώπου 2", required=False)
    person2_birth_country = forms.CharField(label="Χώρα γέννησης Προσώπου 2", required=False)
    person2_parents_birth_place = forms.CharField(label="Τόπος γέννησης γονέων Π2", required=False)
    person2_parents_birth_country = forms.CharField(label="Χώρα γέννησης γονέων Π2", required=False)
    person2_refugee_identity_number = forms.CharField(
        label="Αρ. Προσφυγικής Ταυτότητας Π2", required=False
    )
    person2_citizenship_cypriot = forms.BooleanField(
        label="Κύπριος Πολίτης (Π2)", required=False
    )
    person2_citizenship_repatriated = forms.BooleanField(
        label="Επαναπατρισθείς/είσα Κύπριος/α (Π2)", required=False
    )
    person2_citizenship_eu = forms.BooleanField(
        label="Πολίτης κράτους μέλους ΕΕ (Π2)", required=False
    )
    person2_citizenship_other = forms.CharField(
        label="Άλλη υπηκότητα (Π2)", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "checkbox")
            elif not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", "input")

    class Meta:
        model = Application
        fields = [
            "submission_cycle",
            "submitted_on",
            "family_type",
            "family_type_other",
            "applicant_email",
            "comments",
            "is_family_type_correct",
            "corrected_family_type",
            "signatures_status",
            "completeness_result",
            "completeness_comments",
            "person1_relationship",
            "person2_relationship",
            "person1_residence_community",
            "person2_residence_community",
            "person1_residence_address",
            "person2_residence_address",
            "person1_residence_start",
            "person2_residence_start",
            "residence_category",
            "person1_has_property",
            "person2_has_property",
            "person1_non_alienation_clear",
            "person2_non_alienation_clear",
            "person1_previous_aid_clear",
            "person2_previous_aid_clear",
            "person1_income",
            "person2_income",
            "children_income",
        ]
        widgets = {
            "submitted_on": IsoDateInput(),
            "person1_residence_start": IsoDateInput(),
            "person2_residence_start": IsoDateInput(),
            "comments": forms.Textarea(attrs={"rows": 3}),
            "completeness_comments": forms.Textarea(attrs={"rows": 3}),
        }


class DependentChildForm(forms.ModelForm):
    class Meta:
        model = DependentChild
        fields = ["full_name", "date_of_birth", "category", "is_recognized_dependent"]
        widgets = {
            "date_of_birth": IsoDateInput(attrs={"class": "input"}),
            "full_name": forms.TextInput(attrs={"class": "input"}),
            "category": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_recognized_dependent"].widget.attrs.setdefault("class", "checkbox")


DependentChildFormSet = forms.inlineformset_factory(
    Application,
    DependentChild,
    form=DependentChildForm,
    extra=1,
    can_delete=True,
)
