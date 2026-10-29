from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0019_rejected_incomplete_stage"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="plotapplication",
            name="priority_primary",
        ),
        migrations.RemoveField(
            model_name="plotapplication",
            name="priority_secondary",
        ),
        migrations.RemoveField(
            model_name="plotapplication",
            name="priority_label",
        ),
    ]
