from django.db import migrations, models

ROAD_REQUIRED_LABEL = "Απαιτείται διάνοιξη και εγγραφή δημόσιου δρόμου"


def migrate_road_required_to_other(apps, schema_editor):
    LandPlot = apps.get_model("cases", "LandPlot")
    for plot in LandPlot.objects.filter(access="road_required"):
        if not plot.access_other:
            plot.access_other = ROAD_REQUIRED_LABEL
        plot.access = "other"
        plot.save(update_fields=["access", "access_other"])


def migrate_other_back_to_road_required(apps, schema_editor):
    LandPlot = apps.get_model("cases", "LandPlot")
    for plot in LandPlot.objects.filter(access="other", access_other=ROAD_REQUIRED_LABEL):
        plot.access = "road_required"
        plot.access_other = ""
        plot.save(update_fields=["access", "access_other"])


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0007_alter_completenesscheck_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_road_required_to_other,
            migrate_other_back_to_road_required,
        ),
        migrations.AlterField(
            model_name="landplot",
            name="access",
            field=models.CharField(
                blank=True,
                choices=[
                    ("public_road", "Πρόσβαση σε εγγεγραμμένο δημόσιο δρόμο"),
                    ("other", "Άλλο"),
                ],
                help_text="3.1 Πρόσβαση",
                max_length=16,
            ),
        ),
    ]
