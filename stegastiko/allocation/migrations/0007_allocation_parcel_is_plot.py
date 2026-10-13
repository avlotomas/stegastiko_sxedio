"""Step 3/3: drop the 7.3 link; `parcel` is now the completed plot (plots.Plot)."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0006_allocation_plot_data"),
    ]

    operations = [
        migrations.RemoveField(model_name="allocation", name="parcel"),
        migrations.RenameField(model_name="allocation", old_name="plot", new_name="parcel"),
        migrations.AlterField(
            model_name="allocation",
            name="parcel",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="plots.plot",
            ),
        ),
    ]
