"""ApprovedDesignPlot.owner becomes a real FK; Case.section8_comments becomes section7_comments.

1. ``owner_person_id`` was a plain integer holding an ``applications.Person`` id. Ids that no
   longer match a Person are nulled first (the FK constraint would reject them), then the
   field becomes ``owner = ForeignKey(Person, SET_NULL)`` keeping the same column
   (``db_column="owner_person_id"``), so stored owners are preserved.
2. ``section8_comments`` holds the «7 Σχόλια / Παρατηρήσεις Ενότητας 7»; it is renamed
   (data preserved).
3. Help texts of Consultation say 7.4 (the division consultations) instead of 8.4.
"""

import django.db.models.deletion
from django.db import migrations, models


def null_dangling_owners(apps, schema_editor):
    ApprovedDesignPlot = apps.get_model("cases", "ApprovedDesignPlot")
    Person = apps.get_model("applications", "Person")
    person_ids = set(Person.objects.values_list("pk", flat=True))
    dangling = [
        plot_id
        for plot_id, owner_id in ApprovedDesignPlot.objects.exclude(
            owner_person_id__isnull=True
        ).values_list("pk", "owner_person_id")
        if owner_id not in person_ids
    ]
    if dangling:
        ApprovedDesignPlot.objects.filter(pk__in=dangling).update(owner_person_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0026_dedupe_approved_design_plots"),
        ("applications", "0003_person_citizenship_refugee"),
    ]

    operations = [
        migrations.RunPython(null_dangling_owners, migrations.RunPython.noop),
        migrations.RenameField(
            model_name="approveddesignplot",
            old_name="owner_person_id",
            new_name="owner",
        ),
        migrations.AlterField(
            model_name="approveddesignplot",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                db_column="owner_person_id",
                help_text="8.2 Ιδιοκτήτης οικοπέδου",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_design_plots",
                to="applications.person",
            ),
        ),
        migrations.RenameField(
            model_name="case",
            old_name="section8_comments",
            new_name="section7_comments",
        ),
        migrations.AlterField(
            model_name='consultation',
            name='comments',
            field=models.TextField(blank=True, help_text='5 / 7.4 Σχόλια'),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='department',
            field=models.CharField(choices=[('tkx', 'Τ.Κ.Χ'), ('tay', 'Τ.Α.Υ'), ('ahk', 'Α.Η.Κ'), ('other', 'Άλλο')], help_text='5 / 7.4 Τμήμα / Υπηρεσία', max_length=16),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='department_other',
            field=models.CharField(blank=True, help_text='5 / 7.4 Περιγραφή όταν Τμήμα / Υπηρεσία = Άλλο', max_length=255),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='due_date',
            field=models.DateField(blank=True, help_text='5 / 7.4 Προθεσμία απάντησης', null=True),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='response_date',
            field=models.DateField(blank=True, help_text='5 / 7.4 Ημ. λήψης απάντησης', null=True),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='response_text',
            field=models.TextField(blank=True, help_text='5 / 7.4 Άποψη / Απάντηση'),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='sent_date',
            field=models.DateField(blank=True, help_text='5 / 7.4 Ημ. αποστολής', null=True),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='stage',
            field=models.CharField(choices=[('suitability', 'Καταλληλότητα'), ('division', 'Κατασκευαστικά σχέδια')], help_text='5 / 7.4 Στάδιο', max_length=16),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='status',
            field=models.CharField(choices=[('pending', 'Εκκρεμεί'), ('received', 'Λήφθηκε'), ('closed', 'Κλείστηκε')], default='pending', help_text='5 / 7.4 Κατάσταση (αυτόματη από την ημ. απάντησης)', max_length=16),
        ),
        migrations.AlterField(
            model_name='consultation',
            name='topic',
            field=models.TextField(blank=True, help_text='5 / 7.4 Θέμα διαβούλευσης'),
        ),
    ]
