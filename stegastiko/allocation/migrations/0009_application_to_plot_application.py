import django.db.models.deletion
from django.db import migrations, models


def detach_old_applications(apps, schema_editor):
    """The old citizen applications are being removed.

    Ranking entries only make sense with their application, so they go. Allocations stay (the
    plot remains given away) but lose the link to the removed application.
    """
    apps.get_model("allocation", "RankingEntry").objects.all().delete()
    apps.get_model("allocation", "Allocation").objects.update(application=None)


def restore_placeholder_applications(apps, schema_editor):
    """Reverse: the old application table is empty again, so give each detached allocation a
    placeholder application (the old column is NOT NULL). Without any Person it cannot be built
    and the allocation is dropped."""
    import datetime

    Allocation = apps.get_model("allocation", "Allocation")
    Application = apps.get_model("applications", "Application")
    Person = apps.get_model("applications", "Person")
    person = Person.objects.order_by("pk").first()
    for allocation in Allocation.objects.filter(application__isnull=True).select_related("parcel"):
        if person is None:
            allocation.delete()
            continue
        allocation.application = Application.objects.create(
            community_id=allocation.parcel.community_id,
            person=person,
            folder_number=f"RESTORED-{allocation.pk}",
            submitted_on=datetime.date.today(),
            family_type="other",
            applicant_email="restored@example.invalid",
        )
        allocation.save(update_fields=["application"])


class Migration(migrations.Migration):
    """Ranking entries and allocations now point at the Παράρτημα 3 application."""

    dependencies = [
        ("allocation", "0008_rankinglist_unique_community"),
        ("applications", "0005_application_community"),
        ("plot_applications", "0005_citizenship_two_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="allocation",
            name="application",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="applications.application",
            ),
        ),
        migrations.RunPython(detach_old_applications, restore_placeholder_applications),
        migrations.AlterField(
            model_name="rankingentry",
            name="application",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ranking_entries",
                to="plot_applications.plotapplication",
            ),
        ),
        migrations.AlterField(
            model_name="allocation",
            name="application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="allocations",
                to="plot_applications.plotapplication",
            ),
        ),
    ]
