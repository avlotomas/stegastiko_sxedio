from django.urls import reverse

from core.permissions import has_access

SETTINGS_NAV_SECTIONS = (
    {
        "key": "overview",
        "url_name": "system_configuration",
        "label": "Επισκόπηση",
        "function": "settings",
    },
    {
        "key": "users",
        "url_name": "settings_users",
        "label": "Χρήστες",
        "function": "settings_users",
    },
    {
        "key": "roles",
        "url_name": "settings_roles",
        "label": "Ρόλοι και δικαιώματα",
        "function": "settings_roles",
    },
    {
        "key": "catalogs",
        "url_name": "utility_service_types",
        "label": "Κατάλογος υπηρεσιών (4.2)",
        "function": "settings_catalogs",
    },
    {
        "key": "branding",
        "url_name": "system_settings_branding",
        "label": "Εμφάνιση εφαρμογής",
        "function": "settings_branding",
    },
    {
        "key": "menu_labels",
        "url_name": "system_settings_menu_labels",
        "label": "Ονόματα μενού",
        "function": "settings_menu_labels",
    },
    {
        "key": "workflow",
        "url_name": "system_settings_workflow",
        "label": "Αριθμοδότηση και υπενθυμίσεις",
        "function": "settings_workflow",
    },
    {
        "key": "case_labels",
        "url_name": "system_settings_case_labels",
        "label": "Τίτλοι αίτησης διαχωρισμού",
        "functions": ("settings_section_labels", "settings_subsection_labels"),
    },
    {
        "key": "email",
        "url_name": "system_settings_email",
        "label": "Αποστολή email (SMTP)",
        "function": "settings_email",
    },
)


def settings_nav(user, active_key: str):
    items = []
    for section in SETTINGS_NAV_SECTIONS:
        functions = section.get("functions")
        if functions:
            if not any(has_access(user, code) for code in functions):
                continue
        elif not has_access(user, section["function"]):
            continue
        items.append(
            {
                **section,
                "url": reverse(section["url_name"]),
                "is_active": section["key"] == active_key,
            }
        )
    return items
