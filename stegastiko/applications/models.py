from django.core.exceptions import ValidationError
from django.db import models

from cases.models import SubmissionCycle
from core.models import AuditedModel, DocumentCatalogItem


class Person(AuditedModel):
    identity_number = models.CharField(max_length=32, unique=True)
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    date_of_birth = models.DateField()
    birth_place = models.CharField(max_length=128)
    birth_country = models.CharField(max_length=128)
    parents_birth_place = models.CharField(max_length=128)
    parents_birth_country = models.CharField(max_length=128)
    refugee_identity_number = models.CharField(
        max_length=64,
        blank=True,
        help_text="10.3.1 Αρ. Προσφυγικής Ταυτότητας (εκτοπισθέντες)",
    )
    citizenship_cypriot = models.BooleanField(
        default=False, help_text="10.3.1 Υπηκοότητα — Κύπριος Πολίτης"
    )
    citizenship_repatriated = models.BooleanField(
        default=False, help_text="10.3.1 Υπηκοότητα — Επαναπατρισθείς/είσα Κύπριος/α"
    )
    citizenship_eu = models.BooleanField(
        default=False, help_text="10.3.1 Υπηκοότητα — Πολίτης κράτους μέλους ΕΕ"
    )
    citizenship_other = models.CharField(
        max_length=128, blank=True, help_text="10.3.1 Άλλη υπηκοότητα (κείμενο)"
    )
    document_type = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("last_name", "first_name", "identity_number")

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.identity_number})"

    def clean(self):
        if self.pk:
            previous = Person.objects.filter(pk=self.pk).first()
            if previous and previous.identity_number != self.identity_number:
                raise ValidationError("The identity number cannot be changed.")


class Application(AuditedModel):
    class FamilyType(models.TextChoices):
        WITH_CHILDREN = "with_children", "Οικογένεια με τέκνα"
        COUPLE_NO_CHILDREN = "couple_no_children", "Ζεύγος χωρίς τέκνα"
        SINGLE_PARENT = "single_parent", "Μονογονεϊκή οικογένεια"
        OTHER = "other", "Άλλο"

    class CompletenessResult(models.TextChoices):
        COMPLETE = "complete", "ΠΛΗΡΗΣ"
        INCOMPLETE = "incomplete", "ΜΗ ΠΛΗΡΗΣ"

    class Outcome104(models.TextChoices):
        PASS = "pass", "Κατ' αρχήν πληροί"
        FAIL = "fail", "Κατ' αρχήν δεν πληροί"
        PENDING = "pending", "Εκκρεμεί έλεγχος"

    submission_cycle = models.ForeignKey(
        SubmissionCycle, on_delete=models.PROTECT, related_name="applications"
    )
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="applications_as_person1")
    person2 = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="applications_as_person2"
    )
    folder_number = models.CharField(max_length=32, unique=True)
    submitted_on = models.DateField()
    family_type = models.CharField(max_length=32, choices=FamilyType.choices)
    family_type_other = models.CharField(max_length=255, blank=True)
    applicant_email = models.EmailField()
    comments = models.TextField(blank=True)

    declared_children_count = models.PositiveIntegerField(default=0)
    recognized_dependent_children_count = models.PositiveIntegerField(default=0)
    family_members_count = models.PositiveIntegerField(default=0)

    person1_relationship = models.CharField(max_length=64, default="Αιτητής")
    person2_relationship = models.CharField(max_length=64, blank=True)
    person1_residence_community = models.CharField(max_length=255, blank=True)
    person2_residence_community = models.CharField(max_length=255, blank=True)
    person1_residence_address = models.CharField(max_length=255, blank=True)
    person2_residence_address = models.CharField(max_length=255, blank=True)
    person1_residence_start = models.DateField(null=True, blank=True)
    person2_residence_start = models.DateField(null=True, blank=True)

    is_family_type_correct = models.BooleanField(null=True, blank=True)
    corrected_family_type = models.CharField(max_length=32, choices=FamilyType.choices, blank=True)
    signatures_status = models.CharField(max_length=32, blank=True)
    completeness_result = models.CharField(
        max_length=16, choices=CompletenessResult.choices, blank=True
    )
    completeness_updated_at = models.DateTimeField(null=True, blank=True)
    completeness_comments = models.TextField(blank=True)
    outcome_104 = models.CharField(max_length=16, choices=Outcome104.choices, default=Outcome104.PENDING)
    residence_category = models.CharField(max_length=64, blank=True)
    person1_has_property = models.BooleanField(default=False)
    person2_has_property = models.BooleanField(default=False)
    person1_non_alienation_clear = models.BooleanField(default=True)
    person2_non_alienation_clear = models.BooleanField(default=True)
    person1_previous_aid_clear = models.BooleanField(default=True)
    person2_previous_aid_clear = models.BooleanField(default=True)
    person1_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    person2_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    children_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ("-submitted_on", "-id")

    def __str__(self):
        return self.folder_number


class DependentChild(AuditedModel):
    class ChildCategory(models.TextChoices):
        MINOR = "minor", "Ανήλικο"
        STUDENT = "student", "Σπουδάζει"
        NATIONAL_GUARD = "national_guard", "Εθνοφρουρός"
        ADULT_DISABILITY = "adult_disability", "Ενήλικο άτομο με αναπηρία"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="dependent_children")
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField()
    category = models.CharField(max_length=32, choices=ChildCategory.choices)
    is_recognized_dependent = models.BooleanField(default=False)

    class Meta:
        ordering = ("id",)


class SupportingDocument(AuditedModel):
    class Status(models.TextChoices):
        YES = "yes", "ΝΑΙ"
        NO = "no", "ΟΧΙ"
        NOT_REQUIRED = "not_required", "ΔΕΝ ΑΠΑΙΤΕΙΤΑΙ"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="supporting_documents")
    catalog_item = models.ForeignKey(
        DocumentCatalogItem, on_delete=models.PROTECT, related_name="application_documents"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ("catalog_item__code", "id")
        unique_together = ("application", "catalog_item")


class EligibilityCheck(AuditedModel):
    class Criterion(models.TextChoices):
        CITIZENSHIP = "10.4.1", "10.4.1 Κυπριακή υπηκοότητα"
        AGE = "10.4.2", "10.4.2 Ηλικία"
        RESIDENCE = "10.4.3", "10.4.3 Διαμονή"
        PROPERTY = "10.4.4", "10.4.4 Άλλη ακίνητη ιδιοκτησία"
        NON_ALIENATION = "10.4.5", "10.4.5 Μη αποξένωση"
        INCOME = "10.4.6", "10.4.6 Εισόδημα"
        PREVIOUS_AID = "10.4.7", "10.4.7 Προηγούμενη κρατική ενίσχυση"

    class Result(models.TextChoices):
        PASS = "pass", "ΠΛΗΡΟΥΤΑΙ"
        FAIL = "fail", "ΔΕΝ ΠΛΗΡΟΥΤΑΙ"
        PENDING = "pending", "ΕΚΚΡΕΜΕΙ"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="eligibility_checks")
    criterion = models.CharField(max_length=16, choices=Criterion.choices)
    person1_result = models.CharField(max_length=16, choices=Result.choices, default=Result.PENDING)
    person2_result = models.CharField(max_length=16, choices=Result.choices, blank=True)
    overall_result = models.CharField(max_length=16, choices=Result.choices, default=Result.PENDING)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ("criterion", "id")
        unique_together = ("application", "criterion")


class CommitteeDecision(AuditedModel):
    class Decision(models.TextChoices):
        ELIGIBLE = "eligible", "Δικαιούχος"
        NOT_ELIGIBLE = "not_eligible", "Μη Δικαιούχος"

    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="committee_decision"
    )
    decision = models.CharField(max_length=16, choices=Decision.choices)
    comments = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)


class Objection(AuditedModel):
    class Decision(models.TextChoices):
        ACCEPTED = "accepted", "ΑΠΟΔΟΧΗ"
        REJECTED = "rejected", "ΑΠΟΡΡΙΨΗ"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="objections")
    submitted_on = models.DateField()
    is_on_time = models.BooleanField(default=True)
    reason = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    ministry_letter_date = models.DateField(null=True, blank=True)
    decision = models.CharField(max_length=16, choices=Decision.choices, blank=True)
