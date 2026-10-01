import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

DEFAULT_SERVICE_TYPES = (
    "Τηλεπικοινωνίες",
    "ΑΗΚ",
    "Υδατοπρομήθεια",
    "Αποχέτευση",
    "Άλλο",
)
OTHER_SERVICE_TYPE = "Άλλο"


def seed_service_types(apps, schema_editor):
    UtilityServiceType = apps.get_model("cases", "UtilityServiceType")
    for order, name in enumerate(DEFAULT_SERVICE_TYPES, start=1):
        UtilityServiceType.objects.get_or_create(name=name, defaults={"display_order": order})


def link_existing_services(apps, schema_editor):
    """Free-text names become dropdown values; an unknown name is added to the list."""
    UtilityServiceType = apps.get_model("cases", "UtilityServiceType")
    UtilityService = apps.get_model("cases", "UtilityService")
    types_by_name = {item.name.casefold(): item for item in UtilityServiceType.objects.all()}
    next_order = len(types_by_name) + 1
    for service in UtilityService.objects.all():
        name = (service.service_name or "").strip() or OTHER_SERVICE_TYPE
        service_type = types_by_name.get(name.casefold())
        if service_type is None:
            service_type = UtilityServiceType.objects.create(name=name, display_order=next_order)
            types_by_name[name.casefold()] = service_type
            next_order += 1
        service.service_type = service_type
        service.save(update_fields=["service_type"])


def restore_service_names(apps, schema_editor):
    UtilityService = apps.get_model("cases", "UtilityService")
    for service in UtilityService.objects.select_related("service_type"):
        service.service_name = service.service_type.name
        service.save(update_fields=["service_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0009_landplot_estimated_cost_and_usable_area_label"),
    ]

    operations = [
        migrations.CreateModel(
            name="UtilityServiceType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(help_text="4.2 Ονομασία υπηρεσίας", max_length=128, unique=True)),
                ("display_order", models.PositiveIntegerField(default=0, help_text="4.2 Σειρά εμφάνισης")),
                ("is_active", models.BooleanField(default=True, help_text="4.2 Ενεργή (διαθέσιμη για επιλογή)")),
            ],
            options={"ordering": ("display_order", "name")},
        ),
        migrations.RunPython(seed_service_types, migrations.RunPython.noop),
        migrations.AddField(
            model_name="utilityservice",
            name="service_type",
            field=models.ForeignKey(
                help_text="4.2 Υπηρεσία",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="case_services",
                to="cases.utilityservicetype",
            ),
        ),
        migrations.AlterField(
            model_name="utilityservice",
            name="service_name",
            field=models.CharField(blank=True, help_text="4.2 Υπηρεσία", max_length=128),
        ),
        migrations.RunPython(link_existing_services, restore_service_names),
        migrations.RemoveField(model_name="utilityservice", name="service_name"),
        migrations.AlterField(
            model_name="utilityservice",
            name="service_type",
            field=models.ForeignKey(
                help_text="4.2 Υπηρεσία",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="case_services",
                to="cases.utilityservicetype",
            ),
        ),
    ]
