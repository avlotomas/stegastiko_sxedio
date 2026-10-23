from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0005_citizenship_two_options"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="plotapplication",
            name="previous_residence_from",
        ),
        migrations.RemoveField(
            model_name="plotapplication",
            name="previous_residence_to",
        ),
    ]
