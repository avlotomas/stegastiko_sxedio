"""Step 2/3: point each Allocation at the ApprovedDesignPlot that absorbed its Parcel."""

from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError

TABLE = "allocation_allocation"
NEW_COLUMN = "approved_design_plot_id"


def _has_new_column(schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if TABLE not in connection.introspection.table_names(cursor):
            return False
        columns = connection.introspection.get_table_description(cursor, TABLE)
    return any(column.name == NEW_COLUMN for column in columns)


def copy_plot_links(apps, schema_editor):
    # A database that applied the former monolithic 0002 has no approved_design_plot_id
    # column any more: Allocation.parcel already references ApprovedDesignPlot.
    if not _has_new_column(schema_editor):
        return
    Allocation = apps.get_model("allocation", "Allocation")
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    plot_ids = dict(
        ApprovedDesignPlot.objects.exclude(legacy_parcel_id=None).values_list(
            "legacy_parcel_id", "id"
        )
    )
    for allocation in Allocation.objects.exclude(parcel_id=None).iterator():
        try:
            plot_id = plot_ids[allocation.parcel_id]
        except KeyError:
            raise RuntimeError(
                f"Allocation {allocation.pk}: legacy parcel {allocation.parcel_id} has no "
                "ApprovedDesignPlot (cases 0024 should have created or merged one)."
            ) from None
        Allocation.objects.filter(pk=allocation.pk).update(approved_design_plot_id=plot_id)


def restore_parcel_links(apps, schema_editor):
    Allocation = apps.get_model("allocation", "Allocation")
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    parcel_ids = dict(
        ApprovedDesignPlot.objects.exclude(legacy_parcel_id=None).values_list(
            "id", "legacy_parcel_id"
        )
    )
    for allocation in Allocation.objects.exclude(approved_design_plot_id=None).iterator():
        parcel_id = parcel_ids.get(allocation.approved_design_plot_id)
        if parcel_id is None:
            raise IrreversibleError(
                f"Allocation {allocation.pk} points at ApprovedDesignPlot "
                f"{allocation.approved_design_plot_id}, which has no legacy Parcel to point "
                "back to."
            )
        Allocation.objects.filter(pk=allocation.pk).update(parcel_id=parcel_id)


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0002_allocation_approved_design_plot"),
    ]

    operations = [
        migrations.RunPython(copy_plot_links, restore_parcel_links),
    ]
