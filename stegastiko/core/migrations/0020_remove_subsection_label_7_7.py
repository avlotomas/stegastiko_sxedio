from django.db import migrations

SETTING_KEY_7_7 = "caseSubsectionLabel.7.7"

ROLE_TECHNICAL_OFFICER = "Τεχνικός λειτουργός"
OLD_ROLE_DESCRIPTION_PART = "υποδομές διαχωρισμού (7.1–7.7)"
NEW_ROLE_DESCRIPTION_PART = "υποδομές διαχωρισμού (7.1–7.6)"


def remove_subsection_label_7_7(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    Role = apps.get_model("core", "Role")

    # The 7.7 infrastructure table is now the 7.6 checks table.
    SystemSetting.objects.filter(key=SETTING_KEY_7_7).delete()

    for role in Role.objects.filter(
        name=ROLE_TECHNICAL_OFFICER, description__contains=OLD_ROLE_DESCRIPTION_PART
    ):
        role.description = role.description.replace(
            OLD_ROLE_DESCRIPTION_PART, NEW_ROLE_DESCRIPTION_PART
        )
        role.save(update_fields=["description"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_rename_subsection_labels_7_6_7_7"),
    ]

    operations = [
        migrations.RunPython(remove_subsection_label_7_7, migrations.RunPython.noop),
    ]
