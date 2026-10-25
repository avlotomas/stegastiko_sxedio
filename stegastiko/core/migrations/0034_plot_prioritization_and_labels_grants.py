"""Νέες λειτουργίες «Προτεραιοποίηση αιτήσεων παραχώρησης οικοπέδου» (`plot_prioritization`) και
«Τίτλοι αίτησης παραχώρησης οικοπέδου» (`settings_plot_application_labels`).

- Ρόλοι με εμφάνιση αιτήσεων παραχώρησης αποκτούν προβολή και εξαγωγή PDF του καταλόγου
  προτεραιοποίησης· όσοι έχουν και επεξεργασία αποκτούν αλλαγή σειράς.
- Ρόλοι με πρόσβαση στους τίτλους ενοτήτων Κ.Σ./Δ.Δ. αποκτούν την ίδια πρόσβαση στους τίτλους
  της αίτησης παραχώρησης οικοπέδου.
"""

from django.db import migrations

NEW_PREFIXES = ("plot_prioritization:", "settings_plot_application_labels:")


def grant(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    for role in Role.objects.all():
        grants = set(role.grants or ())
        updated = set(grants)
        if "plot_applications:view" in grants:
            updated |= {"plot_prioritization:view", "plot_prioritization:export"}
            if "plot_applications:edit" in grants:
                updated.add("plot_prioritization:edit")
        for action in ("view", "edit"):
            if f"settings_section_labels:{action}" in grants:
                updated.add(f"settings_plot_application_labels:{action}")
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
        ("core", "0033_plot_app_change_history_grant"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
