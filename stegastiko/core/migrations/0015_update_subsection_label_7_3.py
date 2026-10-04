from django.db import migrations

OLD_LABEL_7_3 = "Αίτηση στο ΤΠΟ"
NEW_LABEL_7_3 = "Στοιχεία αίτησης για έγκριση σχεδιασμού"
SETTING_KEY = "caseSubsectionLabel.7.3"


def rename_subsection_label_7_3(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    SystemSetting.objects.filter(key=SETTING_KEY, value=OLD_LABEL_7_3).update(value=NEW_LABEL_7_3)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_renumber_case_labels_7_8"),
    ]

    operations = [
        migrations.RunPython(rename_subsection_label_7_3, migrations.RunPython.noop),
    ]
