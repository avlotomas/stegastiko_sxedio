from django.db import migrations


class Migration(migrations.Migration):
    """An announcement covers several communities, so a ranking list is unique per community."""

    dependencies = [
        ("allocation", "0007_allocation_parcel_is_plot"),
        ("cases", "0037_submissioncycle_communities"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="rankinglist",
            unique_together={("community", "submission_cycle", "list_type")},
        ),
    ]
