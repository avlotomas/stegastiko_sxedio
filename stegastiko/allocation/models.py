from django.db import models

from applications.models import Application
from cases.models import Parcel, SubmissionCycle
from core.models import AuditedModel, Community


class RankingList(AuditedModel):
    class ListType(models.TextChoices):
        PRELIMINARY = "preliminary", "Προκαταρκτικός"
        FINAL = "final", "Τελικός"

    community = models.ForeignKey(Community, on_delete=models.PROTECT, related_name="ranking_lists")
    submission_cycle = models.ForeignKey(
        SubmissionCycle, on_delete=models.PROTECT, related_name="ranking_lists"
    )
    list_type = models.CharField(max_length=16, choices=ListType.choices)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-id",)
        unique_together = ("submission_cycle", "list_type")


class RankingEntry(AuditedModel):
    class Status(models.TextChoices):
        ELIGIBLE = "eligible", "Δικαιούχος"
        ALTERNATE = "alternate", "Επιλαχών"

    ranking_list = models.ForeignKey(RankingList, on_delete=models.CASCADE, related_name="entries")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="ranking_entries")
    proposed_rank = models.PositiveIntegerField(null=True, blank=True)
    finalized_rank = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ("finalized_rank", "proposed_rank", "id")
        unique_together = ("ranking_list", "application")


class Lottery(AuditedModel):
    class LotteryType(models.TextChoices):
        RANK_TIE = "rank_tie", "Κλήρωση ισοψηφίας κατάταξης"
        PARCEL_ALLOCATION = "parcel_allocation", "Κλήρωση κατανομής οικοπέδων"

    community = models.ForeignKey(Community, on_delete=models.PROTECT, related_name="lotteries")
    submission_cycle = models.ForeignKey(
        SubmissionCycle, on_delete=models.PROTECT, related_name="lotteries"
    )
    lottery_type = models.CharField(max_length=32, choices=LotteryType.choices)
    lottery_date = models.DateField()
    location = models.CharField(max_length=255)
    comments = models.TextField(blank=True)


class Allocation(AuditedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ενεργή"
        CANCELLED = "cancelled", "Ακυρώθηκε"

    lottery = models.ForeignKey(
        Lottery, on_delete=models.SET_NULL, null=True, blank=True, related_name="allocations"
    )
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="allocations")
    parcel = models.ForeignKey(Parcel, on_delete=models.PROTECT, related_name="allocations")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    cancellation_reason = models.TextField(blank=True)
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-allocated_at", "-id")


class Payment(AuditedModel):
    class Status(models.TextChoices):
        PAID = "paid", "ΠΛΗΡΩΘΗΚΕ"
        PENDING = "pending", "ΕΚΚΡΕΜΕΙ"

    allocation = models.OneToOneField(Allocation, on_delete=models.CASCADE, related_name="payment")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    comments = models.TextField(blank=True)


class Agreement(AuditedModel):
    class Status(models.TextChoices):
        SIGNED = "signed", "ΥΠΟΓΡΑΦΗΚΕ"
        NOT_SIGNED = "not_signed", "ΔΕΝ ΥΠΟΓΡΑΦΗΚΕ"

    allocation = models.OneToOneField(Allocation, on_delete=models.CASCADE, related_name="agreement")
    signed_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_SIGNED)
    template_version = models.CharField(max_length=64, blank=True)
    comments = models.TextField(blank=True)


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
