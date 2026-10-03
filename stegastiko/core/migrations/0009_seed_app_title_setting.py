from django.db import migrations


def seed_app_title_setting(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    SystemSetting.objects.update_or_create(
        key="appTitle",
        defaults={
            "value": "Στεγαστικό Σχέδιο",
            "description": "Τίτλος εφαρμογής (κεφαλίδα, πάνω αριστερά)",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_reminderread"),
    ]

    operations = [
        migrations.RunPython(seed_app_title_setting, migrations.RunPython.noop),
    ]
