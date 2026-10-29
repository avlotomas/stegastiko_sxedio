"""Αίτηση για Παραχώρηση Οικοπέδου — Παράρτημα 3 του Σχεδίου (Ενότ. 5).

A separate model from `applications.Application`: it follows the official form the
citizens fill in, section by section (1–12 + Ένορκη Δήλωση + Κατάλογος Δικαιολογητικών).
Persons are shared with the «Άτομα» registry (`Person`).
"""

from decimal import Decimal

from django.db import models

from applications.models import Person
from core.models import AuditedModel, Community


class ResidenceCategory(models.TextChoices):
    """Ενότητα 2 της Αίτησης / Ενότ. 11 του Σχεδίου."""

    AUTOCHTHON = "autochthon", "(Α) Αυτόχθονας"
    DISPLACED = "displaced", "(Α) Εκτοπισθείς"
    INTERNAL_EMIGRANT = "internal_emigrant", "(Β) Απόδημος Εσωτερικού"
    REPATRIATED = "repatriated", "(Γ) Επαναπατρισθείς / Απόδημος Εξωτερικού"
    NEIGHBOURING = "neighbouring", "(Δ) Κάτοικος Γειτονικής Κοινότητας"


class EligibilityResult(models.TextChoices):
    PASS = "pass", "Κατ' αρχήν πληροί"
    FAIL = "fail", "Δεν πληροί"
    PENDING = "pending", "Εκκρεμεί έλεγχος"


class EligibilityOverride(models.TextChoices):
    PASS = "pass", "ΔΙΚΑΙΟΥΧΟΣ"
    FAIL = "fail", "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"


class ApplicationCompleteness(models.TextChoices):
    COMPLETE = "complete", "Πλήρης"
    INCOMPLETE = "incomplete", "Ελλιπής"


class DocumentsCompleteness(models.TextChoices):
    COMPLETE = "complete", "Ολοκληρωμένη"
    INCOMPLETE = "incomplete", "Ελλιπής"


class ApplicationStage(models.TextChoices):
    COLLECTION = "collection", "Συλλογή πληροφοριών και πιστοποιητικών"
    EXAMINATION = "examination", "Εξέταση επιλεξιμότητας"
    PRIORITIZATION = "prioritization", "Επιλογή και προτεραιοποίηση"
    OBJECTIONS = "objections", "Προκαταρκτικός κατάλογος — Ενστάσεις"
    OBJECTIONS_COMMITTEE = "objections_committee", "Επιτροπή Εξέτασης Ενστάσεων"
    LOTTERY = "lottery", "Στάδιο κλήρωσης"
    AGREEMENT = "agreement", "Υπογραφή συμφωνίας και πληρωμή"
    COMPLETED = "completed", "Ολοκλήρωση"
    REJECTED = "rejected", "Απόρριψη από λειτουργό"
    COMMITTEE_REJECTED = "committee_rejected", "Απόρριψη από Επιτροπή"
    FORFEITED = "forfeited", "Απόρριψη — μη προσέλευση/υπογραφή/πληρωμή"


REJECTION_STAGES = (
    ApplicationStage.REJECTED,
    ApplicationStage.COMMITTEE_REJECTED,
    ApplicationStage.FORFEITED,
)


class PlotAllocationStatus(models.TextChoices):
    PENDING = "pending", "Εκκρεμεί"
    ALLOCATED = "allocated", "Πήρε οικόπεδο"
    RUNNER_UP = "runner_up", "Επιλαχών"
    NOT_ALLOCATED = "not_allocated", "Δεν πήρε οικόπεδο"


class PlotApplication(AuditedModel):
    class FamilyStatus(models.TextChoices):
        COUPLE_WITH_CHILDREN = "couple_with_children", "Ζεύγος με τέκνα"
        COUPLE_WITHOUT_CHILDREN = "couple_without_children", "Ζεύγος χωρίς τέκνα"
        SINGLE_PARENT = "single_parent", "Μονογονεϊκή οικογένεια"

    class SingleParentStatus(models.TextChoices):
        UNMARRIED = "unmarried", "Άγαμος/η"
        WIDOWED = "widowed", "Χήρος/α"
        DIVORCED = "divorced", "Διαζευγμένος/η"
        OTHER = "other", "Άλλο"

    COUPLE_STATUSES = (FamilyStatus.COUPLE_WITH_CHILDREN, FamilyStatus.COUPLE_WITHOUT_CHILDREN)

    announcement = models.ForeignKey(
        "cases.SubmissionCycle",
        on_delete=models.PROTECT,
        related_name="applications",
        help_text="Γνωστοποίηση υποβολής αιτήσεων (Ενότ. 4, 5)",
    )
    protocol_number = models.CharField(max_length=32, unique=True)
    submitted_on = models.DateField(null=True, blank=True, help_text="Ημερομηνία υποβολής (Ενότ. 5)")

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
        blank=True,
        help_text="Έγκυρη ηλεκτρονική διεύθυνση για την επίσημη επικοινωνία (Ενότ. 6, 7)",
    )
    correspondence_street = models.CharField(max_length=255, blank=True)
    correspondence_number = models.CharField(max_length=32, blank=True)
    correspondence_apartment = models.CharField(max_length=32, blank=True)
    correspondence_community = models.CharField(max_length=255, blank=True)
    correspondence_postal_code = models.CharField(max_length=16, blank=True)
    correspondence_district = models.CharField(max_length=128, blank=True)

    # 2. Τόπος διαμονής αιτητή/αιτήτριας
    residence_category = models.CharField(
        max_length=32, choices=ResidenceCategory.choices, blank=True
    )
    residence_street = models.CharField(max_length=255, blank=True)
    residence_number = models.CharField(max_length=32, blank=True)
    residence_apartment = models.CharField(max_length=32, blank=True)
    residence_postal_code = models.CharField(max_length=16, blank=True)
    residence_community = models.CharField(
        max_length=255,
        blank=True,
        help_text="Κοινότητα / Δ.Δ. διαμονής (για (Δ): η Γειτονική Κοινότητα)",
    )
    resides_in_controlled_areas = models.BooleanField(
        default=False,
        help_text="Διαμένει σε ελεγχόμενες από την Κυπριακή Δημοκρατία περιοχές (Ενότ. 11.ΙΙΙ)",
    )
    origin_parent_description = models.TextField(
        blank=True, help_text="(Β) Καταγωγή από την Κοινότητα ως προς ποιο γονέα"
    )
    previous_residence_address = models.CharField(
        max_length=255, blank=True, help_text="(Β) Διεύθυνση κατά την περίοδο μόνιμης κατοίκησης"
    )
    residence_notes = models.TextField(blank=True, help_text="Αναλυτική περιγραφή / λοιπές πληροφορίες")

    # 3. Οικογενειακή κατάσταση
    family_status = models.CharField(max_length=32, choices=FamilyStatus.choices, blank=True)
    single_parent_status = models.CharField(
        max_length=16, choices=SingleParentStatus.choices, blank=True
    )
    single_parent_other = models.CharField(max_length=255, blank=True)

    # 9. Άλλη ακίνητη ιδιοκτησία (Ενότ. 10.Δ)
    has_dwelling = models.BooleanField(null=True)
    has_dwelling_details = models.TextField(blank=True)
    has_residential_land = models.BooleanField(null=True)
    has_residential_land_details = models.TextField(blank=True)

    # 10. Αποξένωση ακίνητης ιδιοκτησίας (Ενότ. 10.Ε)
    has_alienated_property = models.BooleanField(null=True)
    has_alienated_property_details = models.TextField(blank=True)

    # 11. Παραχώρηση άλλης κρατικής στεγαστικής βοήθειας (Ενότ. 20.3)
    previous_housing_aid = models.BooleanField(null=True)
    previous_housing_aid_details = models.TextField(blank=True)

    # Σειρά προτεραιότητας μεταξύ των αιτήσεων του ατόμου (ορίζεται στην καρτέλα «Άτομα»)
    preference_order = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Σειρά προτεραιότητας μεταξύ των αιτήσεων παραχώρησης οικοπέδου του ατόμου",
    )

    # 12. Υπογραφές (Ενότ. 5) · Ένορκη δήλωση
    applicant_signed = models.BooleanField(default=False)
    spouse_signed = models.BooleanField(default=False)
    sworn_declaration_date = models.DateField(null=True, blank=True)
    sworn_court = models.CharField(max_length=128, blank=True, help_text="Επαρχιακό Δικαστήριο")
    sworn_by_applicant = models.BooleanField(default=False)
    sworn_by_spouse = models.BooleanField(default=False)

    # Κατάλογος απαιτούμενων δικαιολογητικών (κωδικοί του documents.DOCUMENT_CATALOG)
    attached_documents = models.JSONField(default=list, blank=True)
    document_notes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Σημειώσεις ανά πιστοποιητικό/δικαιολογητικό (κωδικός -> σημείωση)",
    )
    other_documents = models.TextField(blank=True, help_text="Άλλα πιστοποιητικά που επισυνάπτονται")
    documents_completeness = models.CharField(
        max_length=16,
        choices=DocumentsCompleteness.choices,
        default=DocumentsCompleteness.INCOMPLETE,
        help_text="Κατάσταση πληρότητας απαιτούμενων δικαιολογητικών (Ενότ. 5, 20.2)",
    )
    documents_complete_override = models.BooleanField(
        default=False,
        help_text="Χειροκίνητος χαρακτηρισμός της αίτησης ως ολοκληρωμένης ως προς τα δικαιολογητικά παρά τις ελλείψεις (Ενότ. 5, 20.2)",
    )
    documents_complete_reason = models.TextField(
        blank=True,
        help_text="Περιγραφή του λόγου για τον οποίο η αίτηση χαρακτηρίζεται ως ολοκληρωμένη ενώ λείπουν δικαιολογητικά (Ενότ. 5, 20.2)",
    )

    # Απόρριψη της αίτησης από τον λειτουργό με αιτιολογία (Ενότ. 5(β), 6, 20)
    incomplete_rejected = models.BooleanField(
        default=False,
        help_text="Απόρριψη της αίτησης από τον λειτουργό (Ενότ. 5(β), 6, 20)",
    )
    incomplete_rejection_reason = models.TextField(
        blank=True,
        help_text="Λόγος απόρριψης της αίτησης (Ενότ. 5(β), 6, 20)",
    )
    incomplete_rejected_on = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία απόρριψης της αίτησης",
    )
    forfeited = models.BooleanField(
        default=False,
        help_text="Απόρριψη λόγω μη προσέλευσης / μη υπογραφής Συμφωνίας / μη πληρωμής (Ενότ. 8)",
    )
    forfeited_reason = models.TextField(
        blank=True,
        help_text="Αιτιολογία απόρριψης λόγω μη προσέλευσης / μη υπογραφής / μη πληρωμής (Ενότ. 8)",
    )
    forfeited_on = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία απόρριψης λόγω μη προσέλευσης / μη υπογραφής / μη πληρωμής (Ενότ. 8)",
    )

    # Αποτέλεσμα αυτόματου ελέγχου (υπολογίζεται σε κάθε αποθήκευση — rules.evaluate)
    children_count = models.PositiveIntegerField(default=0)
    recognized_children_count = models.PositiveIntegerField(default=0)
    family_members_count = models.PositiveIntegerField(default=0)
    family_income_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    completeness_result = models.CharField(
        max_length=16,
        choices=ApplicationCompleteness.choices,
        default=ApplicationCompleteness.INCOMPLETE,
        help_text="Κατάσταση πληρότητας της αίτησης (υποχρεωτικά πεδία, υπογραφές, δικαιολογητικά, Ενότ. 5, 20.2)",
    )
    completeness_details = models.JSONField(default=list, blank=True)
    eligibility_result = models.CharField(
        max_length=16, choices=EligibilityResult.choices, default=EligibilityResult.PENDING
    )
    eligibility_auto_result = models.CharField(
        max_length=16,
        choices=EligibilityResult.choices,
        default=EligibilityResult.PENDING,
        help_text="Αποτέλεσμα του αυτόματου ελέγχου επιλεξιμότητας από το λογισμικό, πριν από τυχόν χειροκίνητη αλλαγή (Ενότ. 10, 20)",
    )
    eligibility_details = models.JSONField(default=list, blank=True)
    eligibility_override = models.CharField(
        max_length=16,
        choices=EligibilityOverride.choices,
        blank=True,
        help_text="Χειροκίνητη αλλαγή του αποτελέσματος του λογισμικού κατά πόσο ο αιτητής είναι δικαιούχος (Ενότ. 6)",
    )
    eligibility_override_reason = models.TextField(
        blank=True,
        help_text="Αιτιολογία της χειροκίνητης αλλαγής του αποτελέσματος επιλεξιμότητας (Ενότ. 6)",
    )
    priority_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Θέση στον κατάλογο προτεραιοποίησης της Κοινότητας μετά από χειροκίνητη αλλαγή σειράς (Ενότ. 6, 11)",
    )
    application_stage = models.CharField(
        max_length=24,
        choices=ApplicationStage.choices,
        default=ApplicationStage.COLLECTION,
        help_text="Στάδιο αίτησης",
    )
    plot_allocation_status = models.CharField(
        max_length=16,
        choices=PlotAllocationStatus.choices,
        default=PlotAllocationStatus.PENDING,
        help_text="Κατάσταση παραχώρησης οικοπέδου (Εκκρεμεί, Πήρε οικόπεδο, Επιλαχών, Δεν πήρε οικόπεδο — Ενότ. 8, 9)",
    )

    _history_hidden_fields = frozenset(
        {
            "children_count",
            "recognized_children_count",
            "family_members_count",
            "family_income_total",
            "documents_completeness",
            "completeness_result",
            "completeness_details",
            "eligibility_result",
            "eligibility_auto_result",
            "eligibility_details",
            "plot_allocation_status",
        }
    )

    class Meta:
        ordering = ("-submitted_on", "-id")

    def __init__(self, *args, **kwargs):
        community = kwargs.pop("community", None)
        community_id = kwargs.pop("community_id", None)
        if community is None and community_id is not None:
            community = Community.objects.filter(pk=community_id).first()
        if community is not None and "announcement" not in kwargs and "announcement_id" not in kwargs:
            from datetime import date

            from cases.models import SubmissionCycle

            cycle = (
                SubmissionCycle.objects.filter(plots__community=community)
                .order_by("-published_at", "-announcement_date", "-pk")
                .first()
                or SubmissionCycle.objects.order_by("-published_at", "-announcement_date", "-pk").first()
            )
            if cycle is None:
                cycle = SubmissionCycle.objects.create(
                    announcement_date=kwargs.get("submitted_on") or date(2026, 9, 1),
                    submission_months=2,
                )
            if cycle.community is None:
                cycle._fallback_community = community
            kwargs["announcement"] = cycle
        super().__init__(*args, **kwargs)
        if community is not None:
            self._fallback_community = community

    def __str__(self):
        return self.protocol_number

    @property
    def community(self):
        """Η Κοινότητα της γνωστοποίησης στην οποία υποβλήθηκε η αίτηση."""
        if self.announcement_id:
            comm = self.announcement.community
            if comm is not None:
                return comm
        return getattr(self, "_fallback_community", None)

    @property
    def community_id(self):
        comm = self.community
        return comm.pk if comm is not None else None

    @property
    def open_pending_requirements(self):
        if not self.pk:
            return []
        return [req for req in self.pending_requirements.all() if not req.is_fulfilled]

    @property
    def is_pending_extra_info(self) -> bool:
        return bool(self.open_pending_requirements)

    @property
    def has_registered_objection(self) -> bool:
        if not self.pk:
            return False
        return self.objections.exists()

    def _audit_value(self, field_name, value):
        if field_name == "priority_rank":
            override = getattr(self, "_priority_rank_audit_values", None)
            if override and value in override:
                return override[value]
            if value is None:
                return "Σειρά λογισμικού"
        return super()._audit_value(field_name, value)

    def _audit_context(self):
        # Each history entry records the stage at which the change was made.
        case_id, application_id, section_ref = super()._audit_context()
        if not section_ref:
            previous = getattr(self, "_previous_values", None) or {}
            section_ref = f"stage:{previous.get('application_stage') or self.application_stage}"
        return case_id, application_id, section_ref

    @property
    def is_couple(self) -> bool:
        return self.family_status in self.COUPLE_STATUSES

    @property
    def submission_locked(self) -> bool:
        """Ενότ. 4, 5: μετά τη λήξη (ή το πρόωρο κλείσιμο) της προθεσμίας υποβολής η αίτηση δεν αλλάζει."""
        cycle = self.announcement if self.announcement_id else None
        return bool(cycle and cycle.is_published and not cycle.submission_open())

    @property
    def is_documents_complete(self) -> bool:
        return (
            self.documents_completeness == DocumentsCompleteness.COMPLETE
            or bool(self.documents_complete_override)
        )

    @property
    def is_complete(self) -> bool:
        return self.completeness_result == ApplicationCompleteness.COMPLETE

    @property
    def is_rejected_incomplete(self) -> bool:
        return bool(self.incomplete_rejected) or self.application_stage == ApplicationStage.REJECTED

    @property
    def is_eligibility_pending(self) -> bool:
        return self.eligibility_result == EligibilityResult.PENDING

    @property
    def has_beneficiary_outcome(self) -> bool:
        """Χωρίς «Δικαιούχος» / «Παραχώρηση οικοπέδου» όταν απορρίφθηκε από τον λειτουργό ή εκκρεμεί ο έλεγχος."""
        return not (self.is_rejected_incomplete or self.is_eligibility_pending)

    @property
    def eligibility_label(self) -> str:
        if self.is_rejected_incomplete:
            return ""
        return self.get_eligibility_result_display()

    @property
    def beneficiary_status(self) -> str:
        if self.is_rejected_incomplete:
            return ""
        if self.is_eligibility_pending:
            return EligibilityResult.PENDING
        if self.eligibility_result == EligibilityResult.FAIL:
            return EligibilityResult.FAIL
        if (
            self.completeness_result == ApplicationCompleteness.COMPLETE
            and self.documents_completeness == DocumentsCompleteness.COMPLETE
            and self.eligibility_result == EligibilityResult.PASS
        ):
            return EligibilityResult.PASS
        return EligibilityResult.PENDING

    @property
    def is_beneficiary(self) -> bool:
        return self.beneficiary_status == EligibilityResult.PASS

    @property
    def beneficiary_label(self) -> str:
        if not self.has_beneficiary_outcome:
            return ""
        status = self.beneficiary_status
        if status == EligibilityResult.PASS:
            return "ΔΙΚΑΙΟΥΧΟΣ"
        if status == EligibilityResult.FAIL:
            return "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"
        return "ΕΚΚΡΕΜΕΙ"

    @property
    def application_stage_label(self) -> str:
        from plot_applications.stage_labels import get_application_stage_label

        return get_application_stage_label(self.application_stage)

    @property
    def is_eligibility_overridden(self) -> bool:
        return self.eligibility_override in EligibilityOverride.values

    @property
    def stage_badge(self) -> str:
        if self.application_stage == ApplicationStage.COMPLETED:
            return "pass"
        if self.application_stage in REJECTION_STAGES:
            return "fail"
        return "pending"

    @property
    def plot_allocation_label(self) -> str:
        if not self.has_beneficiary_outcome:
            return ""
        return self.get_plot_allocation_status_display()

    @property
    def plot_allocation_badge(self) -> str:
        if self.plot_allocation_status == PlotAllocationStatus.ALLOCATED:
            return "pass"
        if self.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED:
            return "fail"
        return "pending"

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
        OTHER = "other", "Άλλο"

    application = models.ForeignKey(PlotApplication, on_delete=models.CASCADE, related_name="parties")
    role = models.CharField(max_length=16, choices=Role.choices)
    social_insurance_number = models.CharField(max_length=32, blank=True)
    refugee_identity_number = models.CharField(max_length=64, blank=True)
    alien_registration_number = models.CharField(max_length=64, blank=True)
    citizenship = models.CharField(max_length=16, choices=Citizenship.choices, blank=True)
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
        return self.citizenship == self.Citizenship.CYPRIOT


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


class IncomeDeclaration(AuditedModel):
    """8. Εισοδήματα του έτους που προηγείται της αίτησης (Ενότ. 10.Στ)."""

    class Member(models.TextChoices):
        APPLICANT = "applicant", "Αιτητής/τρια"
        SPOUSE = "spouse", "Σύζυγος/Συμβίος"
        CHILD = "child", "Τέκνο"
        OTHER = "other", "Άλλο μέλος της οικογένειας"

    class EmploymentType(models.TextChoices):
        EMPLOYEE = "employee", "Μισθωτός Εργαζόμενος"
        SELF_EMPLOYED = "self_employed", "Αυτοτελώς Εργαζόμενος"
        UNEMPLOYED = "unemployed", "Άνεργος"
        OTHER_SOURCE = "other", "Άλλη πηγή εισοδήματος"

    application = models.ForeignKey(PlotApplication, on_delete=models.CASCADE, related_name="incomes")
    member = models.CharField(max_length=16, choices=Member.choices, default=Member.APPLICANT)
    child = models.ForeignKey(
        ApplicationChild,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incomes",
    )
    employment_type = models.CharField(max_length=16, choices=EmploymentType.choices, blank=True)
    description = models.CharField(
        max_length=255, blank=True, help_text="Περιγραφή / πηγή εισοδήματος"
    )
    gross_annual_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Ετήσιο ακαθάριστο εισόδημα (συμπ. 13ου, 14ου, άλλου μισθού)",
    )

    class Meta:
        ordering = ("application", "id")

    @property
    def member_label(self) -> str:
        if self.member == self.Member.CHILD and self.child_id:
            full_name = f"{self.child.first_name} {self.child.last_name}".strip()
            if full_name:
                return f"Τέκνο: {full_name}"
        return self.get_member_display()

    @property
    def total(self) -> Decimal:
        return self.gross_annual_income or Decimal("0")


class Objection(AuditedModel):
    """Ένσταση αιτητή κατά του Προκαταρκτικού Καταλόγου Δικαιούχων (Ενότ. 7)."""

    class ObjectionType(models.TextChoices):
        REJECTION = "rejection", "Διαφωνία με την απόρριψη (Ενότ. 7(α))"
        RANK = "rank", "Διαφωνία με τη σειρά κατάταξης (Ενότ. 7(β))"

    class Status(models.TextChoices):
        PENDING = "pending", "Εκκρεμεί εξέταση"
        UPHELD = "upheld", "Ικανοποιήθηκε"
        DISMISSED = "dismissed", "Δεν ικανοποιήθηκε"

    application = models.ForeignKey(
        PlotApplication,
        on_delete=models.CASCADE,
        related_name="objections",
        help_text="Αίτηση για την οποία υποβλήθηκε η ένσταση (Ενότ. 7)",
    )
    preliminary_entry = models.ForeignKey(
        "allocation.RankingEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="objections",
        help_text="Εγγραφή στον Προκαταρκτικό Κατάλογο κατά την υποβολή της ένστασης (Ενότ. 6, 7)",
    )
    submitted_on = models.DateField(
        help_text="Ημερομηνία υποβολής ένστασης (εντός 21 ημερών από τη λήψη της επιστολής, Ενότ. 7)"
    )
    objection_type = models.CharField(
        max_length=16,
        choices=ObjectionType.choices,
        help_text="Είδος ένστασης (Ενότ. 7)",
    )
    grounds = models.TextField(
        help_text="Αιτιολόγηση ένστασης / Έκθεση Γεγονότων (Ενότ. 7)"
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Απόφαση Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
    )
    decided_on = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία απόφασης Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
    )
    decision_notes = models.TextField(
        blank=True,
        help_text="Σκεπτικό / απόφαση Επιτροπής Εξέτασης Ενστάσεων (Ενότ. 7)",
    )
    outcome_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Ημερομηνία/ώρα αποστολής email απόφασης ένστασης (Ενότ. 7)",
    )

    class Meta:
        ordering = ("submitted_on", "id")

    def __str__(self):
        return f"Ένσταση {self.application.protocol_number} ({self.get_status_display()})"

    def _audit_context(self):
        case_id, application_id, section_ref = super()._audit_context()
        return case_id, self.application_id or application_id, section_ref or "stage:objections_committee"


class PendingRequirement(AuditedModel):
    """Επιπλέον στοιχείο / πιστοποιητικό που ζητείται από την Επιτροπή Εξέτασης Ενστάσεων (Ενότ. 7)."""

    application = models.ForeignKey(
        PlotApplication,
        on_delete=models.CASCADE,
        related_name="pending_requirements",
        help_text="Αίτηση από την οποία ζητούνται επιπλέον στοιχεία (Ενότ. 7)",
    )
    objection = models.ForeignKey(
        Objection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pending_requirements",
        help_text="Σχετική ένσταση στο πλαίσιο της οποίας ζητούνται τα στοιχεία (Ενότ. 7)",
    )
    description = models.CharField(
        max_length=500,
        help_text="Περιγραφή στοιχείου/πιστοποιητικού που πρέπει να προσκομισθεί",
    )
    is_fulfilled = models.BooleanField(
        default=False,
        help_text="Έχει προσκομισθεί / ελεγχθεί",
    )
    requested_on = models.DateField(
        auto_now_add=True,
        help_text="Ημερομηνία που ζητήθηκε",
    )
    fulfilled_on = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία προσκόμισης",
    )

    class Meta:
        ordering = ("is_fulfilled", "id")

    def __str__(self):
        return f"{self.application.protocol_number}: {self.description}"

    def _audit_context(self):
        case_id, application_id, section_ref = super()._audit_context()
        return case_id, self.application_id or application_id, section_ref or "stage:objections_committee"

