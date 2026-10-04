from django.db import migrations

OLD_LABEL_6_2 = "Συνοπτικός πίνακας τεμαχίων"
NEW_LABEL_6_2 = "Τεχνική αξιολόγηση ανά τεμάχιο"
SETTING_KEY = "caseSubsectionLabel.6.2"


def rename_subsection_label_6_2(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    SystemSetting.objects.filter(key=SETTING_KEY, value=OLD_LABEL_6_2).update(value=NEW_LABEL_6_2)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_grant_menu_labels"),
    ]

    operations = [
        migrations.RunPython(rename_subsection_label_6_2, migrations.RunPython.noop),
    ]
