"""3.1 emails per land plot: roles that edit Ενότητα 3 may also send its emails."""

from django.db import migrations

EDIT = "case_section_3:edit"
SEND = "case_section_3:send"


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
        ("core", "0025_plots_and_announcements_grants"),
    ]

    operations = [
        migrations.RunPython(add_send_grant, remove_send_grant),
    ]
