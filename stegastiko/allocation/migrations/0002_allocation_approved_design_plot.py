"""Step 1/3 of repointing Allocation.parcel from cases.Parcel to cases.ApprovedDesignPlot.

The repoint used to be one migration mixing schema changes with a RunPython data update,
which PostgreSQL rejects ("cannot ALTER TABLE ... because it has pending trigger events").
It is now split into:

* 0002 (this file) - schema: add the nullable ``approved_design_plot`` FK and make the old
  ``parcel`` FK nullable (so 0003/0004 can be reversed with rows present);
* 0003 - data: fill ``approved_design_plot`` from ``ApprovedDesignPlot.legacy_parcel_id``;
* 0004 - schema: drop the old FK, rename the new one to ``parcel`` and make it NOT NULL.

Databases that applied the former monolithic 0002 are already in the final shape; 0003 and
0004 detect that (no ``approved_design_plot_id`` column) and only update migration state.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0001_initial"),
        ("cases", "0024_merge_parcel_into_approved_design_plot"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocation",
            name="approved_design_plot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="cases.approveddesignplot",
            ),
        ),
        migrations.AlterField(
            model_name="allocation",
            name="parcel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="cases.parcel",
            ),
        ),
    ]
