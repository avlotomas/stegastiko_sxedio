"""Οικόπεδα: completed plots, produced by a finished division case or entered by hand.

During a case its plots are rows of 7.3 (ApprovedDesignPlot). Completing the case copies
every «Υπό διαχωρισμό οικόπεδο» row into this table; the other row types are not plots.
"""

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from cases.models import ApprovedDesignPlot, Case, DisposalPriceMixin, YesNo
from core.models import AuditedModel, Community

SECTION_REF = "plots"

# Data fields shared with ApprovedDesignPlot; completing a case copies them over.
COPIED_FIELDS = (
    "field",
    "valuation_referral",
    "design_number",
    "tkx_number",
    "title_deed_number",
    "parcel_number",
    "sheet_plan",
    "final_area_sqm",
    "owner",
    "lot_number_in_field",
    "kotsiani_number",
    "has_separate_title",
    "valuation_amount",
    "disposal_price",
    "comments",
    "numbering_status",
)


class PlotQuerySet(AuditedModel.AuditedQuerySet):
    def available(self):
        """Plots an announcement may offer: value and price recorded, not in an active announcement, and no active allocation."""
        from cases.models import SubmissionCycle

        return (
            self.filter(valuation_amount__isnull=False, disposal_price__isnull=False)
            .exclude(submission_cycles__stage__in=SubmissionCycle.ACTIVE_STAGES)
            .exclude(allocations__status="active")
        )


class PlotManager(AuditedModel.AuditedManager):
    def get_queryset(self):
        return PlotQuerySet(self.model, using=self._db)

    def available(self):
        return self.get_queryset().available()


class Plot(DisposalPriceMixin, AuditedModel):
    NumberingStatus = ApprovedDesignPlot.NumberingStatus

    community = models.ForeignKey(
        Community, on_delete=models.PROTECT, related_name="plots", help_text="Κοινότητα"
    )
    source_case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plots",
        help_text="Αίτηση διαχωρισμού από την οποία προήλθε (κενό: χειροκίνητη καταχώριση)",
    )
    # Unique: one 7.3 row can never produce a second plot, however often the case completes.
    source_design_plot = models.OneToOneField(
        ApprovedDesignPlot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plot",
        help_text="7.3 Γραμμή εγκεκριμένου σχεδιασμού από την οποία προήλθε",
    )
    field = models.ForeignKey(
        "cases.Field",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plots",
        help_text="8.2 Χωράφι προέλευσης (προαιρετικό)",
    )
    valuation_referral = models.ForeignKey(
        "cases.ValuationReferral",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plots",
        help_text="8.2 Παραπομπή προς Διευθυντή ΤΚΧ που καθόρισε την αξία",
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
    owner = models.ForeignKey(
        "applications.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_plots",
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

    objects = PlotManager()

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return self.row_label

    @property
    def number(self):
        return self.title_deed_number or self.tkx_number or self.design_number

    @property
    def row_label(self):
        return f"Οικόπεδο {self.number}" if self.number else f"Οικόπεδο #{self.pk or '—'}"

    @property
    def is_manual(self):
        return self.source_case_id is None

    @property
    def is_allocated(self):
        """Whether an active allocation (Ενότητα 10+) already points at this plot."""
        if not self.pk:
            return False
        if "allocations" in getattr(self, "_prefetched_objects_cache", {}):
            return any(a.status == "active" for a in self.allocations.all())
        return self.allocations.filter(status="active").exists()

    @property
    def is_valued(self) -> bool:
        """Whether both valuation amount and disposal price have been recorded (8.2)."""
        return self.valuation_amount is not None and self.disposal_price is not None

    @property
    def active_announcement(self):
        """The active announcement (`SubmissionCycle`) currently offering this plot, or None."""
        if not self.pk:
            return None
        from cases.models import SubmissionCycle

        if "submission_cycles" in getattr(self, "_prefetched_objects_cache", {}):
            active = [
                c
                for c in self.submission_cycles.all()
                if c.stage in SubmissionCycle.ACTIVE_STAGES
            ]
            active.sort(key=lambda c: (c.announcement_date, c.pk or 0), reverse=True)
            return active[0] if active else None
        return (
            self.submission_cycles.filter(stage__in=SubmissionCycle.ACTIVE_STAGES)
            .order_by("-announcement_date", "-id")
            .first()
        )

    @property
    def is_in_active_announcement(self) -> bool:
        """Whether this plot is currently tied to an uncompleted announcement."""
        return self.active_announcement is not None

    @property
    def is_available_for_announcement(self) -> bool:
        """Whether this plot can be included in a new announcement (`Plot.objects.available()`)."""
        if not self.pk:
            return False
        return (
            self.is_valued
            and not self.is_allocated
            and not self.is_in_active_announcement
        )

    @property
    def announcement_unavailability_reason(self) -> str:
        """Reason why the plot is not available for a new announcement (empty if available)."""
        if self.is_available_for_announcement:
            return ""
        if self.is_allocated:
            return "Έχει κατανομή"
        if self.is_in_active_announcement:
            return "Σε ενεργή γνωστοποίηση"
        return "Εκκρεμεί αξία/τιμή διάθεσης"

    def copy_from(self, design_plot) -> list:
        """Take over the 7.3 data of `design_plot`; returns the names of the changed fields."""
        changed = []
        for name in COPIED_FIELDS:
            attname = self._meta.get_field(name).attname
            value = getattr(design_plot, attname)
            if getattr(self, attname) != value:
                setattr(self, attname, value)
                changed.append(name)
        return changed

    def save(self, *args, **kwargs):
        self.apply_default_disposal_price()
        if kwargs.get("update_fields") is not None and "valuation_amount" in kwargs["update_fields"]:
            kwargs["update_fields"] = {*kwargs["update_fields"], "disposal_price"}
        result = super().save(*args, **kwargs)
        self.remember_disposal_price_inputs()
        return result

    def _audit_context(self):
        # Plots of a case also show up in that case's folder history.
        return self.source_case_id, None, getattr(self, "_section_ref", SECTION_REF)


def generated_plot(design_plot):
    """The Plot a 7.3 row produced when its case was completed, or None."""
    if not design_plot.pk:
        return None
    try:
        return design_plot.plot
    except ObjectDoesNotExist:
        return None
