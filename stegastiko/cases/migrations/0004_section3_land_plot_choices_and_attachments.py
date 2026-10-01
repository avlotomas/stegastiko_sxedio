import unicodedata

from django.db import migrations, models

OWNERSHIP_LABELS = {"state_land": "Κρατική γη", "other": "Άλλη ιδιοκτησία"}
ACCESS_LABELS = {
    "public_road": "Πρόσβαση σε εγγεγραμμένο δημόσιο δρόμο",
    "road_required": "Απαιτείται διάνοιξη και εγγραφή δημόσιου δρόμου",
    "other": "Άλλο",
}


def _normalise(text):
    stripped = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in stripped if not unicodedata.combining(ch)).casefold()


def _ownership_choice(text):
    if not (text or "").strip():
        return "", ""
    if "κρατικ" in _normalise(text):
        return "state_land", ""
    return "other", text.strip()


def _access_choice(text):
    if not (text or "").strip():
        return "", ""
    normalised = _normalise(text)
    if "διανοιξ" in normalised:
        return "road_required", ""
    if "εγγεγραμμεν" in normalised or "δημοσιο δρομο" in normalised:
        return "public_road", ""
    return "other", text.strip()


def free_text_to_choices(apps, schema_editor):
    """3.1 Earlier rows held free text and a checkbox; keep their meaning in the new choices."""
    LandPlot = apps.get_model("cases", "LandPlot")
    for plot in LandPlot.objects.all():
        ownership_status, ownership_other = _ownership_choice(plot.ownership_status)
        access, access_other = _access_choice(plot.access)
        LandPlot.objects.filter(pk=plot.pk).update(
            ownership_status=ownership_status,
            ownership_other=ownership_other,
            access=access,
            access_other=access_other,
            inside_development_zone_answer="yes" if plot.inside_development_zone else "no",
        )


def choices_to_free_text(apps, schema_editor):
    LandPlot = apps.get_model("cases", "LandPlot")
    for plot in LandPlot.objects.all():
        ownership = OWNERSHIP_LABELS.get(plot.ownership_status, plot.ownership_status)
        if plot.ownership_other:
            ownership = f"{ownership}: {plot.ownership_other}"
        access = ACCESS_LABELS.get(plot.access, plot.access)
        if plot.access_other:
            access = f"{access}: {plot.access_other}"
        LandPlot.objects.filter(pk=plot.pk).update(
            ownership_status=ownership[:128],
            access=access[:128],
            inside_development_zone=plot.inside_development_zone_answer == "yes",
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0003_alter_submissioncyclepublication_method_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='landplot',
            name='access_other',
            field=models.CharField(blank=True, help_text='3.1 Διευκρίνιση άλλης πρόσβασης', max_length=255),
        ),
        migrations.AddField(
            model_name='landplot',
            name='ownership_other',
            field=models.CharField(blank=True, help_text='3.1 Είδος άλλης ιδιοκτησίας', max_length=255),
        ),
        migrations.AddField(
            model_name='landplot',
            name='inside_development_zone_answer',
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.RunPython(free_text_to_choices, choices_to_free_text),
        migrations.RemoveField(
            model_name='landplot',
            name='inside_development_zone',
        ),
        migrations.RenameField(
            model_name='landplot',
            old_name='inside_development_zone_answer',
            new_name='inside_development_zone',
        ),
        migrations.AlterField(
            model_name='landplot',
            name='inside_development_zone',
            field=models.CharField(blank=True, choices=[('yes', 'ΝΑΙ'), ('no', 'ΟΧΙ')], help_text='3.1 Εντός Ορίου Ανάπτυξης', max_length=8),
        ),
        migrations.AlterField(
            model_name='landplot',
            name='access',
            field=models.CharField(blank=True, choices=[('public_road', 'Πρόσβαση σε εγγεγραμμένο δημόσιο δρόμο'), ('road_required', 'Απαιτείται διάνοιξη και εγγραφή δημόσιου δρόμου'), ('other', 'Άλλο')], help_text='3.1 Πρόσβαση', max_length=16),
        ),
        migrations.AlterField(
            model_name='landplot',
            name='ownership_status',
            field=models.CharField(blank=True, choices=[('state_land', 'Κρατική γη'), ('other', 'Άλλη ιδιοκτησία')], help_text='3.1 Ιδιοκτησιακό καθεστώς', max_length=16),
        ),
        migrations.AlterField(
            model_name='landplot',
            name='comments',
            field=models.TextField(blank=True, help_text='3.1 Σχόλια / Παρατηρήσεις'),
        ),
        migrations.AlterField(
            model_name='case',
            name='contact_email',
            field=models.EmailField(help_text='1.1 Ηλεκτρονική διεύθυνση επικοινωνίας Κ.Σ./Δ.Δ.', max_length=254),
        ),
        migrations.AlterField(
            model_name='case',
            name='priority_documentation',
            field=models.TextField(blank=True, help_text='1.2 Στοιχεία τεκμηρίωσης των επιλεγμένων χαρακτηριστικών'),
        ),
        migrations.AlterField(
            model_name='case',
            name='section3_comments',
            field=models.TextField(blank=True, help_text='3.3 Σχόλια / Παρατηρήσεις Ενότητας 3'),
        ),
        migrations.AlterField(
            model_name='case',
            name='state_land_comments',
            field=models.TextField(blank=True, help_text='3.2 Σχόλια / Παρατηρήσεις'),
        ),
        migrations.AlterField(
            model_name='case',
            name='state_land_remains_sufficient',
            field=models.CharField(blank=True, choices=[('yes', 'ΝΑΙ'), ('no', 'ΟΧΙ')], help_text='3.2 Μετά την προτεινόμενη αξιοποίηση θα παραμένουν στην Κοινότητα ικανοποιητικές εκτάσεις κρατικής γης;', max_length=8),
        ),
    ]
