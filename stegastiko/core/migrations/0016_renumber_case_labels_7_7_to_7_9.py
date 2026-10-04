from django.db import migrations

# Highest numbers first, so a key is free before the next one moves onto it.
SUBSECTION_KEY_MAP = (
    ("caseSubsectionLabel.7.8.2", "caseSubsectionLabel.7.9.2"),
    ("caseSubsectionLabel.7.8.1", "caseSubsectionLabel.7.9.1"),
    ("caseSubsectionLabel.7.7-7.8-mapping", "caseSubsectionLabel.7.8-7.9-mapping"),
    ("caseSubsectionLabel.7.7-parcels", "caseSubsectionLabel.7.8-parcels"),
    ("caseSubsectionLabel.7.7", "caseSubsectionLabel.7.8"),
)

OLD_LABEL_7_5 = "Διαγωνισμός / ανάθεση εργασιών"
SETTING_KEY_7_5 = "caseSubsectionLabel.7.5"
SETTING_KEY_7_7 = "caseSubsectionLabel.7.7"

SECTION_KEY_7_PLOTS = "caseSectionLabel.7-plots"
OLD_LABEL_7_PLOTS = "Οικόπεδα, αξία και τιμή (7.7–7.8)"
NEW_LABEL_7_PLOTS = "Οικόπεδα, αξία και τιμή (7.8–7.9)"

ROLE_TECHNICAL_OFFICER = "Τεχνικός λειτουργός"
OLD_ROLE_DESCRIPTION_PART = "υποδομές διαχωρισμού (7.1–7.6)"
NEW_ROLE_DESCRIPTION_PART = "υποδομές διαχωρισμού (7.1–7.7)"


def _subsection_description(key):
    subsection_key = key.removeprefix("caseSubsectionLabel.")
    return (
        f"Τίτλος εμφάνισης υποενότητας {subsection_key} "
        "(οθόνες επεξεργασίας και προβολή φακέλου)"
    )


def renumber_case_labels(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    Role = apps.get_model("core", "Role")

    def move(setting, new_key):
        for existing in SystemSetting.objects.filter(key=new_key):
            existing.delete()
        setting.key = new_key
        setting.description = _subsection_description(new_key)
        setting.save(update_fields=["key", "description"])

    for old_key, new_key in SUBSECTION_KEY_MAP:
        setting = SystemSetting.objects.filter(key=old_key).first()
        if setting is not None:
            move(setting, new_key)

    # 7.5 is no longer shown; a customised title follows its fields into 7.7.
    setting_7_5 = SystemSetting.objects.filter(key=SETTING_KEY_7_5).first()
    if setting_7_5 is not None:
        if setting_7_5.value == OLD_LABEL_7_5:
            setting_7_5.delete()
        else:
            move(setting_7_5, SETTING_KEY_7_7)

    for setting in SystemSetting.objects.filter(key=SECTION_KEY_7_PLOTS, value=OLD_LABEL_7_PLOTS):
        setting.value = NEW_LABEL_7_PLOTS
        setting.save(update_fields=["value"])

    for role in Role.objects.filter(
        name=ROLE_TECHNICAL_OFFICER, description__contains=OLD_ROLE_DESCRIPTION_PART
    ):
        role.description = role.description.replace(
            OLD_ROLE_DESCRIPTION_PART, NEW_ROLE_DESCRIPTION_PART
        )
        role.save(update_fields=["description"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_update_subsection_label_7_3"),
    ]

    operations = [
        migrations.RunPython(renumber_case_labels, migrations.RunPython.noop),
    ]
