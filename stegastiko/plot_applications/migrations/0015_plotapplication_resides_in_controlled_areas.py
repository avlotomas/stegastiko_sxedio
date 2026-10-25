from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0014_plotapplication_documents_completeness"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="resides_in_controlled_areas",
            field=models.BooleanField(
                default=False,
                help_text="Διαμένει σε ελεγχόμενες από την Κυπριακή Δημοκρατία περιοχές (Ενότ. 11.ΙΙΙ)",
            ),
        ),
    ]
