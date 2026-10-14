import django.db.models.deletion
from django.db import migrations, models


def copy_community(apps, schema_editor):
    Application = apps.get_model("applications", "Application")
    for application in Application.objects.select_related("submission_cycle"):
        application.community_id = application.submission_cycle.community_id
        application.save(update_fields=["community"])


def restore_cycle(apps, schema_editor):
    """Reverse only: point each row at the first announcement covering its community."""
    Application = apps.get_model("applications", "Application")
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for row in Application.objects.all():
        cycle = SubmissionCycle.objects.filter(communities=row.community_id).order_by("pk").first()
        if cycle is not None:
            row.submission_cycle_id = cycle.pk
            row.save(update_fields=["submission_cycle"])


class Migration(migrations.Migration):
    """An application records its community, not the announcement."""

    dependencies = [
        ("core", "0028_plot_applications_grants"),
        ("cases", "0037_submissioncycle_communities"),
        ("applications", "0004_application_citizenship_refugee"),
    ]

    operations = [
        migrations.AddField(
            model_name="application",
            name="community",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="core.community",
            ),
        ),
        migrations.AlterField(
            model_name="application",
            name="submission_cycle",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="cases.submissioncycle",
            ),
        ),
        migrations.RunPython(copy_community, restore_cycle),
        migrations.AlterField(
            model_name="application",
            name="community",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="core.community",
            ),
        ),
        migrations.RemoveField(model_name="application", name="submission_cycle"),
    ]
