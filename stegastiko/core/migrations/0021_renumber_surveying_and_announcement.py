from django.db import migrations


SECTION_KEYS = {
    "caseSectionLabel.8": "caseSectionLabel.9",
    "caseSectionLabel.7-plots": "caseSectionLabel.8",
    "caseSubsectionLabel.8.1": "caseSubsectionLabel.9.1",
    "caseSubsectionLabel.8.4": "caseSubsectionLabel.9.4",
    "caseSubsectionLabel.7.8": "caseSubsectionLabel.8.1",
    "caseSubsectionLabel.7.8-parcels": "caseSubsectionLabel.8.2-fields",
    "caseSubsectionLabel.7.8-7.9-mapping": "caseSubsectionLabel.8.2",
    "caseSubsectionLabel.7.9.1": "caseSubsectionLabel.8.2-referrals",
    "caseSubsectionLabel.7.9.2": "caseSubsectionLabel.8.3",
}


def forwards(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    SystemSetting = apps.get_model("core", "SystemSetting")

    for role in Role.objects.all():
        grants = []
        for grant in role.grants:
            code, separator, action = grant.partition(":")
            code = {
                "case_section_8": "case_section_9",
                "case_section_7_plots": "case_section_8",
                "case_section_8_plots": "case_section_8",
            }.get(code, code)
            grants.append(f"{code}{separator}{action}" if separator else code)
        role.grants = sorted(set(grants))
        role.save(update_fields=["grants"])

    targets_to_replace = []
    for old_key, new_key in SECTION_KEYS.items():
        setting = SystemSetting.objects.filter(key=old_key).first()
        if setting:
            setting.key = f"__renumber__{new_key}"
            setting.save(update_fields=["key"])
            targets_to_replace.append(new_key)
    SystemSetting.objects.filter(key__in=targets_to_replace).delete()
    for new_key in targets_to_replace:
        SystemSetting.objects.filter(key=f"__renumber__{new_key}").update(key=new_key)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_remove_subsection_label_7_7"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
