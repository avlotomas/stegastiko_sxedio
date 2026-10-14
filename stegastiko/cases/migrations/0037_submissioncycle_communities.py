from django.db import migrations, models


def copy_community(apps, schema_editor):
    SubmissionCycle = apps.get_model("cases", "SubmissionCycle")
    for cycle in SubmissionCycle.objects.all():
        cycle.communities.add(cycle.community_id)


class Migration(migrations.Migration):
    """An announcement covers several communities: add the M2M and copy the single one."""

    dependencies = [
        ("core", "0028_plot_applications_grants"),
        ("cases", "0036_disposal_price_editable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="submissioncycle",
            name="community",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="submission_cycles",
                to="core.community",
            ),
        ),
        migrations.AddField(
            model_name="submissioncycle",
            name="communities",
            field=models.ManyToManyField(
                help_text="9.1 Κοινότητες / Δ.Δ. που καλύπτει η γνωστοποίηση (της ίδιας Επαρχίας, Ενότ. 4)",
                related_name="submission_cycles_m2m",
                to="core.community",
            ),
        ),
        migrations.RunPython(copy_community, migrations.RunPython.noop),
    ]
