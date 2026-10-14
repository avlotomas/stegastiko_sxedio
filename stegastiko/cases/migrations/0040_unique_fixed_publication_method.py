from django.db import migrations, models

FIXED = ("community", "district_office", "district_site", "ministry_site")
LABELS = {
    "community": "Αποστολή/ανάρτηση στην Κοινότητα ή στο Δ.Δ.",
    "district_office": "Έντυπη ανάρτηση στα γραφεία Επαρχιακής Διοίκησης",
    "district_site": "Ιστοσελίδα Επαρχιακής Διοίκησης",
    "ministry_site": "Ιστοσελίδα ΥΠΕΣ",
}


def keep_each_fixed_method_once(apps, schema_editor):
    """A repeated fixed method becomes an «Άλλο» row (nothing is deleted), the earliest stays."""
    Publication = apps.get_model("cases", "SubmissionCyclePublication")
    seen = set()
    for row in Publication.objects.filter(method__in=FIXED).order_by("published_on", "id"):
        key = (row.submission_cycle_id, row.method)
        if key not in seen:
            seen.add(key)
            continue
        row.notes = f"{LABELS[row.method]}. {row.notes}".strip(" .") if row.notes else LABELS[row.method]
        row.method = "other"
        row.save(update_fields=["method", "notes"])


class Migration(migrations.Migration):
    """9.2 The four fixed publication methods occur at most once per announcement."""

    dependencies = [
        ("cases", "0039_submissioncycle_notice_fields"),
    ]

    operations = [
        migrations.RunPython(keep_each_fixed_method_once, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="submissioncyclepublication",
            constraint=models.UniqueConstraint(
                condition=models.Q(("method", "other"), _negated=True),
                fields=("submission_cycle", "method"),
                name="unique_fixed_publication_method_per_cycle",
            ),
        ),
    ]
