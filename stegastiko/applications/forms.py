from django import forms

from applications.models import Application, DependentChild, Person
from applications.person_identity import (
    APPLICATION_PERSON_FIELD_NAMES,
    PERSON_FIELD_LABELS,
    PERSON_FIXED_FIELD_NAMES,
)
from core.forms import IsoDateInput

# Person fields shown on the form (identity_number is the lookup key, handled separately).
PERSON_FORM_FIELD_NAMES = tuple(name for name in PERSON_FIXED_FIELD_NAMES if name != "identity_number")


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "checkbox")
            elif not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", "input")
        for prefix in ("person1", "person2"):
            self.fields[f"{prefix}_identity_number"].widget.attrs.update(
                {"autocomplete": "off", "data-person-search": prefix}
            )

        # An existing Person keeps its fixed fields: they are filled from the stored
        # record and shown read-only; only the application-level fields are editable.
        self.existing_persons: dict[str, Person] = {}
        for prefix in ("person1", "person2"):
            person = self._existing_person(prefix)
            if person is None:
                continue
            self.existing_persons[prefix] = person
            for name in PERSON_FORM_FIELD_NAMES:
                field = self.fields[f"{prefix}_{name}"]
                field.required = False
                field.widget.attrs["readonly"] = "readonly"

    PERSON_SECTION_TITLES = (("person1", "Πρόσωπο 1"), ("person2", "Πρόσωπο 2 (όπου εφαρμόζεται)"))

    def person_sections(self) -> list[dict]:
        """Bound fields per person, split into fixed (Person) and per-application fields."""
        return [
            {
                "prefix": prefix,
                "title": title,
                "identity": self[f"{prefix}_identity_number"],
                "fixed": [self[f"{prefix}_{name}"] for name in PERSON_FORM_FIELD_NAMES],
                "declared": [
                    self[f"{prefix}_{name}"] for name in APPLICATION_PERSON_FIELD_NAMES
                ],
                "existing": self.existing_persons.get(prefix),
            }
            for prefix, title in self.PERSON_SECTION_TITLES
        ]

    def _existing_person(self, prefix: str) -> Person | None:
        key = f"{prefix}_identity_number"
        if self.is_bound:
            identity = self.data.get(self.add_prefix(key))
        else:
            identity = self.initial.get(key)
        identity = (identity or "").strip()
        if not identity:
            return None
        return Person.objects.filter(identity_number=identity).first()

    def _apply_existing_person(self, cleaned: dict, prefix: str) -> None:
        """Fixed fields come from the stored Person; a differing typed value is an error."""
        person = self.existing_persons.get(prefix)
        if person is None:
            return
        for name in PERSON_FORM_FIELD_NAMES:
            key = f"{prefix}_{name}"
            stored = getattr(person, name)
            posted = cleaned.get(key)
            if isinstance(posted, str):
                posted = posted.strip()
            if posted not in (None, "") and posted != stored:
                self.add_error(
                    key,
                    f"Το ΑΔΤ {person.identity_number} είναι ήδη καταχωρημένο και το πεδίο "
                    f"«{PERSON_FIELD_LABELS[name]}» δεν αλλάζει (καταχωρημένο: «{stored}»).",
                )
                continue
            cleaned[key] = stored

    PERSON2_REQUIRED_FIELDS = (
        "person2_first_name",
        "person2_last_name",
        "person2_date_of_birth",
        "person2_birth_place",
        "person2_birth_country",
        "person2_parents_birth_place",
        "person2_parents_birth_country",
    )

    def clean(self):
        cleaned = super().clean()
        person1_identity = (cleaned.get("person1_identity_number") or "").strip()
        person2_identity = (cleaned.get("person2_identity_number") or "").strip()
        if person1_identity and person1_identity == person2_identity:
            self.add_error(
                "person2_identity_number", "Το Πρόσωπο 2 δεν μπορεί να έχει το ίδιο ΑΔΤ με το Πρόσωπο 1."
            )
        self._apply_existing_person(cleaned, "person1")
        self._apply_existing_person(cleaned, "person2")
        if person2_identity and "person2" not in self.existing_persons:
            for name in self.PERSON2_REQUIRED_FIELDS:
                value = cleaned.get(name)
                if name in self.errors:
                    continue
                if value is None or (isinstance(value, str) and not value.strip()):
                    self.add_error(
                        name, "Υποχρεωτικό πεδίο όταν δηλώνεται ΑΔΤ Προσώπου 2."
                    )

        # 10.1.1: the folder number is tied to the Community and is not editable after
        # creation, so an existing application cannot be moved to another community.
        if self.instance.pk and "community" in cleaned:
            new_community = cleaned.get("community")
            if new_community is not None and new_community.pk != self.instance.community_id:
                self.add_error(
                    "community",
                    "Η Κοινότητα δεν μπορεί να αλλάξει μετά τη δημιουργία της αίτησης "
                    "(ο Αρ. Φακέλου Αιτητή είναι συνδεδεμένος με την Κοινότητα).",
                )
        return cleaned

    class Meta:
        model = Application
        fields = [
            "community",
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
            "person1_refugee_identity_number",
            "person1_citizenship_cypriot",
            "person1_citizenship_repatriated",
            "person1_citizenship_eu",
            "person1_citizenship_other",
            "person2_refugee_identity_number",
            "person2_citizenship_cypriot",
            "person2_citizenship_repatriated",
            "person2_citizenship_eu",
            "person2_citizenship_other",
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
        labels = {
            "person1_refugee_identity_number": "Αρ. Προσφυγικής Ταυτότητας Π1",
            "person1_citizenship_cypriot": "Κύπριος Πολίτης (Π1)",
            "person1_citizenship_repatriated": "Επαναπατρισθείς/είσα Κύπριος/α (Π1)",
            "person1_citizenship_eu": "Πολίτης κράτους μέλους ΕΕ (Π1)",
            "person1_citizenship_other": "Άλλη υπηκοότητα (Π1)",
            "person2_refugee_identity_number": "Αρ. Προσφυγικής Ταυτότητας Π2",
            "person2_citizenship_cypriot": "Κύπριος Πολίτης (Π2)",
            "person2_citizenship_repatriated": "Επαναπατρισθείς/είσα Κύπριος/α (Π2)",
            "person2_citizenship_eu": "Πολίτης κράτους μέλους ΕΕ (Π2)",
            "person2_citizenship_other": "Άλλη υπηκοότητα (Π2)",
        }
        help_texts = {
            f"{prefix}_{name}": ""
            for prefix in ("person1", "person2")
            for name in APPLICATION_PERSON_FIELD_NAMES
        }
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
