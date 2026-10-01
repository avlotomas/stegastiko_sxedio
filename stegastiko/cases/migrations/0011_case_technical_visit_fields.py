from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0010_utility_service_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="case",
            name="engineer_full_name",
            field=models.CharField(
                blank=True, help_text="4.6 Ονοματεπώνυμο μηχανικού", max_length=255
            ),
        ),
        migrations.AddField(
            model_name="case",
            name="technical_visit_date",
            field=models.DateField(blank=True, help_text="4.6 Ημερομηνία επισκεψης", null=True),
        ),
    ]
