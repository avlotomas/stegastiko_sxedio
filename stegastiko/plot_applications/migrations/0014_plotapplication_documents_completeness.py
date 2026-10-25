from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plot_applications", "0013_plotapplication_document_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotapplication",
            name="documents_complete_override",
            field=models.BooleanField(
                default=False,
                help_text="Χειροκίνητος χαρακτηρισμός της αίτησης ως ολοκληρωμένης ως προς τα δικαιολογητικά παρά τις ελλείψεις (Ενότ. 5, 20.2)",
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="documents_complete_reason",
            field=models.TextField(
                blank=True,
                help_text="Περιγραφή του λόγου για τον οποίο η αίτηση χαρακτηρίζεται ως ολοκληρωμένη ενώ λείπουν δικαιολογητικά (Ενότ. 5, 20.2)",
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="documents_completeness",
            field=models.CharField(
                choices=[("complete", "Ολοκληρωμένη"), ("incomplete", "Ελλιπής")],
                default="incomplete",
                help_text="Κατάσταση πληρότητας απαιτούμενων δικαιολογητικών (Ενότ. 5, 20.2)",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="completeness_result",
            field=models.CharField(
                choices=[("complete", "Πλήρης"), ("incomplete", "Ελλιπής")],
                default="incomplete",
                help_text="Κατάσταση πληρότητας της αίτησης (υποχρεωτικά πεδία, υπογραφές, δικαιολογητικά, Ενότ. 5, 20.2)",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="plotapplication",
            name="completeness_details",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
