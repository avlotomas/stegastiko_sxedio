"""New «Άτομα» function: viewers of citizen applications see the persons table and the
roles that edit applications may add, change and delete persons."""

from django.db import migrations

FULL = ("persons:view", "persons:create", "persons:edit", "persons:delete")


def grant_persons(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants)
        updated = set(grants)
        if "applications:view" in grants:
            updated.add("persons:view")
        if "applications:edit" in grants:
            updated.update(FULL)
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


def revoke_persons(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        updated = [g for g in role.grants if not g.startswith("persons:")]
        if updated != role.grants:
            role.grants = updated
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_case_section_3_send_grant"),
    ]

    operations = [migrations.RunPython(grant_persons, revoke_persons)]
