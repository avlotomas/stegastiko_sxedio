from django.db import migrations


SECTION_DEFAULTS = {
    "caseSectionLabel.7": "Σχεδιασμός και υλοποίηση διαχωρισμού",
    "caseSectionLabel.7-plots": "Οικόπεδα, αξία και τιμή (7.7–7.8)",
    "caseSectionLabel.8": "Γνωστοποίηση έναρξης αιτήσεων",
}

# Old section key -> new section key
SECTION_KEY_MAP = {
    "caseSectionLabel.8": "caseSectionLabel.7",
    "caseSectionLabel.8-plots": "caseSectionLabel.7-plots",
    "caseSectionLabel.9": "caseSectionLabel.8",
}

# Old subsection key -> new subsection key
SUBSECTION_KEY_MAP = {
    "caseSubsectionLabel.8.1": "caseSubsectionLabel.7.1",
    "caseSubsectionLabel.8.2": "caseSubsectionLabel.7.2",
    "caseSubsectionLabel.8.3": "caseSubsectionLabel.7.3",
    "caseSubsectionLabel.8.4": "caseSubsectionLabel.7.4",
    "caseSubsectionLabel.8.5": "caseSubsectionLabel.7.5",
    "caseSubsectionLabel.8.6": "caseSubsectionLabel.7.6",
    "caseSubsectionLabel.8.7": "caseSubsectionLabel.7.7",
    "caseSubsectionLabel.8.7-parcels": "caseSubsectionLabel.7.7-parcels",
    "caseSubsectionLabel.8.7-8.8-mapping": "caseSubsectionLabel.7.7-7.8-mapping",
    "caseSubsectionLabel.8.8.1": "caseSubsectionLabel.7.8.1",
    "caseSubsectionLabel.8.8.2": "caseSubsectionLabel.7.8.2",
    "caseSubsectionLabel.9.1": "caseSubsectionLabel.8.1",
    "caseSubsectionLabel.9.4": "caseSubsectionLabel.8.4",
}


def _upsert_setting(SystemSetting, key, value, description):
    setting = SystemSetting.objects.filter(key=key).first()
    if setting is None:
        SystemSetting.objects.create(key=key, value=value, description=description)
        return
    setting.value = value
    setting.description = description
    setting.save(update_fields=["value", "description"])


def renumber_case_labels(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")

    # Move old section labels to their new keys so custom admin labels are preserved.
    for old_key, new_key in SECTION_KEY_MAP.items():
        old_setting = SystemSetting.objects.filter(key=old_key).first()
        if old_setting is None:
            continue
        section_key = new_key.removeprefix("caseSectionLabel.")
        _upsert_setting(
            SystemSetting,
            new_key,
            old_setting.value,
            f"Τίτλος εμφάνισης Ενότητας {section_key} (πλοήγηση και κεφαλίδα οθόνης)",
        )

    # Move old subsection labels to new keys.
    for old_key, new_key in SUBSECTION_KEY_MAP.items():
        old_setting = SystemSetting.objects.filter(key=old_key).first()
        if old_setting is None:
            continue
        subsection_key = new_key.removeprefix("caseSubsectionLabel.")
        _upsert_setting(
            SystemSetting,
            new_key,
            old_setting.value,
            f"Τίτλος εμφάνισης υποενότητας {subsection_key} (οθόνες επεξεργασίας και προβολή φακέλου)",
        )

    # Ensure legacy value from the removed section 7 is replaced by the new section-7 title.
    _upsert_setting(
        SystemSetting,
        "caseSectionLabel.7",
        SECTION_DEFAULTS["caseSectionLabel.7"],
        "Τίτλος εμφάνισης Ενότητας 7 (πλοήγηση και κεφαλίδα οθόνης)",
    )

    # Ensure the defaults for 7-plots and 8 are present and renumbered.
    _upsert_setting(
        SystemSetting,
        "caseSectionLabel.7-plots",
        SECTION_DEFAULTS["caseSectionLabel.7-plots"],
        "Τίτλος εμφάνισης Ενότητας 7-plots (πλοήγηση και κεφαλίδα οθόνης)",
    )
    _upsert_setting(
        SystemSetting,
        "caseSectionLabel.8",
        SECTION_DEFAULTS["caseSectionLabel.8"],
        "Τίτλος εμφάνισης Ενότητας 8 (πλοήγηση και κεφαλίδα οθόνης)",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_update_subsection_label_6_2"),
    ]

    operations = [
        migrations.RunPython(renumber_case_labels, migrations.RunPython.noop),
    ]
