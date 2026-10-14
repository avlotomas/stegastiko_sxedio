from django import forms
from django.db.models import Count, Q

from applications.models import Person
from applications.person_identity import PERSON_FIELD_LABELS
from core.appendix1 import appendix1_choices
from core.forms import IsoDateInput
from core.models import Community
from plot_applications.documents import DOCUMENT_CHOICES
from plots.models import Plot
from plot_applications.models import (
    ApplicationChild,
    ApplicationParty,
    IncomeDeclaration,
    PlotApplication,
    ResidenceCategory,
)

# Ενότ. 11 (Ι, ΙΙ, ΙV): η διαμονή είναι στην Κοινότητα της αίτησης, άρα η Κοινότητα διαμονής κλειδώνει σε αυτήν.
COMMUNITY_LOCKED_CATEGORIES = (
    ResidenceCategory.AUTOCHTHON,
    ResidenceCategory.DISPLACED,
    ResidenceCategory.REPATRIATED,
)

YES_NO_CHOICES = (("True", "Ναι"), ("False", "Όχι"))


def _style(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
        elif not isinstance(widget, forms.HiddenInput):
            widget.attrs.setdefault("class", "input")


def yes_no_field(label):
    return forms.TypedChoiceField(
        label=label,
        choices=YES_NO_CHOICES,
        coerce=lambda value: value == "True",
        widget=forms.RadioSelect,
        required=False,
        empty_value=None,
    )


class PersonIdentityForm(forms.Form):
    """Σταθερά στοιχεία προσώπου (μητρώο «Άτομα»). Για υπάρχον ΑΔΤ συμπληρώνονται από το μητρώο."""

    required_css_class = "required"

    FIXED_FIELDS = (
        "first_name",
        "last_name",
        "date_of_birth",
        "birth_place",
        "birth_country",
        "parents_birth_place",
        "parents_birth_country",
    )

    identity_number = forms.CharField(label="Αρ. Δελτίου Ταυτότητας", max_length=32)
    first_name = forms.CharField(label="Όνομα", max_length=128)
    last_name = forms.CharField(label="Επίθετο", max_length=128)
    date_of_birth = forms.DateField(label="Ημερομηνία Γέννησης", widget=IsoDateInput())
    birth_place = forms.CharField(label="Τόπος Γέννησης", max_length=128)
    birth_country = forms.CharField(label="Χώρα Γέννησης", max_length=128)
    parents_birth_place = forms.CharField(label="Τόπος γέννησης γονέων", max_length=128)
    parents_birth_country = forms.CharField(label="Χώρα Γέννησης Γονέων", max_length=128)

    def __init__(self, *args, required=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_required = required
        self.existing = self._existing_person()
        for name, field in self.fields.items():
            field.required = required and (self.existing is None or name == "identity_number")
        if self.existing is not None:
            for name in self.FIXED_FIELDS:
                self.fields[name].widget.attrs["readonly"] = "readonly"
                self.fields[name].help_text = "Από το μητρώο Ατόμων."
        self.fields["identity_number"].help_text = (
            "Αν το ΑΔΤ είναι ήδη καταχωρημένο, τα υπόλοιπα στοιχεία συμπληρώνονται από το μητρώο Ατόμων."
        )
        _style(self)

    def _existing_person(self):
        if self.is_bound:
            identity = self.data.get(self.add_prefix("identity_number"))
        else:
            identity = self.initial.get("identity_number")
        identity = (identity or "").strip()
        return Person.objects.filter(identity_number=identity).first() if identity else None

    @property
    def is_filled(self) -> bool:
        return bool((self.cleaned_data.get("identity_number") or "").strip())

    def clean(self):
        cleaned = super().clean()
        if self.existing is None:
            return cleaned
        for name in self.FIXED_FIELDS:
            stored = getattr(self.existing, name)
            posted = cleaned.get(name)
            if isinstance(posted, str):
                posted = posted.strip()
            if posted not in (None, "") and posted != stored:
                self.add_error(
                    name,
                    f"Το ΑΔΤ {self.existing.identity_number} είναι ήδη καταχωρημένο και το πεδίο "
                    f"«{PERSON_FIELD_LABELS[name]}» δεν αλλάζει (καταχωρημένο: «{stored}»).",
                )
            else:
                cleaned[name] = stored
        return cleaned

    def get_or_create_person(self) -> Person:
        identity = self.cleaned_data["identity_number"].strip()
        if self.existing is not None:
            return self.existing
        return Person.objects.create(
            identity_number=identity,
            **{name: self.cleaned_data[name] for name in self.FIXED_FIELDS},
        )


class PlotApplicationForm(forms.ModelForm):
    required_css_class = "required"

    has_dwelling = yes_no_field(
        "(α) Έχετε εγγεγραμμένη στο όνομά σας (περιλ. συζύγου/συμβίου) κατοικία "
        "(περιλ. κατοικίας σε οικόπεδο αυτοστέγασης, Ενότ. 10.Δ);"
    )
    has_residential_land = yes_no_field(
        "(β) Έχετε εσείς (περιλ. συζύγου/συμβίου), οι γονείς σας ή του/της συζύγου/συμβίου ή τα τέκνα "
        "του ζεύγους εγγεγραμμένο οικόπεδο ή τεμάχιο σε Οικιστική Ζώνη ή σε περιοχή όπου επιτρέπεται "
        "η ανέγερση κατοικίας;"
    )
    has_alienated_property = yes_no_field(
        "(γ) Έχετε αποξενώσει εσείς (περιλ. συζύγου/συμβίου) ή οι γονείς σας ή οι γονείς του/της "
        "συζύγου/συμβίου ακίνητο αξιοποιήσιμο για οικιστικούς σκοπούς εντός των προηγούμενων "
        "τριών (3) ετών;"
    )
    previous_housing_aid = yes_no_field(
        "Έχετε εσείς ή ο/η σύζυγος/συμβίος σας επωφεληθεί στο παρελθόν από οικονομική ενίσχυση ή άλλο "
        "όφελος για στεγαστικούς σκοπούς στο πλαίσιο Κρατικού Στεγαστικού Σχεδίου (εξαιρείται "
        "αποκλειστικά επιδότηση ενοικίου ή επιτοκίου στεγαστικού δανείου);"
    )
    neighbouring_community = forms.ChoiceField(
        label="Γειτονική Κοινότητα διαμονής (Παράρτημα 1)",
        choices=appendix1_choices,
        required=False,
    )
    attached_documents = forms.MultipleChoiceField(
        label="Επισυναπτόμενα δικαιολογητικά",
        choices=DOCUMENT_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = PlotApplication
        fields = [
            "community",
            "submitted_on",
            "received_at",
            "received_by",
            "district_file_number",
            "email",
            "correspondence_street",
            "correspondence_number",
            "correspondence_apartment",
            "correspondence_community",
            "correspondence_postal_code",
            "correspondence_district",
            "residence_category",
            "residence_street",
            "residence_number",
            "residence_apartment",
            "residence_postal_code",
            "residence_community",
            "origin_parent_description",
            "previous_residence_address",
            "previous_residence_from",
            "previous_residence_to",
            "community_residence_since",
            "abroad_from",
            "abroad_to",
            "residence_notes",
            "family_status",
            "single_parent_status",
            "single_parent_other",
            "has_dwelling",
            "has_dwelling_details",
            "has_residential_land",
            "has_residential_land_details",
            "has_alienated_property",
            "has_alienated_property_details",
            "previous_housing_aid",
            "previous_housing_aid_details",
            "other_application_choice_1",
            "other_application_choice_2",
            "other_application_choice_3",
            "other_applications_notes",
            "email_declaration_accepted",
            "applicant_signed",
            "spouse_signed",
            "sworn_declaration_date",
            "sworn_court",
            "sworn_by_applicant",
            "sworn_by_spouse",
            "attached_documents",
            "other_documents",
            "comments",
        ]
        labels = {
            "community": "Κοινότητα στην οποία ζητείται η παραχώρηση οικοπέδου",
            "submitted_on": "Ημερομηνία υποβολής",
            "received_at": "Ημερομηνία και ώρα παραλαβής",
            "received_by": "Όνομα παραλήπτη",
            "district_file_number": "Αρ. Φακέλου Επαρχιακής Διοίκησης",
            "email": "Ηλεκτρονική Διεύθυνση",
            "correspondence_street": "Οδός",
            "correspondence_number": "Αριθμός",
            "correspondence_apartment": "Διαμέρισμα",
            "correspondence_community": "Κοινότητα / Δημοτικό Διαμέρισμα",
            "correspondence_postal_code": "Ταχ. Κωδ.",
            "correspondence_district": "Επαρχία",
            "residence_category": "Κατηγορία",
            "residence_street": "Οδός",
            "residence_number": "Αριθμός",
            "residence_apartment": "Αρ. κατοικίας / διαμερίσματος",
            "residence_postal_code": "Ταχ. Κωδ.",
            "residence_community": "Κοινότητα / Δημοτικό Διαμέρισμα διαμονής",
            "origin_parent_description": "Καταγωγή από την Κοινότητα ως προς ποιο γονέα",
            "previous_residence_address": "Διεύθυνση στην Κοινότητα κατά την περίοδο μόνιμης κατοίκησης",
            "previous_residence_from": "Περίοδος μόνιμης κατοίκησης από",
            "previous_residence_to": "Περίοδος μόνιμης κατοίκησης μέχρι",
            "community_residence_since": "(α) Μόνιμη διαμονή στην Κοινότητα από",
            "abroad_from": "(β) Παραμονή στο εξωτερικό από",
            "abroad_to": "(β) Παραμονή στο εξωτερικό μέχρι",
            "residence_notes": "Αναλυτική περιγραφή / λοιπές πληροφορίες",
            "family_status": "Οικογενειακή κατάσταση",
            "single_parent_status": "Μονογονιός",
            "single_parent_other": "Άλλο (περιγραφή)",
            "has_dwelling_details": "Διευκρινίσεις (α)",
            "has_residential_land_details": "Διευκρινίσεις (β)",
            "has_alienated_property_details": "Διευκρινίσεις (γ)",
            "previous_housing_aid_details": "Επεξηγήσεις και διευκρινίσεις",
            "other_application_choice_1": "1η Επιλογή",
            "other_application_choice_2": "2η Επιλογή",
            "other_application_choice_3": "3η Επιλογή",
            "other_applications_notes": "Λοιπές πληροφορίες (Κοινότητα, Επαρχιακή Διοίκηση)",
            "email_declaration_accepted": "Υπεύθυνη δήλωση για την ηλεκτρονική διεύθυνση — υπογράφηκε",
            "applicant_signed": "Υπογραφή Αιτητή/Αιτήτριας",
            "spouse_signed": "Υπογραφή Συζύγου/Συμβίου",
            "sworn_declaration_date": "Ημερομηνία ορκωμοσίας",
            "sworn_court": "Επαρχιακό Δικαστήριο",
            "sworn_by_applicant": "Ένορκη δήλωση Αιτητή/Αιτήτριας",
            "sworn_by_spouse": "Ένορκη δήλωση Συζύγου/Συμβίου",
            "other_documents": "Άλλα πιστοποιητικά",
            "comments": "Σχόλια / Παρατηρήσεις",
        }
        widgets = {
            "submitted_on": IsoDateInput(),
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "previous_residence_from": IsoDateInput(),
            "previous_residence_to": IsoDateInput(),
            "community_residence_since": IsoDateInput(),
            "abroad_from": IsoDateInput(),
            "abroad_to": IsoDateInput(),
            "sworn_declaration_date": IsoDateInput(),
            "residence_category": forms.RadioSelect,
            "family_status": forms.RadioSelect,
            "single_parent_status": forms.RadioSelect,
            "origin_parent_description": forms.Textarea(attrs={"rows": 2}),
            "residence_notes": forms.Textarea(attrs={"rows": 3}),
            "has_dwelling_details": forms.Textarea(attrs={"rows": 2}),
            "has_residential_land_details": forms.Textarea(attrs={"rows": 2}),
            "has_alienated_property_details": forms.Textarea(attrs={"rows": 2}),
            "previous_housing_aid_details": forms.Textarea(attrs={"rows": 2}),
            "other_applications_notes": forms.Textarea(attrs={"rows": 2}),
            "other_documents": forms.Textarea(attrs={"rows": 2}),
            "comments": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Η Αίτηση δεν συνδέεται με Γνωστοποιήσεις: προσφέρονται οι ενεργές Κοινότητες που
        # έχουν διαθέσιμα Οικόπεδα, με τον αριθμό τους. Στην επεξεργασία μένει μόνο η υπάρχουσα.
        communities = Community.objects.annotate(
            available_plots=Count("plots", filter=Q(plots__in=Plot.objects.available()))
        )
        if self.instance.pk:
            communities = communities.filter(pk=self.instance.community_id)
        else:
            communities = communities.filter(is_active=True, available_plots__gt=0)
        community_field = self.fields["community"]
        community_field.queryset = communities.order_by("name")
        community_field.label_from_instance = lambda community: (
            f"{community.name} ({community.available_plots})"
        )
        self.community_names = {str(c.pk): c.name for c in communities}
        # Η απαιτούμενη τιμή κατά κατηγορία ελέγχεται στο clean().
        self.fields["residence_community"].required = False
        self.fields["residence_community"].help_text = ""
        if self.instance.pk and self.instance.residence_category == ResidenceCategory.NEIGHBOURING:
            self.initial.setdefault("neighbouring_community", self.instance.residence_community)
        self.fields["received_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        for name in ("residence_category", "family_status"):
            self.fields[name].choices = [c for c in self.fields[name].choices if c[0]]
        self.fields["single_parent_status"].choices = [
            c for c in self.fields["single_parent_status"].choices if c[0]
        ]
        _style(self)

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and cleaned.get("community") and (
            cleaned["community"].pk != self.instance.community_id
        ):
            self.add_error("community", "Η Κοινότητα δεν αλλάζει μετά την καταχώριση.")
        if cleaned.get("family_status") == PlotApplication.FamilyStatus.SINGLE_PARENT:
            status = cleaned.get("single_parent_status")
            if not status:
                self.add_error("single_parent_status", "Επιλέξτε την περίπτωση μονογονιού.")
            elif status == PlotApplication.SingleParentStatus.OTHER and not cleaned.get("single_parent_other"):
                self.add_error("single_parent_other", "Περιγράψτε την περίπτωση «Άλλο».")
        else:
            cleaned["single_parent_status"] = ""
            cleaned["single_parent_other"] = ""
        self._clean_residence_community(cleaned)
        for start, end in (
            ("previous_residence_from", "previous_residence_to"),
            ("abroad_from", "abroad_to"),
        ):
            if cleaned.get(start) and cleaned.get(end) and cleaned[end] < cleaned[start]:
                self.add_error(end, "Η ημερομηνία λήξης είναι πριν την έναρξη.")
        return cleaned

    def _clean_residence_community(self, cleaned):
        category = cleaned.get("residence_category")
        if category in COMMUNITY_LOCKED_CATEGORIES:
            community = cleaned.get("community")
            cleaned["residence_community"] = community.name if community else ""
        elif category == ResidenceCategory.NEIGHBOURING:
            chosen = cleaned.get("neighbouring_community") or ""
            if not chosen and "neighbouring_community" not in self.errors:
                self.add_error("neighbouring_community", "Επιλέξτε τη Γειτονική Κοινότητα από τον κατάλογο.")
            cleaned["residence_community"] = chosen
        elif category and not (cleaned.get("residence_community") or "").strip():
            self.add_error("residence_community", "Συμπληρώστε την Κοινότητα / Δημοτικό Διαμέρισμα διαμονής.")


class ApplicationPartyForm(forms.ModelForm):
    required_css_class = "required"

    class Meta:
        model = ApplicationParty
        fields = [
            "social_insurance_number",
            "refugee_identity_number",
            "alien_registration_number",
            "citizenship",
            "citizenship_other",
            "mobile_phone",
            "landline_phone",
            "email",
            "is_self_employed",
            "is_employee",
            "is_unemployed",
            "has_disability",
            "employer_details",
        ]
        labels = {
            "social_insurance_number": "Αρ. Κοινωνικών Ασφαλίσεων",
            "refugee_identity_number": "Αρ. Προσφυγικής Ταυτότητας (για εκτοπισθέντες)",
            "alien_registration_number": "Alien Registration Certificate (όπου εφαρμόζεται)",
            "citizenship": "Υπηκοότητα / Ιδιότητα",
            "citizenship_other": "Άλλο (περιγραφή)",
            "mobile_phone": "Τηλέφωνο Κινητό",
            "landline_phone": "Τηλέφωνο Σταθερό",
            "email": "Ηλεκτρονικό Ταχυδρομείο",
            "is_self_employed": "Αυτοτελώς Εργαζόμενος/η",
            "is_employee": "Μισθωτός/ή",
            "is_unemployed": "Άνεργος/η",
            "has_disability": "Άτομο με αναπηρία",
            "employer_details": "Εργοδότης (σχετικές πληροφορίες)",
        }
        widgets = {
            "citizenship": forms.RadioSelect,
            "employer_details": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, role=ApplicationParty.Role.APPLICANT, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        choices = [c for c in self.fields["citizenship"].choices if c[0]]
        if role == ApplicationParty.Role.APPLICANT:
            for name in ("alien_registration_number", "email"):
                self.fields.pop(name)
        else:
            self.fields["email"].help_text = (
                "Για την επίσημη αλληλογραφία χρησιμοποιείται το email του Αιτητή/Αιτήτριας."
            )
        self.fields["citizenship"].choices = choices
        self.fields["mobile_phone"].required = True
        _style(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("citizenship") == ApplicationParty.Citizenship.OTHER:
            if not (cleaned.get("citizenship_other") or "").strip():
                self.add_error("citizenship_other", "Συμπληρώστε την υπηκοότητα / ιδιότητα.")
        else:
            cleaned["citizenship_other"] = ""
        return cleaned


class ApplicationChildForm(forms.ModelForm):
    required_css_class = "required"

    class Meta:
        model = ApplicationChild
        fields = ["first_name", "last_name", "date_of_birth", "identity_number", "sex", "status"]
        labels = {
            "first_name": "Όνομα",
            "last_name": "Επίθετο",
            "date_of_birth": "Ημερομηνία Γέννησης",
            "identity_number": "Αρ. Δελτίου Ταυτότητας",
            "sex": "Φύλο",
            "status": "Κατάσταση",
        }
        widgets = {"date_of_birth": IsoDateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == ApplicationChild.Status.STUDENT and not cleaned.get("sex"):
            self.add_error("sex", "Για φοιτητή/τρια απαιτείται το φύλο (όριο 23 θήλυ / 25 άρρεν).")
        return cleaned


ChildFormSet = forms.inlineformset_factory(
    PlotApplication, ApplicationChild, form=ApplicationChildForm, extra=0, can_delete=True
)


class IncomeDeclarationForm(forms.ModelForm):
    class Meta:
        model = IncomeDeclaration
        fields = [
            "member_description",
            "employment_type",
            "gross_annual_income",
            "other_income_1_description",
            "other_income_1_amount",
            "other_income_2_description",
            "other_income_2_amount",
            "other_income_3_description",
            "other_income_3_amount",
        ]
        labels = {
            "member_description": "Δήλωση Μέλους Οικογένειας",
            "employment_type": "Κατάσταση",
            "gross_annual_income": "Ετήσιο Ακαθάριστο Εισόδημα (€, συμπ. 13ου, 14ου, άλλου μισθού)",
            "other_income_1_description": "Άλλη πηγή εισοδήματος 1",
            "other_income_1_amount": "Ποσό 1 (€)",
            "other_income_2_description": "Άλλη πηγή εισοδήματος 2",
            "other_income_2_amount": "Ποσό 2 (€)",
            "other_income_3_description": "Άλλη πηγή εισοδήματος 3",
            "other_income_3_amount": "Ποσό 3 (€)",
        }
        help_texts = {"gross_annual_income": "", "member_description": ""}

    def __init__(self, *args, member=IncomeDeclaration.Member.APPLICANT, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        if member != IncomeDeclaration.Member.OTHER:
            self.fields.pop("member_description")
        else:
            self.fields["member_description"].help_text = (
                "Σε περίπτωση περισσότερων μελών, αναφέρετε το σύνολο των εισοδημάτων τους."
            )
        self.fields["gross_annual_income"].required = False
        self.fields["gross_annual_income"].widget.attrs.update({"min": "0", "step": "0.01"})
        _style(self)

    def clean_gross_annual_income(self):
        value = self.cleaned_data.get("gross_annual_income")
        if value is not None and value < 0:
            raise forms.ValidationError("Το ποσό δεν μπορεί να είναι αρνητικό.")
        return value or 0

    def clean(self):
        cleaned = super().clean()
        for slot in IncomeDeclaration.OTHER_INCOME_SLOTS:
            amount = cleaned.get(f"other_income_{slot}_amount")
            if amount is not None and amount < 0:
                self.add_error(f"other_income_{slot}_amount", "Το ποσό δεν μπορεί να είναι αρνητικό.")
            if amount and not cleaned.get(f"other_income_{slot}_description"):
                self.add_error(f"other_income_{slot}_description", "Περιγράψτε την πηγή εισοδήματος.")
        return cleaned

    @property
    def is_empty(self) -> bool:
        data = self.cleaned_data
        return not any(
            data.get(name) for name in self.fields if name != "employment_type"
        ) and not data.get("employment_type")
