import django.db.models.deletion
from django.db import migrations, models


def copy_community(apps, schema_editor):
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    for application in PlotApplication.objects.select_related("submission_cycle"):
        application.community_id = application.submission_cycle.community_id
        application.save(update_fields=["community"])


def restore_cycle(apps, schema_editor):
    """Reverse only: point each row at the first announcement covering its community."""
    PlotApplication = apps.get_model("plot_applications", "PlotApplication")
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for row in PlotApplication.objects.all():
        cycle = SubmissionCycle.objects.filter(communities=row.community_id).order_by("pk").first()
        if cycle is not None:
            row.submission_cycle_id = cycle.pk
            row.save(update_fields=["submission_cycle"])


class Migration(migrations.Migration):
    """A plot application records its community, not the announcement."""

    dependencies = [
        ("core", "0028_plot_applications_grants"),
        ("cases", "0037_submissioncycle_communities"),
        ("plot_applications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="community",
            field=models.ForeignKey(
                help_text="Κοινότητα στην οποία ζητείται η παραχώρηση οικοπέδου (Παράρτημα 3, Ενότ. 5)",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plot_applications",
                to="core.community",
            ),
        ),
        migrations.AlterField(
            model_name="plotapplication",
            name="submission_cycle",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plot_applications",
                to="cases.submissioncycle",
            ),
        ),
        migrations.RunPython(copy_community, restore_cycle),
        migrations.AlterField(
            model_name="plotapplication",
            name="community",
            field=models.ForeignKey(
                help_text="Κοινότητα στην οποία ζητείται η παραχώρηση οικοπέδου (Παράρτημα 3, Ενότ. 5)",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plot_applications",
                to="core.community",
            ),
        ),
        migrations.RemoveField(model_name="plotapplication", name="submission_cycle"),
    ]
