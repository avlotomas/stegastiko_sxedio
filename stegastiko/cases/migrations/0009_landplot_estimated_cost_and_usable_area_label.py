from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0008_remove_landplot_access_road_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="landplot",
            name="estimated_cost",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="4.1 Εκτιμώμενο κόστος",
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="landplot",
            name="usable_area_sqm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="4.1 Αξιοποιήσιμο εμβαδόν γης (τ.μ.)",
                max_digits=12,
                null=True,
            ),
        ),
    ]
