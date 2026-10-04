from django.db import migrations

SETTING_KEY_7_6 = "caseSubsectionLabel.7.6"
SETTING_KEY_7_7 = "caseSubsectionLabel.7.7"

DEFAULT_LABEL_7_6 = "Παρακολουθηση κατασκευαστικων εργασιων"
DEFAULT_LABEL_7_7 = "Έλεγχος υποδομών"


def _subsection_description(key):
    subsection_key = key.removeprefix("caseSubsectionLabel.")
    return (
        f"Τίτλος εμφάνισης υποενότητας {subsection_key} "
        "(οθόνες επεξεργασίας και προβολή φακέλου)"
    )


def rename_subsection_labels_7_6_7_7(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    setting_7_6 = SystemSetting.objects.filter(key=SETTING_KEY_7_6).first()
    setting_7_7 = SystemSetting.objects.filter(key=SETTING_KEY_7_7).first()

    if setting_7_6 is None:
        SystemSetting.objects.create(
            key=SETTING_KEY_7_6,
            value=DEFAULT_LABEL_7_6,
            description=_subsection_description(SETTING_KEY_7_6),
        )
    else:
        setting_7_6.value = DEFAULT_LABEL_7_6
        setting_7_6.description = _subsection_description(SETTING_KEY_7_6)
        setting_7_6.save(update_fields=["value", "description"])

    if setting_7_7 is None:
        SystemSetting.objects.create(
            key=SETTING_KEY_7_7,
            value=DEFAULT_LABEL_7_7,
            description=_subsection_description(SETTING_KEY_7_7),
        )
    else:
        setting_7_7.value = DEFAULT_LABEL_7_7
        setting_7_7.description = _subsection_description(SETTING_KEY_7_7)
        setting_7_7.save(update_fields=["value", "description"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_rename_subsection_labels_7_5_7_7"),
    ]

    operations = [
        migrations.RunPython(rename_subsection_labels_7_6_7_7, migrations.RunPython.noop),
    ]
