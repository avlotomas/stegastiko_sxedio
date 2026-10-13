"""Step 2/3: an existing announcement keeps offering the plots of the cases it covered.

Those cases count as completed: every division plot of theirs gets its Plot, and the
announcement offers the ones that already had a value and price (former 9.1 rule).
"""

from django.db import migrations
from django.utils import timezone

from plots.migration_helpers import plot_for_design_plot

DIVISION_PLOT = "division_plot"


def link_cycles_to_plots(apps, schema_editor):
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    now = timezone.now()
    for cycle in SubmissionCycle.objects.all():
        for case in cycle.cases.all():
            design_plots = ApprovedDesignPlot.objects.filter(case=case, plot_type=DIVISION_PLOT)
            for design_plot in design_plots:
                plot = plot_for_design_plot(apps, design_plot)
                if plot.valuation_amount is not None and plot.disposal_price is not None:
                    cycle.plots.add(plot)
            if case.completed_at is None:
                case.completed_at = now
                case.save(update_fields=["completed_at"])


def link_cycles_to_cases(apps, schema_editor):
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for cycle in SubmissionCycle.objects.all():
        case_ids = {
            plot.source_case_id for plot in cycle.plots.all() if plot.source_case_id is not None
        }
        cycle.cases.add(*case_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0031_submissioncycle_plots"),
    ]

    operations = [
        migrations.RunPython(link_cycles_to_plots, link_cycles_to_cases),
    ]
