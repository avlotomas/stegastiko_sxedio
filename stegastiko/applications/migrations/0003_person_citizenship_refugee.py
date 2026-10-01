from django.db import migrations, models


def copy_citizenship_from_applications(apps, schema_editor):
    Application = apps.get_model("applications", "Application")
    Person = apps.get_model("applications", "Person")
    for app in Application.objects.select_related("person", "person2").iterator():
        if getattr(app, "person1_citizenship_cypriot", False) and app.person_id:
            person = Person.objects.get(pk=app.person_id)
            person.citizenship_cypriot = True
            person.save(update_fields=["citizenship_cypriot"])
        if getattr(app, "person2_citizenship_cypriot", False) and app.person2_id:
            person2 = Person.objects.get(pk=app.person2_id)
            person2.citizenship_cypriot = True
            person2.save(update_fields=["citizenship_cypriot"])


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0002_application_children_income_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="citizenship_cypriot",
            field=models.BooleanField(
                default=False, help_text="10.3.1 Υπηκοότητα — Κύπριος Πολίτης"
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="citizenship_eu",
            field=models.BooleanField(
                default=False, help_text="10.3.1 Υπηκοότητα — Πολίτης κράτους μέλους ΕΕ"
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="citizenship_other",
            field=models.CharField(
                blank=True,
                help_text="10.3.1 Άλλη υπηκοότητα (κείμενο)",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="citizenship_repatriated",
            field=models.BooleanField(
                default=False,
                help_text="10.3.1 Υπηκοότητα — Επαναπατρισθείς/είσα Κύπριος/α"
            ),
        ),
        migrations.AddField(
            model_name="person",
            name="refugee_identity_number",
            field=models.CharField(
                blank=True,
                help_text="10.3.1 Αρ. Προσφυγικής Ταυτότητας (εκτοπισθέντες)",
                max_length=64,
            ),
        ),
        migrations.RunPython(copy_citizenship_from_applications, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="application",
            name="person1_citizenship_cypriot",
        ),
        migrations.RemoveField(
            model_name="application",
            name="person2_citizenship_cypriot",
        ),
    ]
