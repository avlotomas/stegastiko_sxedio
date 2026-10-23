"""Υποενότητες και διαγραφή στην «Αίτηση παραχώρησης οικοπέδου» (plot_applications):
ρόλοι με δικαίωμα εμφάνισης αποκτούν εμφάνιση όλων των υποενοτήτων και ρόλοι με
δικαίωμα επεξεργασίας αποκτούν διαγραφή και επεξεργασία όλων των υποενοτήτων."""

from django.db import migrations

SUBSECTION_CODES = (
    "basic",
    "section_1",
    "section_2",
    "section_3",
    "section_4",
    "section_5",
    "section_6",
    "section_7",
    "section_8",
    "section_9",
    "section_10",
    "section_11",
    "section_12",
    "sworn_declaration",
    "documents",
    "eligibility",
    "other_applications",
    "email_history",
)

VIEW_SUB_GRANTS = {f"plot_app_{code}:view" for code in SUBSECTION_CODES}
EDIT_SUB_GRANTS = {f"plot_app_{code}:edit" for code in SUBSECTION_CODES}
DELETE_GRANT = "plot_applications:delete"


def add_subsection_and_delete_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants or ())
        updated = set(grants)
        if "plot_applications:view" in grants:
            updated |= VIEW_SUB_GRANTS
        if "plot_applications:edit" in grants:
            updated |= EDIT_SUB_GRANTS
            updated.add(DELETE_GRANT)
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


def remove_subsection_and_delete_grants(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    to_remove = VIEW_SUB_GRANTS | EDIT_SUB_GRANTS | {DELETE_GRANT}
    for role in Role.objects.all():
        grants = set(role.grants or ())
        updated = grants - to_remove
        if updated != grants:
            role.grants = sorted(updated)
            role.save(update_fields=["grants"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0030_plot_applications_send_grant"),
    ]

    operations = [
        migrations.RunPython(
            add_subsection_and_delete_grants,
            remove_subsection_and_delete_grants,
        ),
    ]
