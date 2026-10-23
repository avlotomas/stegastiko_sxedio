from django.db import migrations


class Migration(migrations.Migration):
    """Removes the old citizen application; only the Person registry stays in this app."""

    dependencies = [
        ("applications", "0005_application_community"),
        ("allocation", "0009_application_to_plot_application"),
    ]

    operations = [
        migrations.DeleteModel(name="CommitteeDecision"),
        migrations.DeleteModel(name="DependentChild"),
        migrations.DeleteModel(name="EligibilityCheck"),
        migrations.DeleteModel(name="Objection"),
        migrations.DeleteModel(name="SupportingDocument"),
        migrations.DeleteModel(name="Application"),
    ]
