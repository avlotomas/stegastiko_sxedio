"""The old citizen application («Αιτήσεις Πολιτών») and its Excel import were removed:
drop their function grants from every role. Only «Αιτήσεις παραχώρησης οικοπέδου» remains."""

from django.db import migrations

REMOVED_PREFIXES = ("applications:", "application_import:")


def revoke_removed(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        kept = [g for g in role.grants if not g.startswith(REMOVED_PREFIXES)]
        if kept != role.grants:
            role.grants = kept
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0028_plot_applications_grants"),
    ]

    operations = [migrations.RunPython(revoke_removed, migrations.RunPython.noop)]
