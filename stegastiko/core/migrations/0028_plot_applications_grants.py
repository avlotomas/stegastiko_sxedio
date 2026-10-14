"""New «Αιτήσεις παραχώρησης οικοπέδου (Παράρτημα 3)» function: granted to the roles that
already hold the matching access on the citizen applications («Αιτήσεις Πολιτών»)."""

from django.db import migrations

MAPPING = {
    "applications:view": "plot_applications:view",
    "applications:create": "plot_applications:create",
    "applications:edit": "plot_applications:edit",
}


def grant(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants)
        updated = grants | {new for old, new in MAPPING.items() if old in grants}
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


def revoke(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        updated = [g for g in role.grants if not g.startswith("plot_applications:")]
        if updated != role.grants:
            role.grants = updated
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0027_persons_grants"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
