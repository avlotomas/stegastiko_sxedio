from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0006_remove_previous_residence_dates"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="plotapplication",
            name="community_residence_since",
        ),
        migrations.RemoveField(
            model_name="plotapplication",
            name="abroad_from",
        ),
        migrations.RemoveField(
            model_name="plotapplication",
            name="abroad_to",
        ),
    ]
