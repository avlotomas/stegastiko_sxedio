from django.db import migrations, models


def restore_community(apps, schema_editor):
    """Reverse only: give each announcement back the first of its communities."""
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for cycle in SubmissionCycle.objects.all():
        first = cycle.communities.order_by("pk").first()
        if first is not None:
            cycle.community_id = first.pk
            cycle.save(update_fields=["community"])


class Migration(migrations.Migration):
    """The single community goes away once applications and allocation no longer read it."""

    dependencies = [
        ("cases", "0037_submissioncycle_communities"),
        ("applications", "0005_application_community"),
        ("plot_applications", "0002_plotapplication_community"),
        ("allocation", "0008_rankinglist_unique_community"),
        ("plots", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, restore_community),
        migrations.RemoveField(model_name="submissioncycle", name="community"),
        migrations.AlterField(
            model_name="submissioncycle",
            name="plots",
            field=models.ManyToManyField(
                blank=True,
                help_text="9.1 Διαθέσιμα οικόπεδα των Κοινοτήτων που προσφέρει η γνωστοποίηση",
                related_name="submission_cycles",
                to="plots.plot",
            ),
        ),
        migrations.AlterField(
            model_name="submissioncycle",
            name="communities",
            field=models.ManyToManyField(
                help_text="9.1 Κοινότητες / Δ.Δ. που καλύπτει η γνωστοποίηση (της ίδιας Επαρχίας, Ενότ. 4)",
                related_name="submission_cycles",
                to="core.community",
            ),
        ),
    ]
