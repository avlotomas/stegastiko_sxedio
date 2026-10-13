"""Step 1/3: allocations move from 7.3 rows (ApprovedDesignPlot) to completed plots."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0004_allocation_parcel_finalize"),
        ("plots", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allocation",
            name="parcel",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="cases.approveddesignplot",
            ),
        ),
        migrations.AddField(
            model_name="allocation",
            name="plot",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="plots.plot",
            ),
        ),
    ]
