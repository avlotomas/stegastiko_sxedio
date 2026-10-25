from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0012_remove_official_use_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="document_notes",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Σημειώσεις ανά πιστοποιητικό/δικαιολογητικό (κωδικός -> σημείωση)",
            ),
        ),
    ]
