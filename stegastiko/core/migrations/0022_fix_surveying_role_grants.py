from django.db import migrations


def fix_surveying_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = {
            grant.replace("case_section_8_plots:", "case_section_8:")
            for grant in role.grants
        }
        role.grants = sorted(grants)
        role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0021_renumber_surveying_and_announcement"),
    ]

    operations = [
        migrations.RunPython(fix_surveying_grants, migrations.RunPython.noop),
    ]
