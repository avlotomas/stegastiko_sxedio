import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0029_remove_case_section7_comments"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="case",
            name="completed_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text="Ολοκλήρωση αίτησης: δημιουργία των οικοπέδων στον πίνακα «Οικόπεδα»",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="case",
            name="completed_by",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                help_text="Χρήστης που ολοκλήρωσε την αίτηση",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
