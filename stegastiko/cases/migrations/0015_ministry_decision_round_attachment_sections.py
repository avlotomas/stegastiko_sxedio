from django.db import migrations


def migrate_legacy_67_attachments(apps, schema_editor):
    Attachment = apps.get_model("core", "Attachment")
    ContentType = apps.get_model("contenttypes", "ContentType")
    MinistryDecisionRound = apps.get_model("cases", "MinistryDecisionRound")
    content_type = ContentType.objects.get_for_model(MinistryDecisionRound)
    Attachment.objects.filter(
        content_type=content_type,
        section_ref="6.7",
    ).update(section_ref="6.7-rec")


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0014_ministry_decision_round"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_67_attachments, migrations.RunPython.noop),
    ]
