import calendar
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.db.models.signals import m2m_changed
from django.utils import timezone

from cases import section_refs as refs
from core.models import Attachment, AuditedModel, Communication, Community


class YesNo(models.TextChoices):
    YES = "yes", "ΝΑΙ"
    NO = "no", "ΟΧΙ"


# Every case is a division request (Ενότ. 2§2) and runs every section; Αδιάθετα Οικόπεδα are
# registered straight into «Οικόπεδα». Announcements (Ενότητα 9) are a separate flow over the
# completed plots, not a case section.
CASE_SECTION_KEYS = (
    refs.SECTION_1,
    refs.SECTION_2,
    refs.SECTION_3,
    refs.SECTION_4,
    refs.SECTION_5,
    refs.SECTION_6,
    refs.SECTION_7,
)

class CommunicationStatus:
    """Values of `core.Communication.status` used by the 2.2 deficiency emails."""

    DRAFT = "draft"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"

    LABELS = {
        DRAFT: "Προσχέδιο",
        SENDING: "Σε αποστολή",
        SENT: "Απεστάλη",
        FAILED: "Αποτυχία αποστολής",
    }

    @classmethod
    def label(cls, status):
        return cls.LABELS.get(status, cls.LABELS[cls.DRAFT])


# 2.1 The "current" completeness check of a case is the latest by date.
COMPLETENESS_LATEST_ORDER = ("-check_date", "-sequence", "-id")


def _count_subquery(model_name, related_field="case"):
    """Correlated COUNT(*) of child rows, so several counts do not multiply via joins."""
    model = apps.get_model("cases", model_name)
    return Coalesce(
        Subquery(
            model.objects.filter(**{related_field: OuterRef("pk")})
            .order_by()
            .values(related_field)
            .annotate(total=Count("pk"))
            .values("total")[:1],
            output_field=models.IntegerField(),
        ),
        0,
    )


class CaseQuerySet(AuditedModel.AuditedQuerySet):
    def with_list_data(self):
        """Per-row data of the case list in the same query (no query per row)."""
        completeness = apps.get_model("cases", "CompletenessCheck").objects.filter(
            case=OuterRef("pk")
        ).order_by(*COMPLETENESS_LATEST_ORDER)
        rounds = apps.get_model("cases", "MinistryDecisionRound").objects.filter(
            case=OuterRef("pk")
        ).order_by("-id")
        return self.select_related("community").annotate(
            list_completeness_result=Subquery(completeness.values("result")[:1]),
            list_ministry_decision=Subquery(rounds.values("ministry_decision")[:1]),
            list_ministry_decision_other=Subquery(rounds.values("ministry_decision_other")[:1]),
            land_plots_count=_count_subquery("LandPlot"),
            approved_design_plots_count=_count_subquery("ApprovedDesignPlot"),
        )


class CaseManager(AuditedModel.AuditedManager):
    """Keeps the audited manager's blocked bulk updates and adds the list helpers."""

    def get_queryset(self):
        return CaseQuerySet(self.model, using=self._db)

    def with_list_data(self):
        return self.get_queryset().with_list_data()


class Case(AuditedModel):
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
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Ολοκλήρωση αίτησης: δημιουργία των οικοπέδων στον πίνακα «Οικόπεδα»",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
        help_text="Χρήστης που ολοκλήρωσε την αίτηση",
    )
    # Case-level files are told apart by section_ref: 4.4 technical evaluation as a whole,
    # 7.2 division design, 7.3 ΤΠΟ application, 7.7 DLS application.
    attachments = GenericRelation(Attachment)
    ATTACHMENT_SECTION_DIVISION_DESIGN = refs.REF_DIVISION_DESIGN
    ATTACHMENT_SECTION_TPO_APPLICATION = refs.REF_TPO_APPLICATION
    ATTACHMENT_SECTION_DLS_APPLICATION = refs.REF_DLS_APPLICATION

    survey_assignment_date = models.DateField(
        null=True, blank=True, help_text="7.1 Ημερομηνία ανάθεσης μελέτης"
    )
    surveyor_name = models.CharField(
        max_length=255, blank=True, help_text="7.1 Ονοματεπώνυμο ιδιώτη αρμόδιου χωρομέτρη"
    )
    surveyor_phone = models.CharField(max_length=64, blank=True, help_text="7.1 Τηλέφωνο")
    surveyor_email = models.EmailField(blank=True, help_text="7.1 Email")
    survey_assignment_comments = models.TextField(blank=True, help_text="7.1 Σχόλια")

    division_design_status = models.CharField(
        max_length=16, choices=DesignStatus.choices, blank=True, help_text="7.2 Κατάσταση σχεδιασμού"
    )
    division_design_completed_on = models.DateField(
        null=True, blank=True, help_text="7.2 Ημερομηνία ολοκλήρωσης σχεδιασμού"
    )
    division_design_plots_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="7.2 Αριθμός οικοπέδων"
    )
    division_design_comments = models.TextField(blank=True, help_text="7.2 Σχόλια")

    tpo_application_date = models.DateField(
        null=True, blank=True, help_text="7.3 Ημερομηνία υποβολής αίτησης στο ΤΠΟ"
    )
    tpo_application_number = models.CharField(
        max_length=64, blank=True, help_text="7.3 Αριθμός αίτησης ΤΠΟ"
    )
    tpo_response = models.CharField(
        max_length=16, choices=TpoResponse.choices, blank=True, help_text="7.3 Απάντηση Διευθυντή ΤΠΟ"
    )
    tpo_response_date = models.DateField(
        null=True, blank=True, help_text="7.3 Ημερομηνία απάντησης ΤΠΟ"
    )
    tpo_comments = models.TextField(blank=True, help_text="7.3 Σχόλια")

    construction_plans_stage = models.TextField(
        blank=True, help_text="7.4 Στάδιο κατασκευαστικών σχεδίων"
    )
    land_expropriation_required = models.CharField(
        max_length=8, choices=YesNo.choices, blank=True, help_text="7.4 Απαιτείται απαλλοτρίωση γης"
    )

    tender_announcement_date = models.DateField(
        null=True, blank=True, help_text="7.5 Ημερομηνία προκήρυξης διαγωνισμού"
    )
    tender_award_date = models.DateField(
        null=True, blank=True, help_text="7.5 Ημερομηνία κατακύρωσης"
    )
    contractor_name = models.CharField(
        max_length=255, blank=True, help_text="7.5 Ανάδοχος / πρόσωπο ανάθεσης"
    )
    contractor_phone = models.CharField(max_length=64, blank=True, help_text="7.5 Τηλέφωνο αναδόχου")
    contractor_email = models.EmailField(blank=True, help_text="7.5 Email αναδόχου")
    contract_duration_value = models.PositiveIntegerField(
        null=True, blank=True, help_text="7.5 Διάρκεια σύμβασης (μήνες)"
    )
    contract_duration_unit = models.CharField(
        max_length=16,
        choices=ContractDurationUnit.choices,
        blank=True,
        help_text="7.5 Διάρκεια σύμβασης (μονάδα - πάντα μήνες)",
    )
    tender_comments = models.TextField(blank=True, help_text="7.5 Σχόλια")

    dls_application_date = models.DateField(
        null=True, blank=True, help_text="7.7 Ημερομηνία υποβολής αίτησης στο ΤΚΧ"
    )
    dls_file_number = models.CharField(max_length=64, blank=True, help_text="7.7 Αριθμός φακέλου ΤΚΧ")
    dls_response_date = models.DateField(
        null=True, blank=True, help_text="7.7 Ημερομηνία απάντησης / ολοκλήρωσης ΤΚΧ"
    )
    dls_comments = models.TextField(blank=True, help_text="7.7 Σχόλια")

    objects = CaseManager()

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

    def division_design_attachments(self):
        return self.attachments.filter(section_ref=self.ATTACHMENT_SECTION_DIVISION_DESIGN)

    def tpo_application_attachments(self):
        return self.attachments.filter(section_ref=self.ATTACHMENT_SECTION_TPO_APPLICATION)

    def dls_application_attachments(self):
        return self.attachments.filter(section_ref=self.ATTACHMENT_SECTION_DLS_APPLICATION)

    @property
    def latest_infrastructure_check(self):
        return self.infrastructure_checks.first()

    @property
    def is_completed(self):
        return self.completed_at is not None

    @property
    def latest_completeness_check(self):
        """2.1 Current completeness result for this case (latest by date)."""
        return self.completeness_checks.order_by(*COMPLETENESS_LATEST_ORDER).first()

    @property
    def completeness_result(self):
        # Case lists annotate the value (CaseQuerySet.with_list_data) to avoid a query per row.
        if hasattr(self, "list_completeness_result"):
            return self.list_completeness_result or ""
        check = self.latest_completeness_check
        return check.result if check else ""

    @property
    def latest_ministry_decision_display(self):
        """Latest ΥΠΕΣ decision for case lists (source: 6.7 rows)."""
        if hasattr(self, "list_ministry_decision"):
            decision = self.list_ministry_decision
            other = self.list_ministry_decision_other
        else:
            latest = self.ministry_decision_rounds.order_by("-id").first()
            decision = latest.ministry_decision if latest else ""
            other = latest.ministry_decision_other if latest else ""
        if not decision:
            return ""
        return MinistryDecisionRound(
            ministry_decision=decision, ministry_decision_other=other or ""
        ).ministry_decision_display

    @property
    def completeness_result_display(self):
        result = self.completeness_result
        return dict(YesNo.choices).get(result, "") if result else ""

    @property
    def applicable_sections(self):
        return CASE_SECTION_KEYS


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
        """Checks with sent (or in-flight) emails stay immutable for traceability."""
        # Checked in Python so a prefetched `communications` serves the whole grid.
        return all(c.status == CommunicationStatus.FAILED for c in self.communications.all())

    @property
    def sent_emails_count(self):
        return sum(1 for c in self.communications.all() if c.status == CommunicationStatus.SENT)

    @property
    def emails(self):
        """2.2 Emails of this check, oldest first, nested under its grid row."""
        return sorted(self.communications.all(), key=lambda c: (c.created_at, c.pk))

    SEQUENCE_ATTEMPTS = 5

    def _next_sequence(self):
        last = (
            CompletenessCheck.objects.filter(case_id=self.case_id)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
        )
        return (last or 0) + 1

    def save(self, *args, **kwargs):
        if self.sequence:
            return super().save(*args, **kwargs)
        # 2.1 numbering is max+1 per case. Lock the case row (where the database supports
        # it) and retry in a savepoint if a concurrent save took the same number.
        for attempt in range(self.SEQUENCE_ATTEMPTS):
            try:
                with transaction.atomic():
                    Case.objects.select_for_update().filter(pk=self.case_id).exists()
                    self.sequence = self._next_sequence()
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.sequence = None
                if attempt == self.SEQUENCE_ATTEMPTS - 1:
                    raise


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
    rejected = models.CharField(
        max_length=8, choices=YesNo.choices, default=YesNo.NO, help_text="3.1 Απορρίφθηκε"
    )
    attachments = GenericRelation(Attachment)
    communications = GenericRelation(Communication)
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
    def short_label(self):
        """How a 7.3 plot names this parcel as its origin."""
        if self.sheet_plan:
            return f"{self.parcel_number} (Φ/Σχ {self.sheet_plan})"
        return self.parcel_number

    @property
    def is_rejected(self):
        return self.rejected == YesNo.YES

    @property
    def sent_emails_count(self):
        # Counted in Python so a prefetched `communications` serves the whole grid.
        return sum(1 for c in self.communications.all() if c.status == CommunicationStatus.SENT)

    @property
    def emails(self):
        """3.1 Emails about this plot, oldest first, nested under its grid row."""
        return sorted(self.communications.all(), key=lambda c: (c.created_at, c.pk))

    def linked_design_plots(self):
        """7.3 plots that name this parcel as their origin; while any exist it is not deleted."""
        return list(self.approved_design_plots.all())

    @property
    def deletion_refusal(self):
        plots = self.linked_design_plots()
        if plots:
            labels = ", ".join(plot.row_label for plot in plots)
            return (
                f"Το τεμάχιο {self.parcel_number} δεν διαγράφεται γιατί έχει οριστεί ως τεμάχιο "
                f"προέλευσης στα οικόπεδα (7.3): {labels}. Αφαιρέστε πρώτα τη σύνδεση από τα οικόπεδα."
            )
        # Sent (or in-flight) emails stay with their plot for traceability, as in 2.1.
        if any(c.status != CommunicationStatus.FAILED for c in self.communications.all()):
            return (
                f"Το τεμάχιο {self.parcel_number} δεν διαγράφεται γιατί έχουν σταλεί email "
                f"για αυτό. Μπορείτε να το σημειώσετε ως «Απορρίφθηκε»."
            )
        return ""

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
        DIVISION = "division", "Κατασκευαστικά σχέδια"

    class Department(models.TextChoices):
        TKX = "tkx", "Τ.Κ.Χ"
        TAY = "tay", "Τ.Α.Υ"
        AHK = "ahk", "Α.Η.Κ"
        OTHER = "other", "Άλλο"

    class Status(models.TextChoices):
        PENDING = "pending", "Εκκρεμεί"
        RECEIVED = "received", "Λήφθηκε"
        CLOSED = "closed", "Κλείστηκε"

    # Section 5 and subsection 7.4 keep separate rows (and files) on the same entity.
    SECTION_REF_BY_STAGE = {
        Stage.SUITABILITY: refs.REF_SUITABILITY_CONSULTATIONS,
        Stage.DIVISION: refs.REF_DIVISION_CONSULTATIONS,
    }

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="consultations")
    stage = models.CharField(max_length=16, choices=Stage.choices, help_text="5 / 7.4 Στάδιο")
    department = models.CharField(
        max_length=16,
        choices=Department.choices,
        help_text="5 / 7.4 Τμήμα / Υπηρεσία",
    )
    department_other = models.CharField(
        max_length=255,
        blank=True,
        help_text="5 / 7.4 Περιγραφή όταν Τμήμα / Υπηρεσία = Άλλο",
    )
    topic = models.TextField(blank=True, help_text="5 / 7.4 Θέμα διαβούλευσης")
    sent_date = models.DateField(null=True, blank=True, help_text="5 / 7.4 Ημ. αποστολής")
    due_date = models.DateField(null=True, blank=True, help_text="5 / 7.4 Προθεσμία απάντησης")
    response_date = models.DateField(null=True, blank=True, help_text="5 / 7.4 Ημ. λήψης απάντησης")
    response_text = models.TextField(blank=True, help_text="5 / 7.4 Άποψη / Απάντηση")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="5 / 7.4 Κατάσταση (αυτόματη από την ημ. απάντησης)",
    )
    comments = models.TextField(blank=True, help_text="5 / 7.4 Σχόλια")
    attachments = GenericRelation(Attachment)

    class Meta:
        ordering = ("id",)

    @property
    def section_ref(self):
        return self.SECTION_REF_BY_STAGE[self.stage]

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
    """7.6 Παρακολούθηση κατασκευαστικών εργασιών: each on-site check is a separate dated row."""

    WORK_FIELDS = (
        "curbs_ready",
        "pavements_ready",
        "asphalt_ready",
        "pavement_fill_ready",
        "water_ready",
        "telecom_ready",
        "electricity_ready",
        "street_light_ready",
    )

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="infrastructure_checks")
    stage = models.CharField(max_length=255, blank=True, help_text="7.6 Στάδιο")
    check_date = models.DateField(help_text="7.6 Ημερομηνία ελέγχου")
    curbs_ready = models.BooleanField(default=False, help_text="7.6 Ρείθρα")
    pavements_ready = models.BooleanField(default=False, help_text="7.6 Κράσπεδα")
    asphalt_ready = models.BooleanField(
        default=False, help_text="7.6 Οδόστρωμα με ασφαλτικό σκυρόδεμα"
    )
    pavement_fill_ready = models.BooleanField(default=False, help_text="7.6 Επιχωμάτωση πεζοδρομίων")
    water_ready = models.BooleanField(default=False, help_text="7.6 Υδατοπρομήθεια")
    telecom_ready = models.BooleanField(default=False, help_text="7.6 Τηλεπικοινωνίες")
    electricity_ready = models.BooleanField(default=False, help_text="7.6 Παροχή ηλεκτρικού ρεύματος")
    street_light_ready = models.BooleanField(default=False, help_text="7.6 Οδικός φωτισμός")
    is_ready_for_submission_cycle = models.BooleanField(
        default=False,
        help_text="7.6 Συνολικό ΝΑΙ/ΟΧΙ ετοιμότητας για άνοιγμα κύκλου υποβολής (αυτόματο)",
    )
    comments = models.TextField(blank=True, help_text="7.6 Σχόλια")

    class Meta:
        ordering = ("-check_date", "-id")

    @property
    def row_label(self):
        parts = (str(self.check_date or ""), self.stage)
        return " · ".join(part for part in parts if part) or "Νέος έλεγχος"

    def _audit_context(self):
        return self.case_id, None, getattr(self, "_section_ref", refs.REF_INFRASTRUCTURE_CHECKS)

    def save(self, *args, **kwargs):
        # Μέρος Β §2: readiness requires at least gutters/kerbs and asphalt road surface.
        self.is_ready_for_submission_cycle = bool(
            self.curbs_ready and self.pavements_ready and self.asphalt_ready
        )
        return super().save(*args, **kwargs)


class MinistryDecisionRound(AuditedModel):
    """6.7 One row per recommendation / ministry decision cycle."""

    ATTACHMENT_SECTION_RECOMMENDATION = refs.REF_MINISTRY_RECOMMENDATION_FILES
    ATTACHMENT_SECTION_RESPONSE = refs.REF_MINISTRY_RESPONSE_FILES

    class Recommendation(models.TextChoices):
        POSITIVE = "positive", "Θετική"
        NEGATIVE = "negative", "Αρνητική"
        OTHER = "other", "Άλλο"

    class MinistryDecision(models.TextChoices):
        APPROVED = "approved", "Έγκριση"
        REJECTED = "rejected", "Απόρριψη"
        OTHER = "other", "Άλλο"

    case = models.ForeignKey(
        Case, on_delete=models.CASCADE, related_name="ministry_decision_rounds"
    )
    letter_sent_date = models.DateField(
        null=True, blank=True, help_text="6.7 Ημερομηνία αποστολής"
    )
    recommendation = models.CharField(
        max_length=16,
        choices=Recommendation.choices,
        blank=True,
        help_text="6.7 Σύσταση Επαρχιακής Διοίκησης",
    )
    recommendation_other = models.CharField(
        max_length=255,
        blank=True,
        help_text="6.7 Σύσταση Επαρχιακής Διοίκησης — Άλλο",
    )
    ministry_response_date = models.DateField(
        null=True, blank=True, help_text="6.7 Ημερομηνία λήψης απάντησης"
    )
    ministry_decision = models.CharField(
        max_length=16,
        choices=MinistryDecision.choices,
        blank=True,
        help_text="6.7 Απόφαση ΥΠΕΣ",
    )
    ministry_decision_other = models.CharField(
        max_length=255,
        blank=True,
        help_text="6.7 Απόφαση ΥΠΕΣ — Άλλο",
    )
    comments = models.TextField(blank=True, help_text="6.7 Σχόλια / Παρατηρήσεις")
    attachments = GenericRelation(Attachment)

    class Meta:
        ordering = ("id",)

    def recommendation_attachments(self):
        return self.attachments.filter(section_ref=self.ATTACHMENT_SECTION_RECOMMENDATION)

    def response_attachments(self):
        return self.attachments.filter(section_ref=self.ATTACHMENT_SECTION_RESPONSE)

    @property
    def recommendation_display(self):
        if self.recommendation == self.Recommendation.OTHER and self.recommendation_other:
            return f"{self.get_recommendation_display()}: {self.recommendation_other}"
        return self.get_recommendation_display() or ""

    @property
    def ministry_decision_display(self):
        if self.ministry_decision == self.MinistryDecision.OTHER and self.ministry_decision_other:
            return f"{self.get_ministry_decision_display()}: {self.ministry_decision_other}"
        return self.get_ministry_decision_display() or ""

    @property
    def row_label(self):
        parts = []
        if self.letter_sent_date:
            parts.append(str(self.letter_sent_date))
        if self.recommendation:
            parts.append(self.recommendation_display)
        if self.ministry_decision:
            parts.append(self.ministry_decision_display)
        return " · ".join(parts) if parts else "Νέα γραμμή"

    def _audit_context(self):
        return self.case_id, None, getattr(self, "_section_ref", refs.REF_MINISTRY_DECISIONS)


class DisposalPriceMixin:
    """8.2 «Τιμή διάθεσης»: editable, defaulting to 25% of «Αξία για υπολογισμό».

    The price follows the value while it is the automatic one: it is recalculated when it
    is empty, or when the value changes and the price was left at 25% of the old value.
    A price of its own (entered by the user) is kept when the value changes.
    """

    DISPOSAL_PRICE_RATE = Decimal("0.25")

    @classmethod
    def disposal_price_for(cls, valuation_amount):
        if valuation_amount is None:
            return None
        return (Decimal(valuation_amount) * cls.DISPOSAL_PRICE_RATE).quantize(Decimal("0.01"))

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance.remember_disposal_price_inputs()
        return instance

    def remember_disposal_price_inputs(self):
        self._loaded_valuation_amount = self.__dict__.get("valuation_amount")
        self._loaded_disposal_price = self.__dict__.get("disposal_price")

    def apply_default_disposal_price(self):
        loaded_valuation = getattr(self, "_loaded_valuation_amount", None)
        loaded_price = getattr(self, "_loaded_disposal_price", None)
        follows_value = (
            self.valuation_amount != loaded_valuation
            and self.disposal_price == loaded_price
            and loaded_price == self.disposal_price_for(loaded_valuation)
        )
        if self.disposal_price is None or follows_value:
            self.disposal_price = self.disposal_price_for(self.valuation_amount)


class ApprovedDesignPlot(DisposalPriceMixin, AuditedModel):
    """7.3 Στοιχεία Εγκεκριμένου Σχεδιασμού Οικοπέδων: one row per plot or space of the design."""

    class PlotType(models.TextChoices):
        DIVISION_PLOT = "division_plot", "Υπό διαχωρισμό οικόπεδο"
        GREEN_SPACE = "green_space", "Χώρος πρασίνου"
        EAC_SUBSTATION = "eac_substation", "Υποσταθμός ΑΗΚ"
        COMMUNITY_FACILITY = "community_facility", "Χώρος κοινοτικού εξοπλισμού"
        OTHER = "other", "Άλλο"

    class NumberingStatus(models.TextChoices):
        DESIGN = "design", "Αρίθμηση σχεδιασμού"
        TKX = "tkx", "Αρίθμηση ΤΚΧ"
        TITLE_DEED = "title_deed", "Αρίθμηση βάσει τίτλου ιδιοκτησίας"

    case = models.ForeignKey(
        Case, on_delete=models.CASCADE, related_name="approved_design_plots"
    )
    field = models.ForeignKey(
        "cases.Field",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_design_plots",
        help_text="8.2 Χωράφι προέλευσης (προαιρετικό)",
    )
    # A linked 3.1 parcel cannot be deleted (LandPlotGrid.refuse_delete).
    source_land_plots = models.ManyToManyField(
        LandPlot,
        blank=True,
        related_name="approved_design_plots",
        help_text="7.3 Τεμάχια προέλευσης (3.1, προαιρετικά)",
    )
    valuation_referral = models.ForeignKey(
        "cases.ValuationReferral",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_design_plots",
        help_text="8.2 Παραπομπή προς Διευθυντή ΤΚΧ που καθόρισε την αξία",
    )
    plot_type = models.CharField(max_length=32, choices=PlotType.choices, help_text="7.3 Τύπος")
    plot_type_other = models.CharField(
        max_length=255, blank=True, help_text="7.3 Τύπος — Άλλο"
    )
    design_number = models.CharField(max_length=64, blank=True, help_text="7.3 Αρίθμηση")
    tkx_number = models.CharField(max_length=64, blank=True, help_text="8.1 Αρίθμηση ΤΚΧ")
    title_deed_number = models.CharField(
        max_length=64, blank=True, help_text="8.2 Αριθμός τίτλου ιδιοκτησίας"
    )
    parcel_number = models.CharField(max_length=64, blank=True, help_text="8.2 Αριθμός τεμαχίου")
    sheet_plan = models.CharField(max_length=64, blank=True, help_text="8.2 Φύλλο/Σχέδιο")
    final_area_sqm = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="8.2 Τελικό εμβαδόν (τ.μ.)"
    )
    # The column keeps its historical name; it used to be a plain integer id.
    owner = models.ForeignKey(
        "applications.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="owner_person_id",
        related_name="owned_design_plots",
        help_text="8.2 Ιδιοκτήτης οικοπέδου",
    )
    lot_number_in_field = models.CharField(
        max_length=64, blank=True, help_text="8.2 Νούμερο εντός χωραφιού (προαιρετικό)"
    )
    kotsiani_number = models.CharField(
        max_length=64, blank=True, help_text="8.2 Αριθμός κοτσιάνι (προαιρετικός)"
    )
    has_separate_title = models.CharField(
        max_length=8,
        choices=YesNo.choices,
        blank=True,
        help_text="8.2 Υπάρχει ξεχωριστός Τίτλος Ιδιοκτησίας;",
    )
    valuation_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, help_text="8.2 Αξία για υπολογισμό"
    )
    disposal_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="8.2 Τιμή διάθεσης (κενό: αυτόματα 25% της αξίας)",
    )
    comments = models.TextField(blank=True, help_text="8.2 Σχόλια οικοπέδου")
    numbering_status = models.CharField(
        max_length=16,
        choices=NumberingStatus.choices,
        default=NumberingStatus.DESIGN,
        help_text="8.1 / 8.2 Κατάσταση αρίθμησης",
    )

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return self.row_label

    @property
    def plot_type_display(self):
        if self.plot_type == self.PlotType.OTHER and self.plot_type_other:
            return f"{self.get_plot_type_display()}: {self.plot_type_other}"
        return self.get_plot_type_display() or ""

    @property
    def row_label(self):
        number = self.design_number or self.tkx_number or self.title_deed_number
        return " ".join(part for part in (self.plot_type_display, number) if part) or "Νέα γραμμή"

    @property
    def source_land_plots_display(self):
        return ", ".join(land_plot.short_label for land_plot in self.source_land_plots.all())

    @property
    def is_valued(self):
        return self.valuation_amount is not None and self.disposal_price is not None

    @property
    def generated_plot(self):
        """The completed plot (plots.Plot) this row produced when its case was completed."""
        if not self.pk:
            return None
        try:
            return self.plot
        except ObjectDoesNotExist:
            return None

    @property
    def is_allocated(self):
        """Whether an allocation (Ενότητα 10+) already points at the plot of this row."""
        plot = self.generated_plot
        return plot is not None and plot.is_allocated

    def save(self, *args, **kwargs):
        self.apply_default_disposal_price()
        if kwargs.get("update_fields") is not None and "valuation_amount" in kwargs["update_fields"]:
            kwargs["update_fields"] = {*kwargs["update_fields"], "disposal_price"}
        result = super().save(*args, **kwargs)
        self.remember_disposal_price_inputs()
        return result

    def _audit_context(self):
        return self.case_id, None, getattr(self, "_section_ref", refs.REF_APPROVED_DESIGN_PLOTS)


class Field(AuditedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="fields")
    code = models.CharField(max_length=64, help_text="8.2 Κωδικός χωραφιού")
    description = models.CharField(max_length=255, blank=True, help_text="8.2 Περιγραφή χωραφιού")

    class Meta:
        ordering = ("code",)
        unique_together = ("case", "code")

    def __str__(self):
        return self.code


class ValuationReferral(AuditedModel):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="valuation_referrals")
    letter_date = models.DateField(
        null=True, blank=True, help_text="8.2 Ημερομηνία επιστολής / αίτησης προς ΤΚΧ"
    )
    reference_number = models.CharField(
        max_length=128, blank=True, help_text="8.2 Αριθμός φακέλου / αναφοράς"
    )
    response_date = models.DateField(null=True, blank=True, help_text="8.2 Ημερομηνία απάντησης ΤΚΧ")
    comments = models.TextField(blank=True, help_text="8.2 Σχόλια")

    class Meta:
        ordering = ("-letter_date", "-id")

    def __str__(self):
        return self.reference_number or f"ΤΚΧ #{self.pk}"


def add_months(value, months):
    """`value` plus whole calendar months; a day the month lacks becomes its last day."""
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


class SubmissionCycle(AuditedModel):
    """Ενότητα 9 Γνωστοποίηση / ανακοίνωση έναρξης αιτήσεων, συνδεδεμένη με τα διαθέσιμα οικόπεδα μίας Κοινότητας.

    Η γνωστοποίηση είναι ο γονέας (parent) των αιτήσεων παραχώρησης οικοπέδου (Παράρτημα 3)
    και καθοδηγεί τη διαδικασία μέσα από τα 6 στάδια:
    1. Υποβολή αιτήσεων
    Κάθε γνωστοποίηση διέρχεται από επτά στάδια:
    1. Στοιχεία γνωστοποίησης (επιλογή οικοπέδων, ημερομηνία, τρόποι δημοσίευσης)
    2. Υποβολή αιτήσεων (έλεγχος πληρότητας αιτήσεων)
    3. Επιτροπή Εξέτασης Αιτήσεων (έως την αποστολή του Προκαταρκτικού Καταλόγου)
    4. Ενστάσεις
    5. Τελικός Κατάλογος Δικαιούχων
    6. Στάδιο κλήρωσης
    7. Υπογραφή συμφωνίας και πληρωμή
    """

    class Stage(models.TextChoices):
        DETAILS = "details", "1. Στοιχεία γνωστοποίησης"
        SUBMISSION = "submission", "2. Υποβολή αιτήσεων"
        APPLICATIONS_COMMITTEE = "applications_committee", "3. Επιτροπή Εξέτασης Αιτήσεων"
        OBJECTIONS_COMMITTEE = "objections_committee", "4. Ενστάσεις"
        FINAL_LIST = "final_list", "5. Τελικός Κατάλογος Δικαιούχων"
        LOTTERY = "lottery", "6. Στάδιο κλήρωσης"
        AGREEMENTS = "agreements", "7. Υπογραφή συμφωνίας και πληρωμή"
        CLOSED = "closed", "Ολοκλήρωση γνωστοποίησης"

    ACTIVE_STAGES = (
        Stage.DETAILS,
        Stage.SUBMISSION,
        Stage.APPLICATIONS_COMMITTEE,
        Stage.OBJECTIONS_COMMITTEE,
        Stage.FINAL_LIST,
        Stage.LOTTERY,
        Stage.AGREEMENTS,
    )

    plots = models.ManyToManyField(
        "plots.Plot",
        blank=True,
        related_name="submission_cycles",
        help_text="9.1 Διαθέσιμα οικόπεδα μίας Κοινότητας που προσφέρει η γνωστοποίηση",
    )
    announcement_date = models.DateField(help_text="9.1 Ημερομηνία γνωστοποίησης")
    submission_months = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="9.1 Προθεσμία υποβολής αιτήσεων σε μήνες από την ημερομηνία γνωστοποίησης· η τελευταία ημέρα υποβολής υπολογίζεται αυτόματα",
    )
    submission_end_date = models.DateField(
        editable=False,
        help_text="9.1 Τελευταία ημέρα υποβολής αιτήσεων (υπολογίζεται από την ημερομηνία γνωστοποίησης και τους μήνες)",
    )
    stage = models.CharField(
        max_length=32,
        choices=Stage.choices,
        default=Stage.DETAILS,
        help_text="Στάδιο διαδικασίας γνωστοποίησης (1–7)",
    )
    submission_closed_early = models.BooleanField(
        default=False,
        help_text="Η περίοδος υποβολής αιτήσεων έκλεισε πριν από τη λήξη της προθεσμίας (Ενότ. 4, 5) κατόπιν αποδοχής προειδοποίησης",
    )
    objections_closed_on = models.DateField(
        null=True,
        blank=True,
        help_text="Κλείσιμο περιόδου ενστάσεων (Ενότ. 7(α)): λήξη των 21 ημερών ή μετάβαση στο Στάδιο 5 με αποδοχή προειδοποίησης",
    )
    objections_closed_early = models.BooleanField(
        default=False,
        help_text="Η περίοδος ενστάσεων έκλεισε πριν από τη λήξη της προθεσμίας (Ενότ. 7(α), 7(ε)) κατόπιν αποδοχής προειδοποίησης",
    )
    applications_committee_date = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία συνεδρίας Επιτροπής Εξέτασης Αιτήσεων (Ενότ. 6)",
    )
    objections_committee_date = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία συνεδρίας Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
    )
    agreement_location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Τόπος προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 9, 12, 15)",
    )
    agreement_appointment_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Προεπιλεγμένη ημερομηνία/ώρα προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 9, 12, 15)",
    )
    agreement_deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Προεπιλεγμένη προθεσμία προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 8, 9)",
    )
    comments = models.TextField(blank=True, help_text="9.5 Σχόλια / Παρατηρήσεις Ενότητας 9")
    published_at = models.DateTimeField(
        null=True, blank=True, help_text="9.3 Οριστικοποίηση / έκδοση ανακοίνωσης"
    )

    class Meta:
        ordering = ("-announcement_date", "-id")

    def __str__(self):
        return f"{self.communities_label} — γνωστοποίηση {self.announcement_date}"

    def save(self, *args, **kwargs):
        self.submission_end_date = add_months(self.announcement_date, self.submission_months)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {"announcement_date", "submission_months"} & set(update_fields):
            kwargs["update_fields"] = {*update_fields, "submission_end_date"}
        if self.published_at is not None and self.stage == self.Stage.DETAILS:
            self.stage = self.Stage.SUBMISSION
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "stage"}
        super().save(*args, **kwargs)

    @property
    def is_published(self):
        return self.published_at is not None

    @property
    def is_active(self) -> bool:
        """Ενεργή γνωστοποίηση: δεν έχει ολοκληρώσει το τελευταίο της βήμα (Στάδιο 7 — Συμφωνίες & Πληρωμές)."""
        return self.stage != self.Stage.CLOSED

    def submission_open(self, today=None) -> bool:
        """Η προθεσμία υποβολής αιτήσεων είναι ανοικτή (Ενότ. 4, 5)."""
        if self.submission_closed_early:
            return False
        if self.stage not in (self.Stage.DETAILS, self.Stage.SUBMISSION):
            return False
        if not self.submission_end_date:
            return True
        check_date = today or timezone.localdate()
        return check_date <= self.submission_end_date

    def submission_days_remaining(self, today=None) -> int | None:
        """Ημέρες που απομένουν έως τη λήξη της προθεσμίας υποβολής αιτήσεων (αρνητικός αν έληξε)."""
        if not self.submission_end_date:
            return None
        check_date = today or timezone.localdate()
        return (self.submission_end_date - check_date).days

    @property
    def available_plots_count(self):
        return self.plots.count()

    @property
    def community(self):
        """Η μοναδική Κοινότητα των οικοπέδων της γνωστοποίησης (Ενότ. 4, 6, 7)."""
        if self.pk:
            plot = self.plots.select_related("community").order_by("pk").first()
            if plot is not None:
                return plot.community
        return getattr(self, "_fallback_community", None)

    @property
    def communities_label(self):
        """Όνομα της Κοινότητας των οικοπέδων της γνωστοποίησης (για εμφάνιση στους πίνακες)."""
        if self.pk:
            names = sorted({plot.community.name for plot in self.plots.select_related("community").all()})
            if names:
                return ", ".join(names)
        fallback = getattr(self, "_fallback_community", None)
        return fallback.name if fallback is not None else "—"

    @classmethod
    def for_community(cls, community, on_date=None):
        """Δημοσιευμένες γνωστοποιήσεις με οικόπεδα της `community`."""
        cycles = cls.objects.filter(plots__community=community, published_at__isnull=False).distinct()
        if on_date is not None:
            cycles = cycles.filter(announcement_date__lte=on_date, submission_end_date__gte=on_date)
        return cycles


def _validate_single_community_plots(sender, instance, action, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    Plot = apps.get_model("plots", "Plot")
    query = Q(pk__in=pk_set)
    if instance.pk:
        query |= Q(submission_cycles=instance)
    community_ids = set(Plot.objects.filter(query).values_list("community_id", flat=True).distinct())
    if len(community_ids) > 1:
        raise ValidationError(
            "Όλα τα οικόπεδα μιας γνωστοποίησης πρέπει να ανήκουν στην ίδια Κοινότητα (Ενότ. 4, 6, 7)."
        )
    if instance.is_active:
        busy_q = Q(submission_cycles__stage__in=SubmissionCycle.ACTIVE_STAGES)
        if instance.pk:
            busy_q &= ~Q(submission_cycles=instance)
        busy = list(
            Plot.objects.filter(pk__in=pk_set)
            .filter(busy_q | Q(allocations__status="active"))
            .distinct()
            .order_by("id")
        )
        if busy:
            labels = ", ".join(p.row_label for p in busy)
            raise ValidationError(
                f"Το οικόπεδο ({labels}) δεν είναι διαθέσιμο γιατί περιλαμβάνεται ήδη σε ενεργή γνωστοποίηση ή έχει ενεργή κατανομή."
            )


m2m_changed.connect(_validate_single_community_plots, sender=SubmissionCycle.plots.through)


class SubmissionCyclePublication(AuditedModel):
    """9.2 One way the announcement was made known.

    The four fixed methods are each recorded exactly once, with a date and no free text;
    «Άλλο» may be recorded any number of times, each with a date and a comment.
    """

    class PublicationMethod(models.TextChoices):
        COMMUNITY = "community", "Αποστολή/ανάρτηση στην Κοινότητα ή στο Δ.Δ."
        DISTRICT_OFFICE = "district_office", "Έντυπη ανάρτηση στα γραφεία Επαρχιακής Διοίκησης"
        DISTRICT_SITE = "district_site", "Ιστοσελίδα Επαρχιακής Διοίκησης"
        MINISTRY_SITE = "ministry_site", "Ιστοσελίδα ΥΠΕΣ"
        OTHER = "other", "Άλλο"

    FIXED_METHODS = (
        PublicationMethod.COMMUNITY,
        PublicationMethod.DISTRICT_OFFICE,
        PublicationMethod.DISTRICT_SITE,
        PublicationMethod.MINISTRY_SITE,
    )

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
        constraints = [
            models.UniqueConstraint(
                fields=["submission_cycle", "method"],
                condition=~models.Q(method="other"),
                name="unique_fixed_publication_method_per_cycle",
            )
        ]

    @property
    def is_fixed(self):
        return self.method != self.PublicationMethod.OTHER

    @property
    def row_label(self):
        return f"{self.get_method_display()} — {self.published_on}"
