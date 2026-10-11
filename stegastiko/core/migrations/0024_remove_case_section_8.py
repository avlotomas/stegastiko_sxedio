from django.db import migrations


def remove_case_section_8(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    SystemSetting = apps.get_model("core", "SystemSetting")

    for role in Role.objects.all():
        updated_grants = [g for g in role.grants if not g.startswith("case_section_8:")]
        if updated_grants != role.grants:
            role.grants = updated_grants
            role.save(update_fields=["grants"])

    for role in Role.objects.filter(name="Τεχνικός λειτουργός"):
        role.description = role.description.replace("(7.1–7.6)", "(7.1–7.7)")
        role.save(update_fields=["description"])

    SystemSetting.objects.filter(
        key__in=[
            "caseSectionLabel.8",
            "caseSubsectionLabel.8.1",
            "caseSubsectionLabel.8.2",
            "caseSubsectionLabel.8.2-fields",
            "caseSubsectionLabel.8.2-referrals",
            "caseSubsectionLabel.8.3",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_grant_section_delete"),
    ]

    operations = [
        migrations.RunPython(remove_case_section_8, migrations.RunPython.noop),
    ]
