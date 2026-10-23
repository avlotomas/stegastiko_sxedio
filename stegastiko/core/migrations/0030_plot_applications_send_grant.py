"""Αποστολή email σε αίτηση παραχώρησης οικοπέδου: ρόλοι με δικαίωμα επεξεργασίας αποκτούν και δικαίωμα αποστολής email."""

from django.db import migrations

EDIT = "plot_applications:edit"
SEND = "plot_applications:send"


def add_send_grant(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        if EDIT in role.grants and SEND not in role.grants:
            role.grants = sorted({*role.grants, SEND})
            role.save(update_fields=["grants"])


def remove_send_grant(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        if SEND in role.grants:
            role.grants = sorted(set(role.grants) - {SEND})
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0029_remove_old_applications_grants"),
    ]

    operations = [
        migrations.RunPython(add_send_grant, remove_send_grant),
    ]
