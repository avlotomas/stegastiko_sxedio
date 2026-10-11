from django.db import migrations

# Delete views of sections 6-8 now require «Διαγραφή» instead of «Επεξεργασία»;
# roles that could edit these sections keep the ability to delete their rows.
SECTIONS = ("case_section_6", "case_section_7", "case_section_8")


def grant_section_delete(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants)
        added = {f"{code}:delete" for code in SECTIONS if f"{code}:edit" in grants}
        if added - grants:
            role.grants = sorted(grants | added)
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0022_fix_surveying_role_grants"),
    ]

    operations = [
        migrations.RunPython(grant_section_delete, migrations.RunPython.noop),
    ]
