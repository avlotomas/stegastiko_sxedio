"""Helpers for data migrations that create plots.Plot rows from historical 7.3 rows.

They work on historical models (apps.get_model), so they must not import plots.models.
"""

# Attribute names copied from ApprovedDesignPlot (mirrors plots.models.COPIED_FIELDS).
COPIED_ATTNAMES = (
    "field_id",
    "valuation_referral_id",
    "design_number",
    "tkx_number",
    "title_deed_number",
    "parcel_number",
    "sheet_plan",
    "final_area_sqm",
    "owner_id",
    "lot_number_in_field",
    "kotsiani_number",
    "has_separate_title",
    "valuation_amount",
    "disposal_price",
    "comments",
    "numbering_status",
)


def plot_for_design_plot(apps, design_plot):
    """The Plot of a 7.3 row, created like «Ολοκλήρωση αίτησης» would if it is missing."""
    Plot = apps.get_model("plots", "Plot")
    plot = Plot.objects.filter(source_design_plot_id=design_plot.pk).first()
    if plot is not None:
        return plot
    Case = apps.get_model("cases", "Case")
    case = Case.objects.get(pk=design_plot.case_id)
    plot = Plot(
        community_id=case.community_id,
        source_case_id=case.pk,
        source_design_plot_id=design_plot.pk,
        **{attname: getattr(design_plot, attname) for attname in COPIED_ATTNAMES},
    )
    plot.save()
    return plot
