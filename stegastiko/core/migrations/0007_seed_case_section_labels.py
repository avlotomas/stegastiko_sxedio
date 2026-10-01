from django.db import migrations


def seed_case_section_labels(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    labels = {
        "caseSectionLabel.1": "Βασικά στοιχεία και προτεραιότητα",
        "caseSectionLabel.2": "Έλεγχος πληρότητας",
        "caseSectionLabel.3": "Στοιχεία τεμαχίων",
        "caseSectionLabel.4": "Τεχνική αξιολόγηση",
        "caseSectionLabel.5": "Διαβουλεύσεις καταλληλότητας",
        "caseSectionLabel.6": "Απόφαση καταλληλότητας",
        "caseSectionLabel.7": "Σύσταση προς Υπουργό",
        "caseSectionLabel.8": "Διαχωρισμός (8.1–8.6)",
        "caseSectionLabel.8-plots": "Οικόπεδα, αξία και τιμή (8.7–8.8)",
        "caseSectionLabel.9": "Γνωστοποίηση έναρξης αιτήσεων",
    }
    for key, value in labels.items():
        section_key = key.removeprefix("caseSectionLabel.")
        description = f"Τίτλος εμφάνισης Ενότητας {section_key} (πλοήγηση και κεφαλίδα οθόνης)"
        SystemSetting.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_attachment_updated_at_communication_updated_at_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_case_section_labels, migrations.RunPython.noop),
    ]
