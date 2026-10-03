from django.db import migrations

# The menu labels page belongs with «Εμφάνιση εφαρμογής»: roles keep the same access to both.
SOURCE = "settings_branding"
TARGET = "settings_menu_labels"


def grant_menu_labels(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants)
        added = {
            f"{TARGET}:{key.split(':', 1)[1]}" for key in grants if key.split(":", 1)[0] == SOURCE
        }
        if added - grants:
            role.grants = sorted(grants | added)
            role.save(update_fields=["grants"])


def revoke_menu_labels(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        kept = [key for key in role.grants if not key.startswith(f"{TARGET}:")]
        if kept != role.grants:
            role.grants = kept
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):

    dependencies = [("core", "0011_seed_default_roles")]

    operations = [migrations.RunPython(grant_menu_labels, revoke_menu_labels)]
