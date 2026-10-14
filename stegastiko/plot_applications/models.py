"""Αίτηση για Παραχώρηση Οικοπέδου — Παράρτημα 3 του Σχεδίου (Ενότ. 5).

A separate model from `applications.Application`: it follows the official form the
citizens fill in, section by section (1–13 + Ένορκη Δήλωση + Κατάλογος Δικαιολογητικών
+ «Για Επίσημη Χρήση»). Persons are shared with the «Άτομα» registry (`Person`).
"""

from decimal import Decimal

from django.db import models

from applications.models import Person
from core.models import AuditedModel, Community


class ResidenceCategory(models.TextChoices):
    """Ενότητα 2 της Αίτησης / Ενότ. 11 του Σχεδίου (σειρά = πρωτεύουσα προτεραιότητα)."""

    AUTOCHTHON = "autochthon", "(Α) Αυτόχθονας"
    DISPLACED = "displaced", "(Α) Εκτοπισθείς"
    INTERNAL_EMIGRANT = "internal_emigrant", "(Β) Απόδημος Εσωτερικού"
    REPATRIATED = "repatriated", "(Γ) Επαναπατρισθείς / Απόδημος Εξωτερικού"
    NEIGHBOURING = "neighbouring", "(Δ) Κάτοικος Γειτονικής Κοινότητας"


class EligibilityResult(models.TextChoices):
    PASS = "pass", "Κατ' αρχήν πληροί"
    FAIL = "fail", "Δεν πληροί"
    PENDING = "pending", "Εκκρεμεί έλεγχος"


class PlotApplication(AuditedModel):
    class FamilyStatus(models.TextChoices):
        MARRIED = "married", "Ζεύγος — Έγγαμος/η"
        CIVIL_PARTNERSHIP = "civil_partnership", "Ζεύγος — Σύμφωνο Συμβίωσης"
        SINGLE_PARENT = "single_parent", "Μονογονεϊκή Οικογένεια"

    class SingleParentStatus(models.TextChoices):
        WIDOWED = "widowed", "Χήρος/α"
        DIVORCED = "divorced", "Διαζευγμένος/η"
        OTHER = "other", "Άλλο"

    COUPLE_STATUSES = (FamilyStatus.MARRIED, FamilyStatus.CIVIL_PARTNERSHIP)

    # «Για Επίσημη Χρήση»
    community = models.ForeignKey(
        Community,
        on_delete=models.PROTECT,
        related_name="plot_applications",
        help_text="Κοινότητα στην οποία ζητείται η παραχώρηση οικοπέδου (Παράρτημα 3, Ενότ. 5)",
    )
    protocol_number = models.CharField(max_length=32, unique=True)
    submitted_on = models.DateField(help_text="Ημερομηνία υποβολής (Ενότ. 5)")
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.CharField(max_length=255, blank=True)
    district_file_number = models.CharField(max_length=64, blank=True)

    # 1. Προσωπικά στοιχεία αιτητή/αιτήτριας + 5. συζύγου/συμβίου (σταθερά στοιχεία στο μητρώο Ατόμων)
    applicant = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="plot_applications_as_applicant"
    )
    spouse = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plot_applications_as_spouse",
    )
    email = models.EmailField(
        help_text="Έγκυρη ηλεκτρονική διεύθυνση για την επίσημη επικοινωνία (Ενότ. 6, 7)"
    )
    correspondence_street = models.CharField(max_length=255, blank=True)
    correspondence_number = models.CharField(max_length=32, blank=True)
    correspondence_apartment = models.CharField(max_length=32, blank=True)
    correspondence_community = models.CharField(max_length=255, blank=True)
    correspondence_postal_code = models.CharField(max_length=16, blank=True)
    correspondence_district = models.CharField(max_length=128, blank=True)

    # 2. Τόπος διαμονής αιτητή/αιτήτριας
    residence_category = models.CharField(max_length=32, choices=ResidenceCategory.choices)
    residence_street = models.CharField(max_length=255, blank=True)
    residence_number = models.CharField(max_length=32, blank=True)
    residence_apartment = models.CharField(max_length=32, blank=True)
    residence_postal_code = models.CharField(max_length=16, blank=True)
    residence_community = models.CharField(
        max_length=255, help_text="Κοινότητα / Δ.Δ. διαμονής (για (Δ): η Γειτονική Κοινότητα)"
    )
    neighbouring_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="(Δ) Απόσταση από τα όρια της Κοινότητας, κατά μετρήσεις ΤΚΧ (Ενότ. 10.Γ)",
    )
    neighbouring_subcategory = models.CharField(
        max_length=32,
        choices=[c for c in ResidenceCategory.choices if c[0] != ResidenceCategory.NEIGHBOURING],
        blank=True,
        help_text="(Δ) Ιδιότητα σε σχέση με τη Γειτονική Κοινότητα (Ενότ. 11.V — κατ' αναλογία)",
    )
    origin_parent_description = models.TextField(
        blank=True, help_text="(Β) Καταγωγή από την Κοινότητα ως προς ποιο γονέα"
    )
    previous_residence_address = models.CharField(
        max_length=255, blank=True, help_text="(Β) Διεύθυνση κατά την περίοδο μόνιμης κατοίκησης"
    )
    previous_residence_from = models.DateField(null=True, blank=True)
    previous_residence_to = models.DateField(null=True, blank=True)
    community_residence_since = models.DateField(
        null=True, blank=True, help_text="(Γ) Έναρξη μόνιμης διαμονής στην Κοινότητα μετά την επιστροφή"
    )
    abroad_from = models.DateField(null=True, blank=True, help_text="(Γ) Παραμονή στο εξωτερικό από")
    abroad_to = models.DateField(null=True, blank=True, help_text="(Γ) Παραμονή στο εξωτερικό μέχρι")
    residence_notes = models.TextField(blank=True, help_text="Αναλυτική περιγραφή / λοιπές πληροφορίες")

    # 3. Οικογενειακή κατάσταση
    family_status = models.CharField(max_length=32, choices=FamilyStatus.choices)
    single_parent_status = models.CharField(
        max_length=16, choices=SingleParentStatus.choices, blank=True
    )
    single_parent_other = models.CharField(max_length=255, blank=True)

    # 9. Άλλη ακίνητη ιδιοκτησία (Ενότ. 10.Δ, 10.Ε)
    has_dwelling = models.BooleanField(null=True)
    has_dwelling_details = models.TextField(blank=True)
    has_residential_land = models.BooleanField(null=True)
    has_residential_land_details = models.TextField(blank=True)
    has_alienated_property = models.BooleanField(null=True)
    has_alienated_property_details = models.TextField(blank=True)

    # 10. Παραχώρηση άλλης κρατικής στεγαστικής βοήθειας (Ενότ. 20.3)
    previous_housing_aid = models.BooleanField(null=True)
    previous_housing_aid_details = models.TextField(blank=True)

    # 11. Υποβολή άλλης αίτησης στο πλαίσιο του Σχεδίου
    other_application_choice_1 = models.CharField(max_length=255, blank=True)
    other_application_choice_2 = models.CharField(max_length=255, blank=True)
    other_application_choice_3 = models.CharField(max_length=255, blank=True)
    other_applications_notes = models.TextField(blank=True)

    # 12. Υπεύθυνη δήλωση email · 13. Υπογραφές (Ενότ. 5) · Ένορκη δήλωση
    email_declaration_accepted = models.BooleanField(default=False)
    applicant_signed = models.BooleanField(default=False)
    spouse_signed = models.BooleanField(default=False)
    sworn_declaration_date = models.DateField(null=True, blank=True)
    sworn_court = models.CharField(max_length=128, blank=True, help_text="Επαρχιακό Δικαστήριο")
    sworn_by_applicant = models.BooleanField(default=False)
    sworn_by_spouse = models.BooleanField(default=False)

    # Κατάλογος απαιτούμενων δικαιολογητικών (κωδικοί του documents.DOCUMENT_CATALOG)
    attached_documents = models.JSONField(default=list, blank=True)
    other_documents = models.TextField(blank=True, help_text="Άλλα πιστοποιητικά που επισυνάπτονται")

    comments = models.TextField(blank=True)

    # Αποτέλεσμα αυτόματου ελέγχου (υπολογίζεται σε κάθε αποθήκευση — rules.evaluate)
    children_count = models.PositiveIntegerField(default=0)
    recognized_children_count = models.PositiveIntegerField(default=0)
    family_members_count = models.PositiveIntegerField(default=0)
    family_income_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    eligibility_result = models.CharField(
        max_length=16, choices=EligibilityResult.choices, default=EligibilityResult.PENDING
    )
    eligibility_details = models.JSONField(default=list, blank=True)
    priority_primary = models.PositiveSmallIntegerField(null=True, blank=True)
    priority_secondary = models.PositiveSmallIntegerField(null=True, blank=True)
    priority_label = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-submitted_on", "-id")

    def __str__(self):
        return self.protocol_number

    @property
    def is_couple(self) -> bool:
        return self.family_status in self.COUPLE_STATUSES

    def party(self, role):
        return next((p for p in self.parties.all() if p.role == role), None)

    @property
    def applicant_party(self):
        return self.party(ApplicationParty.Role.APPLICANT)

    @property
    def spouse_party(self):
        return self.party(ApplicationParty.Role.SPOUSE)


class ApplicationParty(AuditedModel):
    """Στοιχεία προσώπου που δηλώνονται σε κάθε αίτηση (Ενότητες 1, 4, 5, 6 της Αίτησης)."""

    class Role(models.TextChoices):
        APPLICANT = "applicant", "Αιτητής/τρια"
        SPOUSE = "spouse", "Σύζυγος/Συμβίος"

    class Citizenship(models.TextChoices):
        CYPRIOT = "cypriot", "Κύπριος Πολίτης"
        REPATRIATED = "repatriated", "Επαναπατρισθείς/είσα Κύπριος/α"
        EU = "eu", "Πολίτης Κράτους μέλους ΕΕ"
        OTHER = "other", "Άλλη"

    CYPRIOT_CITIZENSHIPS = (Citizenship.CYPRIOT, Citizenship.REPATRIATED)

    application = models.ForeignKey(PlotApplication, on_delete=models.CASCADE, related_name="parties")
    role = models.CharField(max_length=16, choices=Role.choices)
    social_insurance_number = models.CharField(max_length=32, blank=True)
    refugee_identity_number = models.CharField(max_length=64, blank=True)
    alien_registration_number = models.CharField(max_length=64, blank=True)
    citizenship = models.CharField(max_length=16, choices=Citizenship.choices)
    citizenship_other = models.CharField(max_length=128, blank=True)
    mobile_phone = models.CharField(max_length=32, blank=True)
    landline_phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    is_self_employed = models.BooleanField(default=False)
    is_employee = models.BooleanField(default=False)
    is_unemployed = models.BooleanField(default=False)
    has_disability = models.BooleanField(default=False)
    employer_details = models.TextField(blank=True)

    class Meta:
        ordering = ("application", "role")
        unique_together = ("application", "role")

    @property
    def is_cypriot(self) -> bool:
        return self.citizenship in self.CYPRIOT_CITIZENSHIPS


class ApplicationChild(AuditedModel):
    """7. Τέκνα αιτητή/τριας που ζουν στην ίδια κατοικία (Ενότ. 10.Α)."""

    class Status(models.TextChoices):
        MINOR = "minor", "Ανήλικο τέκνο μέχρι 18 ετών"
        NATIONAL_GUARD = "national_guard", "Στρατιώτης (Εθνοφρουρός)"
        STUDENT = "student", "Φοιτητής/τρια"
        ADULT_DISABILITY = "adult_disability", "Ενήλικο τέκνο με αναπηρία"

    class Sex(models.TextChoices):
        FEMALE = "F", "Θήλυ"
        MALE = "M", "Άρρεν"

    application = models.ForeignKey(PlotApplication, on_delete=models.CASCADE, related_name="children")
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    date_of_birth = models.DateField()
    identity_number = models.CharField(max_length=32, blank=True)
    sex = models.CharField(
        max_length=1,
        choices=Sex.choices,
        blank=True,
        help_text="Απαιτείται για φοιτητές (όριο 23 θήλυ / 25 άρρεν, Ενότ. 10.Α)",
    )
    status = models.CharField(max_length=32, choices=Status.choices)

    class Meta:
        ordering = ("date_of_birth", "id")


class ResidenceInterruption(AuditedModel):
    """Διακοπή μόνιμης διαμονής που δεν τη διακόπτει (Ενότ. 11.I–II): ΕΦ, φοίτηση, νοσηλεία."""

    class Reason(models.TextChoices):
        NATIONAL_GUARD = "national_guard", "Θητεία στην Εθνική Φρουρά"
        TERTIARY_EDUCATION = "tertiary_education", "Φοίτηση στην τριτοβάθμια εκπαίδευση"
        HOSPITALISATION = "hospitalisation", "Ιατρικό πρόβλημα με νοσηλεία"

    application = models.ForeignKey(
        PlotApplication, on_delete=models.CASCADE, related_name="residence_interruptions"
    )
    reason = models.CharField(max_length=32, choices=Reason.choices)
    date_from = models.DateField()
    date_to = models.DateField()

    class Meta:
        ordering = ("date_from", "id")


class IncomeDeclaration(AuditedModel):
    """8. Εισοδήματα του έτους που προηγείται της αίτησης (Ενότ. 10.Στ)."""

    class Member(models.TextChoices):
        APPLICANT = "applicant", "Αιτητής/τρια"
        SPOUSE = "spouse", "Σύζυγος/Συμβίος"
        OTHER = "other", "Άλλο μέλος της οικογένειας"

    class EmploymentType(models.TextChoices):
        EMPLOYEE = "employee", "Μισθωτός Εργαζόμενος"
        SELF_EMPLOYED = "self_employed", "Αυτοτελώς Εργαζόμενος"
        UNEMPLOYED = "unemployed", "Άνεργος"

    application = models.ForeignKey(PlotApplication, on_delete=models.CASCADE, related_name="incomes")
    member = models.CharField(max_length=16, choices=Member.choices)
    member_description = models.CharField(
        max_length=255, blank=True, help_text="Δήλωση μέλους οικογένειας (για «Άλλο μέλος»)"
    )
    employment_type = models.CharField(max_length=16, choices=EmploymentType.choices, blank=True)
    gross_annual_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Ετήσιο ακαθάριστο εισόδημα (συμπ. 13ου, 14ου, άλλου μισθού)",
    )
    other_income_1_description = models.CharField(max_length=255, blank=True)
    other_income_1_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    other_income_2_description = models.CharField(max_length=255, blank=True)
    other_income_2_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    other_income_3_description = models.CharField(max_length=255, blank=True)
    other_income_3_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ("application", "member")
        unique_together = ("application", "member")

    OTHER_INCOME_SLOTS = (1, 2, 3)

    @property
    def other_incomes(self):
        rows = []
        for slot in self.OTHER_INCOME_SLOTS:
            description = getattr(self, f"other_income_{slot}_description")
            amount = getattr(self, f"other_income_{slot}_amount")
            if description or amount:
                rows.append((description, amount or Decimal("0")))
        return rows

    @property
    def total(self) -> Decimal:
        return (self.gross_annual_income or Decimal("0")) + sum(
            (amount for _, amount in self.other_incomes), Decimal("0")
        )
