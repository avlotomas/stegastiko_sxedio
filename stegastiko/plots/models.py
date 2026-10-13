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
        """Plots an announcement may offer: value and price recorded, no active allocation."""
        return self.filter(
            valuation_amount__isnull=False, disposal_price__isnull=False
        ).exclude(allocations__status="active")


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
        """Whether an allocation (Ενότητα 10+) already points at this plot."""
        if not self.pk:
            return False
        return self.allocations.exists()

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
