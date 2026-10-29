from django.db import migrations

NEW_PREFIXES = (
    "announcement_committee:",
    "announcement_objections:",
    "announcement_lottery:",
    "announcement_agreements:",
    "settings_agreement_templates:",
)


def grant(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants or ())
        updated = set(grants)
        if "announcements:view" in grants:
            updated |= {
                "announcement_committee:view",
                "announcement_objections:view",
                "announcement_lottery:view",
                "announcement_agreements:view",
                "announcement_agreements:export",
            }
            if "announcements:edit" in grants or "plot_prioritization:edit" in grants:
                updated |= {
                    "announcement_committee:edit",
                    "announcement_committee:send",
                    "announcement_objections:edit",
                    "announcement_objections:send",
                    "announcement_lottery:edit",
                    "announcement_lottery:send",
                    "announcement_agreements:edit",
                    "announcement_agreements:send",
                }
        if "settings_workflow:view" in grants:
            updated.add("settings_agreement_templates:view")
        if "settings_workflow:edit" in grants:
            updated |= {
                "settings_agreement_templates:edit",
                "settings_agreement_templates:import",
            }
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


def revoke(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        kept = [key for key in role.grants or () if not key.startswith(NEW_PREFIXES)]
        if kept != list(role.grants or ()):
            role.grants = kept
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0034_plot_prioritization_and_labels_grants"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
