"""Υποενότητα «Ιστορικό αλλαγών αίτησης» (plot_app_change_history) στην «Αίτηση παραχώρησης οικοπέδου»:
ρόλοι με δικαίωμα εμφάνισης αποκτούν `plot_app_change_history:view` και ρόλοι με δικαίωμα
επεξεργασίας αποκτούν `plot_app_change_history:edit`."""

from django.db import migrations

VIEW_GRANT = "plot_app_change_history:view"
EDIT_GRANT = "plot_app_change_history:edit"


def add_change_history_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants or ())
        updated = set(grants)
        if "plot_applications:view" in grants:
            updated.add(VIEW_GRANT)
        if "plot_applications:edit" in grants:
            updated.add(EDIT_GRANT)
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


def remove_change_history_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants or ())
        updated = grants - {VIEW_GRANT, EDIT_GRANT}
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_usersecurityprofile"),
    ]

    operations = [
        migrations.RunPython(
            add_change_history_grants,
            remove_change_history_grants,
        ),
    ]
