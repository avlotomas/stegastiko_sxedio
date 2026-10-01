from decimal import Decimal

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from core.models import Attachment, AuditedModel, Communication, Community


class YesNo(models.TextChoices):
    YES = "yes", "ΝΑΙ"
    NO = "no", "ΟΧΙ"


# §Α.3.3 A new-division case runs every section; an unallocated-plots case has no
# Αίτηση Α, so its plots are registered straight into 8.8 and announced in 9.
SECTION_KEYS_NEW_DIVISION = ("1", "2", "3", "4", "5", "6", "7", "8", "8-plots", "9")
SECTION_KEYS_UNALLOCATED = ("1", "8-plots", "9")


class Case(AuditedModel):
    class CaseType(models.TextChoices):
        NEW_DIVISION = "new_division", "Νέο αίτημα διαχωρισμού"
        UNALLOCATED_PLOTS = "unallocated_plots", "Αδιάθετα οικόπεδα"

    class Recommendation(models.TextChoices):
        POSITIVE = "positive", "Θετική"
        NEGATIVE = "negative", "Αρνητική"

    class MinistryDecision(models.TextChoices):
        APPROVED = "approved", "Έγκριση"
        REJECTED = "rejected", "Απόρριψη"

    class DesignStatus(models.TextChoices):
        PENDING = "pending", "Εκκρεμεί"
        COMPLETED = "completed", "Ολοκληρώθηκε"

    class TpoResponse(models.TextChoices):
        POSITIVE = "positive", "Θετική"
        CONDITIONAL = "conditional", "Θετική υπό όρους"
        NEGATIVE = "negative", "Αρνητική"

    class ContractDurationUnit(models.TextChoices):
        MONTHS = "months", "Μήνες"
        YEARS = "years", "Έτη"

    community = models.ForeignKey(Community, on_delete=models.PROTECT, related_name="cases")
    case_number = models.CharField(max_length=64, unique=True, help_text="1.1 Μοναδικός αριθμός υπόθεσης")
    case_type = models.CharField(max_length=32, choices=CaseType.choices, default=CaseType.NEW_DIVISION)
    start_date = models.DateField(help_text="1.1 Ημερομηνία έναρξης διαδικασίας")
    submitted_at = models.DateField(
        null=True, blank=True, help_text="1.1 Ημερομηνία υποβολής αίτησης Κ.Σ./Δ.Δ."
    )
    contact_email = models.EmailField(
        help_text="1.1 Ηλεκτρονική διεύθυνση επικοινωνίας Κ.Σ./Δ.Δ."
    )
    comments = models.TextField(blank=True, help_text="1.3 Σχόλια / Παρατηρήσεις Ενότητας 1")

    priority_turkish_cypriot_properties = models.BooleanField(
        default=False, help_text="1.2 Μεγάλες εκτάσεις τουρκοκυπριακών περιουσιών"
    )
    priority_protection_zones = models.BooleanField(
        default=False, help_text="1.2 Επηρεασμός συνολικής έκτασης γης από Ζώνες Προστασίας"
    )
    priority_nuisance_developments = models.BooleanField(
        default=False, help_text="1.2 Οχληρές αναπτύξεις στα διοικητικά όρια της Κοινότητας"
    )
    priority_limited_private_land = models.BooleanField(
        default=False, help_text="1.2 Μειωμένη διαθεσιμότητα ιδιωτικής γης για οικιστική ανάπτυξη"
    )
    priority_other = models.CharField(
        max_length=255, blank=True, help_text="1.2 Άλλο ιδιαίτερο χαρακτηριστικό (περιγραφή)"
    )
    priority_documentation = models.TextField(
        blank=True,
        help_text="1.2 Σχόλια/Παρατηρήσεις",
    )

    section2_comments = models.TextField(blank=True, help_text="2 Σχόλια / Παρατηρήσεις Ενότητας 2")

    state_land_remains_sufficient = models.CharField(
        max_length=8,
        choices=YesNo.choices,
        blank=True,
        help_text=(
            "3.2 Μετά την προτεινόμενη αξιοποίηση θα παραμένουν στην Κοινότητα "
            "ικανοποιητικές εκτάσεις κρατικής γης;"
        ),
    )
    state_land_comments = models.TextField(blank=True, help_text="3.2 Σχόλια / Παρατηρήσεις")
    section3_comments = models.TextField(
        blank=True, help_text="3.3 Σχόλια / Παρατηρήσεις Ενότητας 3"
    )

    access_technical_evaluation = models.TextField(
        blank=True, help_text="4.3 Τεχνική αξιολόγηση πρόσβασης στο/στα τεμάχιο/α"
    )
    section4_comments = models.TextField(blank=True, help_text="4.5 Σχόλια / Παρατηρήσεις Ενότητας 4")
    engineer_full_name = models.CharField(
        max_length=255, blank=True, help_text="4.6 Ονοματεπώνυμο μηχανικού"
    )
    technical_visit_date = models.DateField(
        null=True, blank=True, help_text="4.6 Ημερομηνία επισκεψης"
    )
    # 4.4 files of the technical evaluation as a whole are kept on the case (section_ref "4.4").
    attachments = GenericRelation(Attachment)

    recommendation_letter_date = models.DateField(
        null=True, blank=True, help_text="7 Ημερομηνία αποστολής επιστολής σύστασης"
    )
    recommendation = models.CharField(
        max_length=16,
        choices=Recommendation.choices,
        blank=True,
        help_text="7 Σύσταση Επαρχιακής Διοίκησης",
    )
    ministry_response_date = models.DateField(
        null=True, blank=True, help_text="7 Ημερομηνία λήψης απάντησης ΥΠΕΣ"
    )
    ministry_decision = models.CharField(
        max_length=16, choices=MinistryDecision.choices, blank=True, help_text="7 Απόφαση ΥΠΕΣ"
    )
    section7_comments = models.TextField(blank=True, help_text="7 Σχόλια / Παρατηρήσεις Ενότητας 7")

    survey_assignment_date = models.DateField(
        null=True, blank=True, help_text="8.1 Ημερομηνία ανάθεσης μελέτης"
    )
    surveyor_name = models.CharField(
        max_length=255, blank=True, help_text="8.1 Ονοματεπώνυμο ιδιώτη αρμόδιου χωρομέτρη"
    )
    surveyor_phone = models.CharField(max_length=64, blank=True, help_text="8.1 Τηλέφωνο χωρομέτρη")
    surveyor_email = models.EmailField(blank=True, help_text="8.1 Email χωρομέτρη")
    survey_assignment_comments = models.TextField(blank=True, help_text="8.1 Σχόλια")

    division_design_status = models.CharField(
        max_length=16, choices=DesignStatus.choices, blank=True, help_text="8.2 Κατάσταση σχεδιασμού"
    )
    division_design_completed_on = models.DateField(
        null=True, blank=True, help_text="8.2 Ημερομηνία ολοκλήρωσης σχεδιασμού"
    )
    division_design_plots_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="8.2 Αριθμός οικοπέδων στον ολοκληρωμένο σχεδιασμό"
    )
    division_design_comments = models.TextField(blank=True, help_text="8.2 Σχόλια")

    tpo_application_date = models.DateField(
        null=True, blank=True, help_text="8.3 Ημερομηνία υποβολής αίτησης στο ΤΠΟ"
    )
    tpo_application_number = models.CharField(
        max_length=64, blank=True, help_text="8.3 Αριθμός αίτησης ΤΠΟ"
    )
    tpo_response = models.CharField(
        max_length=16, choices=TpoResponse.choices, blank=True, help_text="8.3 Απάντηση Διευθυντή ΤΠΟ"
    )
    tpo_response_date = models.DateField(
        null=True, blank=True, help_text="8.3 Ημερομηνία απάντησης ΤΠΟ"
    )
    tpo_comments = models.TextField(blank=True, help_text="8.3 Σχόλια")

    tender_announcement_date = models.DateField(
        null=True, blank=True, help_text="8.5 Ημερομηνία προκήρυξης διαγωνισμού"
    )
    tender_award_date = models.DateField(
        null=True, blank=True, help_text="8.5 Ημερομηνία κατακύρωσης"
    )
    contractor_name = models.CharField(
        max_length=255, blank=True, help_text="8.5 Ανάδοχος / πρόσωπο ανάθεσης"
    )
    contractor_phone = models.CharField(max_length=64, blank=True, help_text="8.5 Τηλέφωνο αναδόχου")
    contractor_email = models.EmailField(blank=True, help_text="8.5 Email αναδόχου")
    contract_duration_value = models.PositiveIntegerField(
        null=True, blank=True, help_text="8.5 Διάρκεια σύμβασης (αριθμός)"
    )
    contract_duration_unit = models.CharField(
        max_length=16,
        choices=ContractDurationUnit.choices,
        blank=True,
        help_text="8.5 Διάρκεια σύμβασης (μονάδα)",
    )
    tender_comments = models.TextField(blank=True, help_text="8.5 Σχόλια")

    works_progress_stage = models.CharField(
        max_length=255, blank=True, help_text="8.6 Τρέχον στάδιο / πορεία εργασιών"
    )
    works_progress_updated_on = models.DateField(
        null=True, blank=True, help_text="8.6 Ημερομηνία ενημέρωσης πορείας"
    )
    works_progress_comments = models.TextField(blank=True, help_text="8.6 Σχόλια γενικής πορείας")

    dls_application_date = models.DateField(
        null=True, blank=True, help_text="8.7 Ημερομηνία υποβολής αίτησης στο ΤΚΧ"
    )
    dls_file_number = models.CharField(max_length=64, blank=True, help_text="8.7 Αριθμός φακέλου ΤΚΧ")
    dls_response_date = models.DateField(
        null=True, blank=True, help_text="8.7 Ημερομηνία απάντησης / ολοκλήρωσης ΤΚΧ"
    )
    dls_comments = models.TextField(blank=True, help_text="8.7 Σχόλια")

    section8_comments = models.TextField(blank=True, help_text="8 Σχόλια / Παρατηρήσεις Ενότητας 8")

    class Meta:
        ordering = ("-start_date", "-id")

    def __str__(self):
        return self.case_number

    def _audit_context(self):
        # The case folder shows aggregate history, so its own events carry the case id.
        return self.pk, None, getattr(self, "_section_ref", "")

    @property
    def priority_characteristics(self):
        """1.2 selected characteristics as Greek labels, for the 6.1 summary."""
        labels = []
        for field_name in (
            "priority_turkish_cypriot_properties",
            "priority_protection_zones",
            "priority_nuisance_developments",
            "priority_limited_private_land",
        ):
            if getattr(self, field_name):
                labels.append(self._meta.get_field(field_name).help_text.removeprefix("1.2 "))
        if self.priority_other:
            labels.append(self.priority_other)
        return labels

    @property
    def latest_infrastructure_check(self):
        return self.infrastructure_checks.first()

    @property
    def is_new_division(self):
        return self.case_type == self.CaseType.NEW_DIVISION

    @property
    def latest_completeness_check(self):
        """2.1 Current completeness result for this case (latest by date)."""
        return self.completeness_checks.order_by("-check_date", "-sequence", "-id").first()

    @property
    def completeness_result(self):
        check = self.latest_completeness_check
        return check.result if check else ""

    @property
    def completeness_result_display(self):
        check = self.latest_completeness_check
        return check.get_result_display() if check else ""

    @property
    def applicable_sections(self):
        """§Α.3.3 Which sections apply depends on the case type."""
        if self.is_new_division:
            return SECTION_KEYS_NEW_DIVISION
        return SECTION_KEYS_UNALLOCATED


class CompletenessCheck(AuditedModel):
    """2.1 One dated completeness check of the Κ.Σ. application."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="completeness_checks")
    sequence = models.PositiveIntegerField(help_text="2 Αύξουσα αρίθμηση ελέγχου (1ος, 2ος, …)")
    check_date = models.DateField(help_text="2 Ημερομηνία ελέγχου")
    result = models.CharField(
        max_length=8,
        choices=YesNo.choices,
        help_text="2 Η αίτηση Κ.Σ., τα απαιτούμενα στοιχεία και ο κατάλογος ≥10 οικογενειών είναι πλήρη",
    )
    deficiencies = models.TextField(
        blank=True, help_text="2 Ελλείψεις / Απαιτούμενα συμπληρωματικά στοιχεία (όταν ΟΧΙ)"
    )
    comments = models.TextField(blank=True, help_text="2 Σχόλια ελέγχου")
    communications = GenericRelation(Communication)

    class Meta:
        ordering = ("-check_date", "-sequence", "-id")
        unique_together = ("case", "sequence")

    def __str__(self):
        return f"{self.case.case_number} — {self.sequence}ος έλεγχος"

    @property
    def row_label(self):
        return f"{self.sequence}ος έλεγχος — {self.check_date}"

    @property
    def is_complete(self):
        return self.result == YesNo.YES

    @property
    def can_delete(self):
        """Checks with sent emails stay immutable for traceability."""
        return not self.communications.exists()

    def save(self, *args, **kwargs):
        if not self.sequence:
            last = (
                CompletenessCheck.objects.filter(case=self.case)
                .order_by("-sequence")
                .values_list("sequence", flat=True)
                .first()
            )
            self.sequence = (last or 0) + 1
        return super().save(*args, **kwargs)


class LandPlot(AuditedModel):
    class SuitabilityDecision(models.TextChoices):
        SUITABLE = "suitable", "Κατάλληλο"
        CONDITIONAL = "conditional", "Κατάλληλο υπό προϋποθέσεις"
        UNSUITABLE = "unsuitable", "Μη κατάλληλο"

    class Morphology(models.TextChoices):
        FLAT = "flat", "Επίπεδο έδαφος"
        MILD = "mild", "Ήπιες υψομετρικές διαφορές"
        STEEP = "steep", "Έντονες υψομετρικές διαφορές"
        OTHER = "other", "Άλλη τεχνική ιδιαιτερότητα"

    class OwnershipStatus(models.TextChoices):
        STATE_LAND = "state_land", "Κρατική γη"
        OTHER = "other", "Άλλη ιδιοκτησία"

    class Access(models.TextChoices):
        PUBLIC_ROAD = "public_road", "Πρόσβαση σε εγγεγραμμένο δημόσιο δρόμο"
        OTHER = "other", "Άλλο"

    TECHNICAL_EVALUATION_FIELDS = (
        "morphology",
        "morphology_other",
        "morphology_comments",
        "usable_area_sqm",
        "estimated_cost",
        "estimated_plots_count",
        "technical_suitability",
    )

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="land_plots")
    parcel_number = models.CharField(max_length=64, help_text="3.1 Αρ. τεμαχίου")
    sheet_plan = models.CharField(max_length=64, blank=True, help_text="3.1 Φύλλο/Σχέδιο")
    location = models.CharField(max_length=255, blank=True, help_text="3.1 Τοποθεσία")
    ownership_status = models.CharField(
        max_length=16,
        choices=OwnershipStatus.choices,
        blank=True,
        help_text="3.1 Ιδιοκτησιακό καθεστώς",
    )
    ownership_other = models.CharField(
        max_length=255, blank=True, help_text="3.1 Είδος άλλης ιδιοκτησίας"
    )
    area_sqm = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="3.1 Εμβαδόν (τ.μ.)"
    )
    zone = models.CharField(max_length=128, blank=True, help_text="3.1 Πολεοδομική Ζώνη")
    inside_development_zone = models.CharField(
        max_length=8, choices=YesNo.choices, blank=True, help_text="3.1 Εντός Ορίου Ανάπτυξης"
    )
    access = models.CharField(
        max_length=16, choices=Access.choices, blank=True, help_text="3.1 Πρόσβαση"
    )
    access_other = models.CharField(
        max_length=255, blank=True, help_text="3.1 Διευκρίνιση άλλης πρόσβασης"
    )
    comments = models.TextField(blank=True, help_text="3.1 Σχόλια / Παρατηρήσεις")
    attachments = GenericRelation(Attachment)
    morphology = models.CharField(
        max_length=16, choices=Morphology.choices, blank=True, help_text="4.1 Μορφολογία"
    )
    morphology_other = models.CharField(
        max_length=255, blank=True, help_text="4.1 Περιγραφή άλλης τεχνικής ιδιαιτερότητας"
    )
    morphology_comments = models.TextField(blank=True, help_text="4.1 Σχόλια Μορφολογίας")
    usable_area_sqm = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="4.1 Αξιοποιήσιμο εμβαδόν γης (τ.μ.)",
    )
    estimated_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="4.1 Εκτιμώμενο κόστος",
    )
    estimated_plots_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="4.1 Εκτιμώμενος αριθμός οικοπέδων"
    )
    technical_suitability = models.CharField(
        max_length=16,
        choices=SuitabilityDecision.choices,
        blank=True,
        help_text="4.1 Τεχνική Καταλληλότητα",
    )
    suitability_decision = models.CharField(
        max_length=16,
        choices=SuitabilityDecision.choices,
        blank=True,
        help_text="6.6 Απόφαση Καταλληλότητας",
    )
    suitability_justification = models.TextField(blank=True, help_text="6.6 Αιτιολόγηση")

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.case.case_number} - {self.parcel_number}"

    @property
    def ownership_display(self):
        """3.1 «Άλλη ιδιοκτησία» carries its kind in the same cell."""
        if self.ownership_status == self.OwnershipStatus.OTHER and self.ownership_other:
            return f"{self.get_ownership_status_display()}: {self.ownership_other}"
        return self.get_ownership_status_display()

    @property
    def access_display(self):
        """3.1 «Άλλο» carries its description in the same cell."""
        if self.access == self.Access.OTHER and self.access_other:
            return f"{self.get_access_display()}: {self.access_other}"
        return self.get_access_display()

    @property
    def morphology_display(self):
        """4.1 «Άλλη τεχνική ιδιαιτερότητα» carries its description in the same cell."""
        if self.morphology == self.Morphology.OTHER and self.morphology_other:
            return f"{self.get_morphology_display()}: {self.morphology_other}"
        return self.get_morphology_display()

    @property
    def has_technical_evaluation(self):
        """Any 4.1 value recorded for this plot."""
        return any(
            getattr(self, name) not in (None, "") for name in self.TECHNICAL_EVALUATION_FIELDS
        )

    @property
    def deletion_warning(self):
        """Shown before deleting a 3.1 plot whose 4.1 evaluation would be lost with it."""
        if not self.has_technical_evaluation:
            return ""
        return (
            f"Προσοχή: υπάρχει τεχνική αξιολόγηση (Ενότητα 4.1) για το τεμάχιο "
            f"{self.parcel_number}. Με τη διαγραφή του τεμαχίου θα διαγραφεί και η "
            f"τεχνική αξιολόγηση, καθώς και τα αρχεία του και η απόφαση καταλληλότητας (6.6)."
        )

    @property
    def row_label(self):
        """Identifies which parcel an evaluation row (4.1) or decision row (6.6) edits."""
        parts = [f"Τεμάχιο {self.parcel_number}"]
        if self.sheet_plan:
            parts.append(f"Φ/Σχ {self.sheet_plan}")
        if self.area_sqm is not None:
            parts.append(f"{self.area_sqm} τ.μ.")
        return " · ".join(parts)


class UtilityServiceType(AuditedModel):
    """4.2 Values of the «Υπηρεσία» dropdown, maintained by the administrator.

    Renaming a value renames it on every case row that uses it; values in use are
    deactivated rather than deleted.
    """

    name = models.CharField(max_length=128, unique=True, help_text="4.2 Ονομασία υπηρεσίας")
    display_order = models.PositiveIntegerField(default=0, help_text="4.2 Σειρά εμφάνισης")
    is_active = models.BooleanField(default=True, help_text="4.2 Ενεργή (διαθέσιμη για επιλογή)")

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name

    @property
    def is_in_use(self):
        return self.case_services.exists()


class UtilityService(AuditedModel):
    """4.2 One row per utility service; the same service may appear more than once."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="utility_services")
    service_type = models.ForeignKey(
        UtilityServiceType,
        on_delete=models.PROTECT,
        related_name="case_services",
        help_text="4.2 Υπηρεσία",
    )
    proximity = models.CharField(max_length=255, blank=True, help_text="4.2 Εγγύτητα με το/τα τεμάχιο/α")
    comments = models.TextField(blank=True, help_text="4.2 Σχόλια")

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.case.case_number} - {self.service_type}"

    @property
    def row_label(self):
        if self.proximity:
            return f"{self.service_type} ({self.proximity})"
        return str(self.service_type)


class Consultation(AuditedModel):
    class Stage(models.TextChoices):
        SUITABILITY = "suitability", "Καταλληλότητα"
        DIVISION = "division", "Διαχωρισμός"

    class Department(models.TextChoices):
        TKX = "tkx", "Τ.Κ.Χ"
        TAY = "tay", "Τ.Α.Υ"
        AHK = "ahk", "Α.Η.Κ"
        OTHER = "other", "Άλλο"

    class Status(models.TextChoices):
        PENDING = "pending", "Εκκρεμεί"
        RECEIVED = "received", "Λήφθηκε"
        CLOSED = "closed", "Κλείστηκε"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="consultations")
    stage = models.CharField(max_length=16, choices=Stage.choices, help_text="5 / 8.4 Στάδιο")
    department = models.CharField(
        max_length=16,
        choices=Department.choices,
        help_text="5 / 8.4 Τμήμα / Υπηρεσία",
    )
    department_other = models.CharField(
        max_length=255,
        blank=True,
        help_text="5 / 8.4 Περιγραφή όταν Τμήμα / Υπηρεσία = Άλλο",
    )
    topic = models.TextField(blank=True, help_text="5 / 8.4 Θέμα διαβούλευσης")
    sent_date = models.DateField(null=True, blank=True, help_text="5 / 8.4 Ημ. αποστολής")
    due_date = models.DateField(null=True, blank=True, help_text="5 / 8.4 Προθεσμία απάντησης")
    response_date = models.DateField(null=True, blank=True, help_text="5 / 8.4 Ημ. λήψης απάντησης")
    response_text = models.TextField(blank=True, help_text="5 / 8.4 Άποψη / Απάντηση")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="5 / 8.4 Κατάσταση (αυτόματη από την ημ. απάντησης)",
    )
    comments = models.TextField(blank=True, help_text="5 / 8.4 Σχόλια")
    attachments = GenericRelation(Attachment)

    class Meta:
        ordering = ("id",)

    @property
    def department_display(self):
        if self.department == self.Department.OTHER:
            return (self.department_other or "").strip() or self.get_department_display()
        return self.get_department_display()

    @property
    def row_label(self):
        topic = (self.topic or "").strip()
        if topic:
            return f"{self.department_display} — {topic[:60]}"
        return self.department_display

    def save(self, *args, **kwargs):
        if self.status != self.Status.CLOSED:
            self.status = self.Status.RECEIVED if self.response_date else self.Status.PENDING
        return super().save(*args, **kwargs)


class InfrastructureCheck(AuditedModel):
    """8.6 Each on-site check is a separate dated event."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="infrastructure_checks")
    check_date = models.DateField(help_text="8.6 Ημερομηνία ελέγχου")
    curbs_ready = models.BooleanField(default=False, help_text="8.6 Ρείθρα")
    curbs_comments = models.CharField(max_length=255, blank=True, help_text="8.6 Σχόλια ρείθρων")
    pavements_ready = models.BooleanField(default=False, help_text="8.6 Κράσπεδα")
    pavements_comments = models.CharField(max_length=255, blank=True, help_text="8.6 Σχόλια κρασπέδων")
    asphalt_ready = models.BooleanField(default=False, help_text="8.6 Ασφαλτοστρωμένο οδόστρωμα")
    asphalt_comments = models.CharField(max_length=255, blank=True, help_text="8.6 Σχόλια οδοστρώματος")
    pavement_fill_ready = models.BooleanField(default=False, help_text="8.6 Επιχωμάτωση πεζοδρομίων")
    pavement_fill_comments = models.CharField(
        max_length=255, blank=True, help_text="8.6 Σχόλια επιχωμάτωσης"
    )
    water_ready = models.BooleanField(default=False, help_text="8.6 Υδατοπρομήθεια")
    water_comments = models.CharField(max_length=255, blank=True, help_text="8.6 Σχόλια υδατοπρομήθειας")
    telecom_ready = models.BooleanField(default=False, help_text="8.6 Τηλεπικοινωνίες")
    telecom_comments = models.CharField(
        max_length=255, blank=True, help_text="8.6 Σχόλια τηλεπικοινωνιών"
    )
    electricity_ready = models.BooleanField(default=False, help_text="8.6 Παροχή ηλεκτρικού ρεύματος")
    electricity_comments = models.CharField(max_length=255, blank=True, help_text="8.6 Σχόλια ηλεκτρισμού")
    street_light_ready = models.BooleanField(default=False, help_text="8.6 Οδικός φωτισμός")
    street_light_comments = models.CharField(max_length=255, blank=True, help_text="8.6 Σχόλια φωτισμού")
    is_ready_for_submission_cycle = models.BooleanField(
        default=False,
        help_text="8.6 Συνολικό ΝΑΙ/ΟΧΙ ετοιμότητας για άνοιγμα κύκλου υποβολής (αυτόματο)",
    )
    comments = models.TextField(blank=True, help_text="8.6 Σχόλια ελέγχου")

    class Meta:
        ordering = ("-check_date", "-id")

    def save(self, *args, **kwargs):
        # Μέρος Β §2: readiness requires at least gutters/kerbs and asphalt road surface.
        self.is_ready_for_submission_cycle = bool(
            self.curbs_ready and self.pavements_ready and self.asphalt_ready
        )
        return super().save(*args, **kwargs)


class Field(AuditedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="fields")
    code = models.CharField(max_length=64, help_text="8.7 Κωδικός χωραφιού")
    description = models.CharField(max_length=255, blank=True, help_text="8.7 Περιγραφή χωραφιού")

    class Meta:
        ordering = ("code",)
        unique_together = ("case", "code")

    def __str__(self):
        return self.code


class Parcel(AuditedModel):
    DISPOSAL_PRICE_RATE = Decimal("0.25")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="parcels")
    field = models.ForeignKey(
        Field,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcels",
        help_text="8.7 Χωράφι προέλευσης (προαιρετικό)",
    )
    valuation_referral = models.ForeignKey(
        "cases.ValuationReferral",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcels",
        help_text="8.8 Παραπομπή προς Διευθυντή ΤΚΧ που καθόρισε την αξία",
    )
    owner_person_id = models.IntegerField(null=True, blank=True, help_text="8.7 Ιδιοκτήτης (Person)")
    lot_number_in_field = models.CharField(
        max_length=64, blank=True, help_text="8.7 Νούμερο εντός χωραφιού (προαιρετικό)"
    )
    design_lot_number = models.CharField(
        max_length=64, blank=True, help_text="8.7 Αρ. οικοπέδου στον εγκεκριμένο σχεδιασμό"
    )
    tkx_lot_number = models.CharField(max_length=64, blank=True, help_text="8.7 Αρ. οικοπέδου ΤΚΧ")
    kotsiani_number = models.CharField(
        max_length=64, blank=True, help_text="8.7 Αριθμός κοτσιάνι (προαιρετικός)"
    )
    has_separate_title = models.CharField(
        max_length=8,
        choices=YesNo.choices,
        blank=True,
        help_text="8.8.1 Υπάρχει ξεχωριστός Τίτλος Ιδιοκτησίας;",
    )
    sheet_plan = models.CharField(
        max_length=64, blank=True, help_text="8.8 Φύλλο/Σχέδιο (αδιάθετα οικόπεδα)"
    )
    final_area_sqm = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="8.7 Τελικό εμβαδόν (τ.μ.)"
    )
    valuation_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, help_text="8.8 Αξία για υπολογισμό"
    )
    disposal_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="8.8 Τιμή διάθεσης (αυτόματα 25% της αξίας)",
    )
    comments = models.TextField(blank=True, help_text="8.7 Σχόλια οικοπέδου")

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return self.design_lot_number or self.tkx_lot_number or f"Οικόπεδο #{self.pk}"

    @property
    def row_label(self):
        parts = [f"Οικόπεδο {self}"]
        if self.field_id:
            parts.append(f"χωράφι {self.field.code}")
        if self.final_area_sqm is not None:
            parts.append(f"{self.final_area_sqm} τ.μ.")
        return " · ".join(parts)

    @property
    def is_valued(self):
        """8.8.2 A plot counts as valued once it has both a value and a computed price."""
        return self.valuation_amount is not None and self.disposal_price is not None

    def save(self, *args, **kwargs):
        if self.valuation_amount is None:
            self.disposal_price = None
        else:
            self.disposal_price = (self.valuation_amount * self.DISPOSAL_PRICE_RATE).quantize(
                Decimal("0.01")
            )
        return super().save(*args, **kwargs)


class ValuationReferral(AuditedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="valuation_referrals")
    letter_date = models.DateField(
        null=True, blank=True, help_text="8.8 Ημερομηνία επιστολής / αίτησης προς ΤΚΧ"
    )
    reference_number = models.CharField(
        max_length=128, blank=True, help_text="8.8 Αριθμός φακέλου / αναφοράς"
    )
    response_date = models.DateField(null=True, blank=True, help_text="8.8 Ημερομηνία απάντησης ΤΚΧ")
    comments = models.TextField(blank=True, help_text="8.8 Σχόλια")

    class Meta:
        ordering = ("-letter_date", "-id")

    def __str__(self):
        return self.reference_number or f"ΤΚΧ #{self.pk}"


class SubmissionCycle(AuditedModel):
    """Ενότητα 9 Γνωστοποίηση / ανακοίνωση έναρξης αιτήσεων, ανά Κοινότητα.

    One announcement may cover several cases of the same community, so the available
    plots can mix an old split with a new one (§Α.3.2).
    """

    community = models.ForeignKey(Community, on_delete=models.PROTECT, related_name="submission_cycles")
    cases = models.ManyToManyField(
        Case,
        related_name="submission_cycles",
        help_text="9.1 Υποθέσεις της ίδιας Κοινότητας που καλύπτει η γνωστοποίηση",
    )
    announcement_date = models.DateField(help_text="9.1 Ημερομηνία γνωστοποίησης")
    submission_start_date = models.DateField(help_text="9.1 Έναρξη υποβολής αιτήσεων")
    submission_end_date = models.DateField(help_text="9.1 Λήξη υποβολής αιτήσεων")
    comments = models.TextField(blank=True, help_text="9.5 Σχόλια / Παρατηρήσεις Ενότητας 9")
    announcement_text = models.TextField(
        blank=True, help_text="9.3 Κείμενο ανακοίνωσης (αυτόματο προσχέδιο, επεξεργάσιμο)"
    )
    published_at = models.DateTimeField(
        null=True, blank=True, help_text="9.3 Οριστικοποίηση / έκδοση ανακοίνωσης"
    )

    class Meta:
        ordering = ("-announcement_date", "-id")

    def __str__(self):
        return f"{self.community.name} — γνωστοποίηση {self.announcement_date}"

    @property
    def is_published(self):
        return self.published_at is not None

    @property
    def available_parcels(self):
        """9.1 Plots of the linked cases that cleared 8.8 (value and price recorded)."""
        return Parcel.objects.filter(
            case__in=self.cases.all(),
            valuation_amount__isnull=False,
            disposal_price__isnull=False,
        )

    @property
    def available_plots_count(self):
        return self.available_parcels.count()


class SubmissionCyclePublication(AuditedModel):
    class PublicationMethod(models.TextChoices):
        COMMUNITY = "community", "Αποστολή/ανάρτηση στην Κοινότητα ή στο Δ.Δ."
        DISTRICT_OFFICE = "district_office", "Έντυπη ανάρτηση στα γραφεία Επαρχιακής Διοίκησης"
        DISTRICT_SITE = "district_site", "Ιστοσελίδα Επαρχιακής Διοίκησης"
        MINISTRY_SITE = "ministry_site", "Ιστοσελίδα ΥΠΕΣ"
        OTHER = "other", "Άλλο"

    submission_cycle = models.ForeignKey(
        SubmissionCycle, on_delete=models.CASCADE, related_name="publications"
    )
    method = models.CharField(
        max_length=32, choices=PublicationMethod.choices, help_text="9.2 Τρόπος δημοσίευσης"
    )
    published_on = models.DateField(help_text="9.2 Ημερομηνία δημοσίευσης")
    notes = models.CharField(
        max_length=255, blank=True, help_text="9.2 Διευκρίνιση «Άλλο» / σημειώσεις"
    )

    class Meta:
        ordering = ("published_on", "id")
