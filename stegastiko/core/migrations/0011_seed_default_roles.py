from django.db import migrations

CASE_SECTIONS = (
    "case_section_1",
    "case_section_2",
    "case_section_3",
    "case_section_4",
    "case_section_5",
    "case_section_6",
    "case_section_7",
    "case_section_7_plots",
    "case_section_8",
)

# Every access type of each case section (mirrors core.function_catalog at v2.0.41).
CASE_SECTION_ACTIONS = {
    "case_section_1": ("view", "edit"),
    "case_section_2": ("view", "create", "edit", "delete", "send"),
    "case_section_3": ("view", "create", "edit", "delete"),
    "case_section_4": ("view", "create", "edit", "delete", "export"),
    "case_section_5": ("view", "create", "edit", "delete"),
    "case_section_6": ("view", "edit", "export"),
    "case_section_7": ("view", "edit"),
    "case_section_7_plots": ("view", "edit"),
    "case_section_8": ("view", "create", "edit", "publish"),
}

SETTINGS_PAGES = (
    "settings_catalogs",
    "settings_branding",
    "settings_workflow",
    "settings_section_labels",
    "settings_subsection_labels",
    "settings_email",
)

CASES_READ = {"cases": ("view",), "case_history": ("view",)} | {
    code: ("view",) for code in CASE_SECTIONS
}
CASE_EXPORTS = {"case_section_4": ("export",), "case_section_6": ("export",)}

CASES_FULL = {
    "cases": ("view", "create"),
    "case_history": ("view",),
    **CASE_SECTION_ACTIONS,
}


def _merge(*parts):
    merged = {}
    for part in parts:
        for code, actions in part.items():
            merged.setdefault(code, set()).update(actions)
    return merged


DEFAULT_ROLES = (
    (
        "Διαχειριστής συστήματος",
        "Χρήστες, ρόλοι και ρυθμίσεις συστήματος. Προβολή υποθέσεων και αιτήσεων "
        "χωρίς δικαίωμα καταχώρισης ή αποφάσεων (§Β.3).",
        _merge(
            CASES_READ,
            {"applications": ("view",)},
            {"settings": ("view",)},
            {code: ("view", "edit") for code in SETTINGS_PAGES},
            {
                "settings_users": ("view", "create", "edit"),
                "settings_roles": ("view", "create", "edit", "delete"),
            },
        ),
    ),
    (
        "Προϊστάμενος ελέγχου",
        "Πλήρης πρόσβαση στις υποθέσεις Κ.Σ. / Δ.Δ. και στις αιτήσεις πολιτών, "
        "περιλαμβανομένης της οριστικοποίησης και έκδοσης ανακοίνωσης (8.3).",
        _merge(
            {"reminders": ("view",)},
            CASES_FULL,
            {"applications": ("view", "create", "edit"), "application_import": ("import",)},
        ),
    ),
    (
        "Λειτουργός καταχώρισης",
        "Καταχώριση και επεξεργασία σε όλες τις Ενότητες και στις αιτήσεις πολιτών· "
        "χωρίς οριστικοποίηση / έκδοση ανακοίνωσης (8.3).",
        _merge(
            {"reminders": ("view",)},
            {code: actions for code, actions in CASES_FULL.items() if code != "case_section_8"},
            {"case_section_8": ("view", "create", "edit")},
            {"applications": ("view", "create", "edit"), "application_import": ("import",)},
        ),
    ),
    (
        "Τεχνικός λειτουργός",
        "Τεχνική αξιολόγηση (Ενότητα 4) και υποδομές διαχωρισμού (7.1–7.6)· "
        "προβολή των υπόλοιπων Ενοτήτων. Χωρίς πρόσβαση σε αιτήσεις πολιτών.",
        _merge(
            {"reminders": ("view",)},
            CASES_READ,
            CASE_EXPORTS,
            {
                "case_section_4": CASE_SECTION_ACTIONS["case_section_4"],
                "case_section_7": ("view", "edit"),
            },
        ),
    ),
    (
        "Μέλος Επιτροπής",
        "Προβολή υποθέσεων και αιτήσεων πολιτών. Οι αποφάσεις 10.5 και η σειρά 10.7 "
        "θα προστεθούν όταν υλοποιηθούν.",
        _merge(CASES_READ, CASE_EXPORTS, {"applications": ("view",)}),
    ),
    (
        "Έπαρχος",
        "Προβολή όλων, διαχωρισμός/οικόπεδα (Ενότητα 7) και οριστικοποίηση / "
        "έκδοση ανακοίνωσης (8.3).",
        _merge(
            {"reminders": ("view",)},
            CASES_READ,
            CASE_EXPORTS,
            {"case_section_7": ("view", "edit"), "case_section_8": ("view", "publish")},
            {"applications": ("view",)},
        ),
    ),
    (
        "Μόνο ανάγνωση",
        "Προβολή και αναφορές (PDF), περιλαμβανομένου του ιστορικού.",
        _merge({"reminders": ("view",)}, CASES_READ, CASE_EXPORTS, {"applications": ("view",)}),
    ),
)

# Members of the former Django groups (migration 0003) keep an equivalent role.
LEGACY_GROUP_TO_ROLE = {
    "Λειτουργός καταχώρισης": "Λειτουργός καταχώρισης",
    "Προϊστάμενος ελέγχου": "Προϊστάμενος ελέγχου",
    "Μέλος Επιτροπής": "Μέλος Επιτροπής",
    "Έπαρχος": "Έπαρχος",
    "Διαχειριστής": "Διαχειριστής συστήματος",
    "Μόνο ανάγνωση": "Μόνο ανάγνωση",
}


def seed_default_roles(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    Group = apps.get_model("auth", "Group")

    roles = {}
    for name, description, grants in DEFAULT_ROLES:
        role, _ = Role.objects.get_or_create(name=name, defaults={"description": description})
        role.description = description
        role.grants = sorted(f"{code}:{action}" for code, actions in grants.items() for action in actions)
        role.save()
        roles[name] = role

    for group_name, role_name in LEGACY_GROUP_TO_ROLE.items():
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            continue
        roles[role_name].members.add(*group.user_set.all())
        group.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0010_role"),
    ]

    operations = [migrations.RunPython(seed_default_roles, migrations.RunPython.noop)]
