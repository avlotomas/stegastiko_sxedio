from decimal import Decimal

from django.db import models
from django.utils import timezone

from cases.models import SubmissionCycle
from core.models import AuditedModel


class RankingList(AuditedModel):
    class ListType(models.TextChoices):
        PRELIMINARY = "preliminary", "Προκαταρκτικός"
        FINAL = "final", "Τελικός"

    submission_cycle = models.ForeignKey(
        SubmissionCycle, on_delete=models.PROTECT, related_name="ranking_lists"
    )
    list_type = models.CharField(max_length=16, choices=ListType.choices)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by_id = models.IntegerField(null=True, blank=True)
    objection_deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Λήξη της περιόδου ενστάσεων του Προκαταρκτικού Καταλόγου (Ενότ. 7)",
    )
    plots_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Διαθέσιμα οικόπεδα της γνωστοποίησης κατά την έκδοση του Τελικού Καταλόγου (Ενότ. 8)",
    )
    notifications_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Αποστολή των επιστολών / email του καταλόγου στους αιτητές (Ενότ. 6(β), 7(ε))· μετά δεν ανακαλείται",
    )

    class Meta:
        ordering = ("-id",)
        unique_together = ("submission_cycle", "list_type")

    def __init__(self, *args, **kwargs):
        community = kwargs.pop("community", None)
        kwargs.pop("community_id", None)
        super().__init__(*args, **kwargs)
        if community is not None:
            self._fallback_community = community

    @property
    def community(self):
        if self.submission_cycle_id:
            comm = self.submission_cycle.community
            if comm is not None:
                return comm
        return getattr(self, "_fallback_community", None)

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        if self.pk:
            from plot_applications.rules import apply_evaluation

            for entry in self.entries.select_related("application").all():
                if entry.application_id:
                    apply_evaluation(entry.application)
        return result


class RankingEntry(AuditedModel):
    class Status(models.TextChoices):
        ELIGIBLE = "eligible", "Δικαιούχος"
        ALTERNATE = "alternate", "Επιλαχών"
        REJECTED = "rejected", "Μη δικαιούχος"

    ranking_list = models.ForeignKey(RankingList, on_delete=models.CASCADE, related_name="entries")
    application = models.ForeignKey(
        "plot_applications.PlotApplication",
        on_delete=models.CASCADE,
        related_name="ranking_entries",
    )
    proposed_rank = models.PositiveIntegerField(null=True, blank=True)
    finalized_rank = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    comments = models.TextField(blank=True)
    snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Κριτήρια προτεραιότητας (Ενότ. 11) / λόγοι απόρριψης όπως ίσχυαν κατά την έκδοση του καταλόγου",
    )
    notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Ημερομηνία/ώρα αποστολής επιστολής/email στον αιτητή (Ενότ. 6, 7)",
    )
    receipt_confirmed_on = models.DateField(
        null=True,
        blank=True,
        help_text="Ημερομηνία επιβεβαίωσης λήψης από τον αιτητή εντός 5 ημερών (Ενότ. 6)",
    )
    objection_deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Προθεσμία υποβολής ένστασης του αιτητή (21 ημέρες από τη λήψη/αποστολή, Ενότ. 6, 7)",
    )

    class Meta:
        ordering = ("finalized_rank", "proposed_rank", "id")
        unique_together = ("ranking_list", "application")

    @property
    def effective_receipt_date(self):
        """Ημερομηνία λήψης κατά Ενότ. 6: ημερομηνία επιβεβαίωσης εντός 5 ημ. ή ημερομηνία αποστολής."""
        if self.receipt_confirmed_on is not None:
            return self.receipt_confirmed_on
        if self.notified_at is not None:
            if timezone.is_aware(self.notified_at):
                return timezone.localtime(self.notified_at).date()
            return self.notified_at.date()
        return None

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        if self.application_id:
            from plot_applications.rules import apply_evaluation

            apply_evaluation(self.application)
        return result

    def delete(self, *args, **kwargs):
        application = self.application if self.application_id else None
        result = super().delete(*args, **kwargs)
        if application is not None and application.pk:
            from plot_applications.rules import apply_evaluation

            apply_evaluation(application)
        return result


class Lottery(AuditedModel):
    class LotteryType(models.TextChoices):
        RANK_TIE = "rank_tie", "Κλήρωση ισοψηφίας κατάταξης"
        PARCEL_ALLOCATION = "parcel_allocation", "Κλήρωση κατανομής οικοπέδων"

    submission_cycle = models.ForeignKey(
        SubmissionCycle, on_delete=models.PROTECT, related_name="lotteries"
    )
    lottery_type = models.CharField(
        max_length=32,
        choices=LotteryType.choices,
        default=LotteryType.PARCEL_ALLOCATION,
    )
    lottery_date = models.DateTimeField(
        help_text="Ημερομηνία και ώρα διεξαγωγής κλήρωσης (Ενότ. 9)"
    )
    location = models.CharField(max_length=255)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Ολοκλήρωση κλήρωσης οικοπέδων (Ενότ. 9)",
    )
    comments = models.TextField(blank=True)

    def __init__(self, *args, **kwargs):
        community = kwargs.pop("community", None)
        kwargs.pop("community_id", None)
        super().__init__(*args, **kwargs)
        if community is not None:
            self._fallback_community = community

    @property
    def community(self):
        if self.submission_cycle_id:
            return self.submission_cycle.community
        return getattr(self, "_fallback_community", None)


class Allocation(AuditedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ενεργή"
        CANCELLED = "cancelled", "Ακυρώθηκε"

    lottery = models.ForeignKey(
        Lottery, on_delete=models.SET_NULL, null=True, blank=True, related_name="allocations"
    )
    # Empty only for allocations made through the removed old citizen application.
    application = models.ForeignKey(
        "plot_applications.PlotApplication",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="allocations",
    )
    parcel = models.ForeignKey(
        "plots.Plot", on_delete=models.PROTECT, related_name="allocations"
    )
    replaces = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacements",
        help_text="Προηγούμενη κατανομή που αντικαταστάθηκε από επιλαχόντα (Ενότ. 8)",
    )
    runner_up_justification = models.TextField(
        blank=True,
        help_text="Αιτιολογία επιλογής επιλαχόντα όταν δεν επιλέγεται ο αμέσως επόμενος κατά σειρά (Ενότ. 8)",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    cancellation_reason = models.TextField(blank=True)
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-allocated_at", "-id")

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        if self.application_id:
            from plot_applications.rules import apply_evaluation

            apply_evaluation(self.application)
        return result

    def delete(self, *args, **kwargs):
        application = self.application if self.application_id else None
        result = super().delete(*args, **kwargs)
        if application is not None and application.pk:
            from plot_applications.rules import apply_evaluation

            apply_evaluation(application)
        return result


class Payment(AuditedModel):
    class Status(models.TextChoices):
        PAID = "paid", "ΠΛΗΡΩΘΗΚΕ"
        PENDING = "pending", "ΕΚΚΡΕΜΕΙ"
        UNPAID = "unpaid", "ΜΗ ΠΛΗΡΩΜΕΝΗ"

    allocation = models.OneToOneField(Allocation, on_delete=models.CASCADE, related_name="payment")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Τιμή διάθεσης οικοπέδου (25% Γενικής Εκτίμησης, Ενότ. 13, 15)",
    )
    paid_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    comments = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.amount is None and self.allocation_id and self.allocation.parcel_id:
            self.amount = self.allocation.parcel.disposal_price or Decimal("0.00")
        return super().save(*args, **kwargs)


class Agreement(AuditedModel):
    class Status(models.TextChoices):
        SIGNED = "signed", "ΥΠΟΓΡΑΦΗΚΕ"
        NOT_SIGNED = "not_signed", "ΔΕΝ ΥΠΟΓΡΑΦΗΚΕ"
        NO_SHOW = "no_show", "ΜΗ ΠΡΟΣΕΛΕΥΣΗ"

    allocation = models.OneToOneField(Allocation, on_delete=models.CASCADE, related_name="agreement")
    appointment_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Ημερομηνία και ώρα προσέλευσης για υπογραφή και πληρωμή (Ενότ. 9, 12, 15)",
    )
    deadline = models.DateField(
        null=True,
        blank=True,
        help_text="Προθεσμία προσέλευσης για υπογραφή Συμφωνίας και πληρωμή (Ενότ. 8, 9)",
    )
    invited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Ημερομηνία/ώρα αποστολής πρόσκλησης υπογραφής (Ενότ. 9)",
    )
    signed_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_SIGNED)
    template_version = models.CharField(max_length=64, blank=True)
    comments = models.TextField(blank=True)


class AgreementTemplate(AuditedModel):
    """Πρότυπο Συμφωνίας Παραχώρησης (Παράρτημα 4, Ενότ. 12) σε μορφή Word (.docx)."""

    name = models.CharField(
        max_length=255,
        help_text="Ονομασία προτύπου Συμφωνίας Παραχώρησης (Παράρτημα 4, Ενότ. 12)",
    )
    version = models.CharField(
        max_length=64,
        blank=True,
        help_text="Έκδοση προτύπου",
    )
    template_file = models.FileField(
        upload_to="agreement_templates/",
        help_text="Αρχείο Word (.docx) με πεδία {{placeholders}} (Παράρτημα 4)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Ενεργό πρότυπο για παραγωγή Συμφωνιών",
    )

    class Meta:
        ordering = ("-is_active", "-id")

    def __str__(self):
        return f"{self.name} ({self.version})" if self.version else self.name


class TitleTransfer(AuditedModel):
    allocation = models.OneToOneField(Allocation, on_delete=models.CASCADE, related_name="title_transfer")
    transfer_date = models.DateField(null=True, blank=True)
    title_number = models.CharField(max_length=64, blank=True)
    title_issue_date = models.DateField(null=True, blank=True)
    comments = models.TextField(blank=True)


class ConstructionMonitoring(AuditedModel):
    class ProgressResult(models.TextChoices):
        IN_PROGRESS = "in_progress", "Σε εξέλιξη"
        COMPLETED = "completed", "Ολοκληρωμένη"
        NOT_STARTED = "not_started", "Δεν έχει προχωρήσει"

    agreement = models.OneToOneField(
        Agreement, on_delete=models.CASCADE, related_name="construction_monitoring"
    )
    two_year_check_done = models.BooleanField(default=False)
    two_year_result = models.CharField(max_length=16, choices=ProgressResult.choices, blank=True)
    three_year_check_done = models.BooleanField(default=False)
    housing_completed = models.BooleanField(default=False)
    extension_granted = models.BooleanField(default=False)
    new_deadline = models.DateField(null=True, blank=True)
    comments = models.TextField(blank=True)
