from django import forms

from applications.models import Person
from applications.person_identity import PERSON_FIELD_LABELS, PERSON_FIXED_FIELD_NAMES
from cases.forms import StyledFormMixin
from core.forms import IsoDateInput

DOCUMENT_TYPE_LABEL = "Τύπος εγγράφου ταυτοποίησης (αλλοδαποί)"
IDENTITY_LOCKED_HELP = (
    "Ο Αρ. Δελτίου Ταυτότητας συνδέει το άτομο με τις αιτήσεις του και δεν αλλάζει."
)


class PersonForm(StyledFormMixin, forms.ModelForm):
    """The fixed identity fields of one Person (10.3.1).

    The ΑΔΤ is the key that links a person to their applications, so it is set once on
    creation and is read-only afterwards.
    """

    class Meta:
        model = Person
        fields = [*PERSON_FIXED_FIELD_NAMES, "document_type"]
        widgets = {"date_of_birth": IsoDateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, label in PERSON_FIELD_LABELS.items():
            self.fields[name].label = label
            self.fields[name].required = True
        self.fields["document_type"].label = DOCUMENT_TYPE_LABEL
        if self.instance.pk:
            identity = self.fields["identity_number"]
            # A disabled field ignores posted data and keeps the stored value.
            identity.disabled = True
            identity.help_text = IDENTITY_LOCKED_HELP

    def clean_identity_number(self):
        if self.instance.pk:
            return self.instance.identity_number
        identity_number = (self.cleaned_data.get("identity_number") or "").strip()
        if Person.objects.filter(identity_number__iexact=identity_number).exists():
            raise forms.ValidationError("Υπάρχει ήδη άτομο με αυτόν τον Αρ. Δελτίου Ταυτότητας.")
        return identity_number

    def clean(self):
        cleaned_data = super().clean()
        for name in ("first_name", "last_name", "birth_place", "birth_country",
                     "parents_birth_place", "parents_birth_country", "document_type"):
            if isinstance(cleaned_data.get(name), str):
                cleaned_data[name] = cleaned_data[name].strip()
        return cleaned_data
