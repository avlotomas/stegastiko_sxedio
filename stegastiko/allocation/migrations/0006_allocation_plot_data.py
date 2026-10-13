"""Step 2/3: every allocated 7.3 row gets its Plot and the allocation points at it."""

from django.db import migrations

from plots.migration_helpers import plot_for_design_plot


def point_allocations_at_plots(apps, schema_editor):
    Allocation = apps.get_model("allocation", "Allocation")
    for allocation in Allocation.objects.filter(plot__isnull=True).select_related("parcel"):
        allocation.plot = plot_for_design_plot(apps, allocation.parcel)
        allocation.save(update_fields=["plot"])


def point_allocations_at_design_plots(apps, schema_editor):
    Allocation = apps.get_model("allocation", "Allocation")
    for allocation in Allocation.objects.select_related("plot"):
        if allocation.plot.source_design_plot_id is None:
            raise RuntimeError(
                f"Allocation {allocation.pk} points at a manually entered plot; it cannot be "
                "moved back to a 7.3 row."
            )
        allocation.parcel_id = allocation.plot.source_design_plot_id
        allocation.save(update_fields=["parcel"])


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0005_allocation_plot"),
    ]

    operations = [
        migrations.RunPython(point_allocations_at_plots, point_allocations_at_design_plots),
    ]
