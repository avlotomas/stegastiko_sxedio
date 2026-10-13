"""Ενότητα 9 leaves the case: its grants move to the stand-alone «Γνωστοποιήσεις» function.

New functions: «Οικόπεδα» (completed plots) and «Ολοκλήρωση αίτησης» under the cases.
  * announcements:<x>        <- case_section_9:<x>
  * plots:view               <- cases:view
  * plots:create/edit/delete <- case_section_9:create (roles that entered announcements)
  * case_completion:view     <- case_section_7:view
  * case_completion:edit     <- case_section_9:publish (roles that issued announcements)
"""

from django.db import migrations

OLD = "case_section_9"


def move_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    SystemSetting = apps.get_model("core", "SystemSetting")
    for role in Role.objects.all():
        grants = set(role.grants)
        updated = {g for g in grants if not g.startswith(f"{OLD}:")}
        updated |= {f"announcements:{g.split(':', 1)[1]}" for g in grants if g.startswith(f"{OLD}:")}
        if "cases:view" in grants:
            updated.add("plots:view")
        if f"{OLD}:create" in grants:
            updated |= {"plots:view", "plots:create", "plots:edit", "plots:delete"}
        if "case_section_7:view" in grants:
            updated.add("case_completion:view")
        if f"{OLD}:publish" in grants:
            updated |= {"case_completion:view", "case_completion:edit"}
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])

    SystemSetting.objects.filter(
        key__in=["caseSectionLabel.9", "caseSubsectionLabel.9.1", "caseSubsectionLabel.9.4"]
    ).delete()


def restore_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants)
        updated = {
            g for g in grants if g.split(":", 1)[0] not in {"announcements", "plots", "case_completion"}
        }
        updated |= {f"{OLD}:{g.split(':', 1)[1]}" for g in grants if g.startswith("announcements:")}
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_remove_case_section_8"),
    ]

    operations = [
        migrations.RunPython(move_grants, restore_grants),
    ]
