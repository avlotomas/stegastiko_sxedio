from datetime import date

from django import forms
from django.db.models import Count, Q

from applications.models import Person
from applications.person_identity import PERSON_FIELD_LABELS
from cases.models import SubmissionCycle
from core.appendix1 import appendix1_choices
from core.forms import IsoDateInput
from core.models import Community
from plot_applications.documents import DOCUMENT_CHOICES
from plot_applications.parameters import age_at
from plot_applications.rules import parameter
from plots.models import Plot
from plot_applications.models import (
    ApplicationChild,
    ApplicationParty,
    EligibilityOverride,
    IncomeDeclaration,
    Objection,
    PendingRequirement,
    PlotApplication,
    ResidenceCategory,
)

# Ενότ. 11 (Ι, ΙΙ, ΙV): η διαμονή είναι στην Κοινότητα της αίτησης, άρα η Κοινότητα διαμονής κλειδώνει σε αυτήν.
COMMUNITY_LOCKED_CATEGORIES = (
    ResidenceCategory.AUTOCHTHON,
    ResidenceCategory.DISPLACED,
    ResidenceCategory.REPATRIATED,
)

YES_NO_CHOICES = (
    ("True", "Ναι"),
    ("False", "Όχι"),
    ("", "Μη ορισμένο"),
)


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
    MINIMUM_REQUIRED_FIELDS = (
        "identity_number",
        "first_name",
        "last_name",
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
        kwargs.pop("is_draft", None)
        super().__init__(*args, **kwargs)
        self.is_required = required
        self.existing = self._existing_person()
        for name, field in self.fields.items():
            has_stored = self.existing is not None and getattr(self.existing, name) not in (None, "")
            if self.is_bound:
                field.required = (
                    required
                    and (name in self.MINIMUM_REQUIRED_FIELDS)
                    and (not has_stored or name == "identity_number")
                )
            else:
                field.required = required and (not has_stored or name == "identity_number")
        if self.existing is not None:
            for name in self.FIXED_FIELDS:
                if getattr(self.existing, name) not in (None, ""):
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
            if stored in (None, ""):
                cleaned[name] = posted if name == "date_of_birth" else (posted or "")
            elif posted not in (None, "") and posted != stored:
                self.add_error(
                    name,
                    f"Το ΑΔΤ {self.existing.identity_number} είναι ήδη καταχωρημένο και το πεδίο "
                    f"«{PERSON_FIELD_LABELS[name]}» δεν αλλάζει (καταχωρημένο: «{stored}»).",
                )
            else:
                cleaned[name] = stored
        return cleaned

    def _field_values(self) -> dict:
        return {
            name: (
                self.cleaned_data.get(name)
                if name == "date_of_birth"
                else (self.cleaned_data.get(name) or "").strip()
            )
            for name in self.FIXED_FIELDS
        }

    def get_or_create_person(self) -> Person:
        identity = self.cleaned_data["identity_number"].strip()
        values = self._field_values()
        if self.existing is not None:
            changed = False
            for name, value in values.items():
                if getattr(self.existing, name) in (None, "") and value not in (None, ""):
                    setattr(self.existing, name, value)
                    changed = True
            if changed:
                self.existing.save()
            return self.existing
        return Person.objects.create(
            identity_number=identity,
            **values,
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
        "Έχετε αποξενώσει εσείς (περιλ. συζύγου/συμβίου) ή οι γονείς σας ή οι γονείς του/της "
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
            "announcement",
            "submitted_on",
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
            "resides_in_controlled_areas",
            "origin_parent_description",
            "previous_residence_address",
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
            "applicant_signed",
            "spouse_signed",
            "sworn_declaration_date",
            "sworn_court",
            "sworn_by_applicant",
            "sworn_by_spouse",
            "attached_documents",
            "other_documents",
            "documents_complete_override",
            "documents_complete_reason",
        ]
        labels = {
            "announcement": "Γνωστοποίηση υποβολής αιτήσεων",
            "submitted_on": "Ημερομηνία υποβολής",
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
            "resides_in_controlled_areas": "Διαμένει σε ελεγχόμενες από την Κυπριακή Δημοκρατία περιοχές",
            "origin_parent_description": "Καταγωγή από την Κοινότητα ως προς ποιο γονέα",
            "previous_residence_address": "Διεύθυνση στην Κοινότητα κατά την περίοδο μόνιμης κατοίκησης",
            "residence_notes": "Αναλυτική περιγραφή / λοιπές πληροφορίες",
            "family_status": "Οικογενειακή κατάσταση",
            "single_parent_status": "Μονογονιός",
            "single_parent_other": "Άλλο (περιγραφή)",
            "has_dwelling_details": "Διευκρινίσεις (α)",
            "has_residential_land_details": "Διευκρινίσεις (β)",
            "has_alienated_property_details": "Διευκρινίσεις",
            "previous_housing_aid_details": "Επεξηγήσεις και διευκρινίσεις",
            "applicant_signed": "Υπογραφή Αιτητή/Αιτήτριας",
            "spouse_signed": "Υπογραφή Συζύγου/Συμβίου",
            "sworn_declaration_date": "Ημερομηνία ορκωμοσίας",
            "sworn_court": "Επαρχιακό Δικαστήριο",
            "sworn_by_applicant": "Ένορκη δήλωση Αιτητή/Αιτήτριας",
            "sworn_by_spouse": "Ένορκη δήλωση Συζύγου/Συμβίου",
            "other_documents": "Άλλα πιστοποιητικά",
            "documents_complete_override": "Τα πιστοποιητικά / δικαιολογητικά είναι εντάξει (παρά τις ελλείψεις)",
            "documents_complete_reason": "Περιγραφή λόγου ολοκλήρωσης δικαιολογητικών (προαιρετική)",
        }
        widgets = {
            "submitted_on": IsoDateInput(),
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
            "other_documents": forms.Textarea(attrs={"rows": 2}),
            "documents_complete_reason": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Αιτιολογήστε γιατί η αίτηση χαρακτηρίζεται ως ολοκληρωμένη παρά τα ελλείποντα δικαιολογητικά…",
                }
            ),
        }

    def __init__(self, data=None, *args, **kwargs):
        kwargs.pop("is_draft", None)
        prefix = kwargs.get("prefix")
        ann_key = f"{prefix}-announcement" if prefix else "announcement"
        comm_key = f"{prefix}-community" if prefix else "community"
        if data is not None and ann_key not in data and comm_key in data:
            data = data.copy()
            raw_comm = str(data.get(comm_key) or "").strip()
            if raw_comm.isdigit():
                comm_id = int(raw_comm)
                cycle = (
                    SubmissionCycle.objects.filter(plots__community_id=comm_id)
                    .exclude(stage=SubmissionCycle.Stage.CLOSED)
                    .order_by("-published_at", "-announcement_date", "-pk")
                    .first()
                    or SubmissionCycle.objects.filter(plots__community_id=comm_id)
                    .order_by("-published_at", "-announcement_date", "-pk")
                    .first()
                )
                if cycle is not None:
                    data[ann_key] = str(cycle.pk)
                else:
                    data[ann_key] = ""
            else:
                data[ann_key] = raw_comm
        super().__init__(data, *args, **kwargs)
        # Η Αίτηση συνδέεται με τη Γνωστοποίηση (η οποία προσφέρει τα οικόπεδα μίας Κοινότητας).
        announcements = SubmissionCycle.objects.prefetch_related("plots__community")
        if self.instance.pk and self.instance.announcement_id:
            announcements = announcements.filter(pk=self.instance.announcement_id)
        else:
            available_ids = (
                SubmissionCycle.objects.exclude(stage=SubmissionCycle.Stage.CLOSED)
                .filter(
                    plots__valuation_amount__isnull=False,
                    plots__disposal_price__isnull=False,
                    plots__community__is_active=True,
                )
                .exclude(plots__allocations__status="active")
                .values_list("pk", flat=True)
            )
            bound_id = None
            if self.is_bound:
                raw = self.data.get(self.add_prefix("announcement"))
                if raw and str(raw).isdigit():
                    bound_id = int(raw)
            elif self.initial.get("announcement"):
                init_val = self.initial["announcement"]
                bound_id = init_val.pk if hasattr(init_val, "pk") else (int(init_val) if str(init_val).isdigit() else None)
            q = Q(pk__in=available_ids)
            if bound_id:
                q |= Q(pk=bound_id)
            announcements = announcements.filter(q).distinct()
        announcement_field = self.fields["announcement"]
        announcement_field.queryset = announcements.order_by("-announcement_date", "-id")

        def _label(cycle: SubmissionCycle) -> str:
            comm = cycle.community
            plots_cnt = len(list(cycle.plots.all()))
            if comm is not None:
                return f"{comm.name} ({plots_cnt}) — γνωστοποίηση {cycle.announcement_date:%d/%m/%Y}"
            return f"Γνωστοποίηση {cycle.announcement_date:%d/%m/%Y} ({plots_cnt})"

        announcement_field.label_from_instance = _label
        self.community_names = {
            str(c.pk): (c.community.name if c.community is not None else "") for c in announcements
        }
        for name in ("submitted_on", "email", "residence_category", "family_status"):
            self.fields[name].required = not self.is_bound
        self.fields["residence_community"].required = False
        for field in self.fields.values():
            field.help_text = ""
        if self.instance.pk and self.instance.residence_category == ResidenceCategory.NEIGHBOURING:
            self.initial.setdefault("neighbouring_community", self.instance.residence_community)
        for bool_field in (
            "has_dwelling",
            "has_residential_land",
            "has_alienated_property",
            "previous_housing_aid",
        ):
            val = self.initial.get(bool_field, getattr(self.instance, bool_field, None))
            if val is True or val == "True":
                self.initial[bool_field] = "True"
            elif val is False or val == "False":
                self.initial[bool_field] = "False"
            else:
                self.initial[bool_field] = ""
        for name in ("residence_category", "family_status"):
            self.fields[name].choices = [c for c in self.fields[name].choices if c[0]]
        self.fields["single_parent_status"].choices = [
            c for c in self.fields["single_parent_status"].choices if c[0]
        ]
        _style(self)

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and cleaned.get("announcement") and (
            cleaned["announcement"].pk != self.instance.announcement_id
        ):
            self.add_error("announcement", "Η Γνωστοποίηση δεν αλλάζει μετά την καταχώριση.")
        if self.fields["family_status"].disabled and self.instance.pk:
            cleaned["family_status"] = self.instance.family_status
            cleaned["single_parent_status"] = self.instance.single_parent_status
            cleaned["single_parent_other"] = self.instance.single_parent_other
        elif cleaned.get("family_status") == PlotApplication.FamilyStatus.SINGLE_PARENT:
            status = cleaned.get("single_parent_status")
            if status != PlotApplication.SingleParentStatus.OTHER:
                cleaned["single_parent_other"] = ""
        else:
            cleaned["single_parent_status"] = ""
            cleaned["single_parent_other"] = ""
        if self.fields["residence_category"].disabled and self.instance.pk:
            cleaned["residence_community"] = self.instance.residence_community
        else:
            self._clean_residence_community(cleaned)
        if self.fields["documents_complete_override"].disabled and self.instance.pk:
            cleaned["documents_complete_override"] = self.instance.documents_complete_override
            cleaned["documents_complete_reason"] = self.instance.documents_complete_reason
        elif cleaned.get("documents_complete_override"):
            cleaned["documents_complete_reason"] = (cleaned.get("documents_complete_reason") or "").strip()
        else:
            cleaned["documents_complete_reason"] = ""
        return cleaned

    def _clean_residence_community(self, cleaned):
        category = cleaned.get("residence_category")
        if category in COMMUNITY_LOCKED_CATEGORIES:
            announcement = cleaned.get("announcement") or (
                self.instance.announcement if self.instance.pk and self.instance.announcement_id else None
            )
            community = announcement.community if announcement else None
            cleaned["residence_community"] = community.name if community else ""
        elif category == ResidenceCategory.NEIGHBOURING:
            chosen = cleaned.get("neighbouring_community") or ""
            cleaned["residence_community"] = chosen
        else:
            cleaned["residence_community"] = (cleaned.get("residence_community") or "").strip()


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
        kwargs.pop("is_draft", None)
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
        self.fields["citizenship"].required = not self.is_bound
        if not self.is_bound:
            self.fields["citizenship_other"].required = True
        self.fields["mobile_phone"].required = (role == ApplicationParty.Role.APPLICANT) or not self.is_bound
        _style(self)

    def clean(self):
        cleaned = super().clean()
        if self.fields["citizenship"].disabled and self.instance.pk:
            cleaned["citizenship"] = self.instance.citizenship
            cleaned["citizenship_other"] = self.instance.citizenship_other
            return cleaned
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

    def __init__(self, *args, submitted_on: date | None = None, is_draft: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.submitted_on = submitted_on
        self.is_draft = is_draft
        _style(self)

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        sex = cleaned.get("sex")
        dob = cleaned.get("date_of_birth")

        if status == ApplicationChild.Status.STUDENT and not sex:
            self.add_error("sex", "Για φοιτητή/τρια απαιτείται το φύλο (όριο 23 θήλυ / 25 άρρεν).")

        if dob is not None:
            ref_date = self.submitted_on or date.today()
            if dob > ref_date:
                self.add_error(
                    "date_of_birth",
                    "Η ημερομηνία γέννησης δεν μπορεί να είναι μεταγενέστερη της ημερομηνίας υποβολής.",
                )
            elif not self.is_draft:
                age = age_at(ref_date, dob)
                minor_limit = parameter("plotApp.minorMaxAge")
                if status == ApplicationChild.Status.MINOR and age >= minor_limit:
                    self.add_error(
                        "date_of_birth",
                        f"Ηλικία {age} ετών: για ανήλικο τέκνο η ηλικία πρέπει να είναι μικρότερη των {minor_limit} ετών (Ενότ. 10.Α).",
                    )
                elif status == ApplicationChild.Status.STUDENT and sex:
                    student_limit = parameter(
                        "plotApp.studentMaxAgeFemale" if sex == "F" else "plotApp.studentMaxAgeMale"
                    )
                    if age > student_limit:
                        self.add_error(
                            "date_of_birth",
                            f"Ηλικία {age} ετών: υπερβαίνει το όριο των {student_limit} ετών για φοιτητή/τρια (Ενότ. 10.Α).",
                        )
                elif status == ApplicationChild.Status.ADULT_DISABILITY and age < minor_limit:
                    self.add_error(
                        "date_of_birth",
                        f"Ηλικία {age} ετών: για ενήλικο τέκνο με αναπηρία η ηλικία πρέπει να είναι τουλάχιστον {minor_limit} ετών (Ενότ. 10.Α).",
                    )
        return cleaned


ChildFormSet = forms.inlineformset_factory(
    PlotApplication, ApplicationChild, form=ApplicationChildForm, extra=0, can_delete=True
)


class IncomeDeclarationForm(forms.ModelForm):
    member = forms.CharField(label="Μέλος", required=False, widget=forms.Select)

    class Meta:
        model = IncomeDeclaration
        fields = [
            "member",
            "employment_type",
            "description",
            "gross_annual_income",
        ]
        labels = {
            "member": "Μέλος",
            "employment_type": "Κατάσταση / Είδος",
            "description": "Περιγραφή / Πηγή",
            "gross_annual_income": "Ετήσιο Ποσό (€)",
        }
        help_texts = {
            "member": "",
            "employment_type": "",
            "description": "",
            "gross_annual_income": "",
        }

    def __init__(
        self,
        *args,
        is_couple=True,
        is_draft=False,
        children_choices=(),
        child_id_to_index=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.is_couple = is_couple
        self.is_draft = is_draft
        self.selected_child_index = None
        child_id_to_index = child_id_to_index or {}

        choices = [(IncomeDeclaration.Member.APPLICANT, IncomeDeclaration.Member.APPLICANT.label)]
        if is_couple:
            choices.append((IncomeDeclaration.Member.SPOUSE, IncomeDeclaration.Member.SPOUSE.label))
        if children_choices:
            choices.extend(children_choices)
        else:
            choices.append((IncomeDeclaration.Member.CHILD, IncomeDeclaration.Member.CHILD.label))
        choices.append((IncomeDeclaration.Member.OTHER, IncomeDeclaration.Member.OTHER.label))

        if (
            not self.is_bound
            and self.instance.pk
            and self.instance.member == IncomeDeclaration.Member.CHILD
            and self.instance.child_id in child_id_to_index
        ):
            self.initial["member"] = f"child:{child_id_to_index[self.instance.child_id]}"
        elif not self.is_bound and not self.instance.pk:
            self.initial.setdefault("member", IncomeDeclaration.Member.APPLICANT)

        self.fields["member"].widget.choices = choices
        self.fields["gross_annual_income"].required = False
        self.fields["gross_annual_income"].widget.attrs.update({"min": "0", "step": "0.01"})
        _style(self)

    def clean_member(self):
        raw = (self.cleaned_data.get("member") or "").strip()
        self.selected_child_index = None
        if not raw or raw == IncomeDeclaration.Member.APPLICANT:
            return IncomeDeclaration.Member.APPLICANT
        if raw in (
            IncomeDeclaration.Member.SPOUSE,
            IncomeDeclaration.Member.CHILD,
            IncomeDeclaration.Member.OTHER,
        ):
            return raw
        if raw.startswith("child:"):
            suffix = raw.split(":", 1)[1]
            if suffix.isdigit():
                self.selected_child_index = int(suffix)
                return IncomeDeclaration.Member.CHILD
        raise forms.ValidationError("Επιλέξτε έγκυρο μέλος οικογένειας.")

    def clean_gross_annual_income(self):
        value = self.cleaned_data.get("gross_annual_income")
        if value is not None and value < 0:
            raise forms.ValidationError("Το ποσό δεν μπορεί να είναι αρνητικό.")
        return value or 0

    def clean(self):
        cleaned = super().clean()
        if self.is_empty:
            return cleaned
        if cleaned.get("member") == IncomeDeclaration.Member.SPOUSE and not self.is_couple:
            return cleaned
        emp_type = cleaned.get("employment_type")
        amount = cleaned.get("gross_annual_income") or 0
        desc = (cleaned.get("description") or "").strip()
        if not self.is_draft:
            if not emp_type:
                self.add_error("employment_type", "Επιλέξτε κατάσταση / είδος εισοδήματος.")
            elif (
                emp_type != IncomeDeclaration.EmploymentType.UNEMPLOYED
                and amount <= 0
                and "gross_annual_income" not in self.errors
            ):
                self.add_error(
                    "gross_annual_income",
                    "Για την επιλεγμένη κατάσταση απαιτείται ετήσιο ποσό μεγαλύτερο του μηδενός.",
                )
            if emp_type == IncomeDeclaration.EmploymentType.OTHER_SOURCE and not desc:
                self.add_error("description", "Περιγράψτε την πηγή εισοδήματος.")
        return cleaned

    @property
    def is_empty(self) -> bool:
        data = getattr(self, "cleaned_data", {})
        return (
            not data.get("employment_type")
            and not (data.get("description") or "").strip()
            and not data.get("gross_annual_income")
        )


IncomeFormSet = forms.inlineformset_factory(
    PlotApplication, IncomeDeclaration, form=IncomeDeclarationForm, extra=0, can_delete=True
)


class PlotApplicationEmailForm(forms.Form):
    """Αποστολή email προς το άτομο/αιτητή με δυνατότητα προσθήκης ελλειπόντων δικαιολογητικών και χειροκίνητης επεξεργασίας."""

    recipient = forms.EmailField(
        label="Προς",
        max_length=255,
        required=False,
        widget=forms.EmailInput(attrs={"class": "input", "data-email-recipient-input": ""}),
    )
    subject = forms.CharField(
        label="Θέμα",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    body = forms.CharField(
        label="Κείμενο",
        required=False,
        widget=forms.Textarea(
            attrs={"class": "input", "rows": 10, "data-email-body": ""}
        ),
    )


class PlotApplicationEligibilityOverrideForm(forms.Form):
    """Χειροκίνητη αλλαγή του αποτελέσματος του λογισμικού κατά πόσο ο αιτητής είναι δικαιούχος (Ενότ. 6)."""

    eligibility_override = forms.ChoiceField(
        label="Αποτέλεσμα επιλεξιμότητας",
        required=False,
        choices=(("", "Όπως το αποτέλεσμα του λογισμικού"), *EligibilityOverride.choices),
        widget=forms.Select(attrs={"class": "input"}),
    )
    eligibility_override_reason = forms.CharField(
        label="Αιτιολογία χειροκίνητης αλλαγής",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 3,
                "placeholder": "Αιτιολογήστε γιατί αλλάζει το αποτέλεσμα του λογισμικού…",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        override = cleaned.get("eligibility_override") or ""
        reason = (cleaned.get("eligibility_override_reason") or "").strip()
        if override and not reason:
            self.add_error(
                "eligibility_override_reason",
                "Η αιτιολογία είναι υποχρεωτική όταν αλλάζει χειροκίνητα το αποτέλεσμα του λογισμικού.",
            )
        cleaned["eligibility_override"] = override
        cleaned["eligibility_override_reason"] = reason if override else ""
        return cleaned


class PlotApplicationIncompleteRejectionForm(forms.Form):
    """Απόρριψη αίτησης από τον λειτουργό με υποχρεωτικό λόγο σε ελεύθερο κείμενο."""

    required_css_class = "required"

    incomplete_rejection_reason = forms.CharField(
        label="Λόγος απόρριψης",
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 3,
                "required": "required",
                "placeholder": "Αναφέρετε τον λόγο απόρριψης της αίτησης…",
            }
        ),
        error_messages={"required": "Ο λόγος απόρριψης είναι υποχρεωτικός."},
    )

    def clean_incomplete_rejection_reason(self):
        reason = (self.cleaned_data.get("incomplete_rejection_reason") or "").strip()
        if not reason:
            raise forms.ValidationError("Ο λόγος απόρριψης είναι υποχρεωτικός.")
        return reason


class PlotApplicationDocumentsCompletenessForm(forms.Form):
    """Χειροκίνητος χαρακτηρισμός της αίτησης ως ολοκληρωμένης ως προς τα δικαιολογητικά με προαιρετική περιγραφή λόγου."""

    documents_complete_override = forms.BooleanField(
        label="Τα πιστοποιητικά / δικαιολογητικά είναι εντάξει (παρά τις ελλείψεις)",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
    )
    documents_complete_reason = forms.CharField(
        label="Περιγραφή λόγου ολοκλήρωσης δικαιολογητικών (προαιρετική)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 2,
                "placeholder": "Προαιρετικά: αιτιολογήστε γιατί τα δικαιολογητικά θεωρούνται εντάξει παρά τις ελλείψεις…",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        override = bool(cleaned.get("documents_complete_override"))
        reason = (cleaned.get("documents_complete_reason") or "").strip()
        cleaned["documents_complete_reason"] = reason if override else ""
        return cleaned


