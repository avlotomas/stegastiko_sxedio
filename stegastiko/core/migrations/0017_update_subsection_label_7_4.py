from django.db import migrations

OLD_LABEL_7_4 = "Διαβουλεύσεις κατά τον διαχωρισμό"
NEW_LABEL_7_4 = "Κατασκευαστικά Σχέδια και Διαβουλεύσεις"
SETTING_KEY = "caseSubsectionLabel.7.4"


def rename_subsection_label_7_4(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    for setting in SystemSetting.objects.filter(key=SETTING_KEY, value=OLD_LABEL_7_4):
        setting.value = NEW_LABEL_7_4
        setting.save(update_fields=["value"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_renumber_case_labels_7_7_to_7_9"),
    ]

    operations = [
        migrations.RunPython(rename_subsection_label_7_4, migrations.RunPython.noop),
    ]
