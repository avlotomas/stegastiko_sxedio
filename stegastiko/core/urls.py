from django.urls import path

from core.access_views import (
    role_create,
    role_delete,
    role_edit,
    role_list,
    user_create,
    user_edit,
    user_list,
)
from core.settings_views import (
    system_configuration,
    system_settings_branding,
    system_settings_email,
    system_settings_menu_labels,
    system_settings_section_labels,
    system_settings_subsection_labels,
    system_settings_workflow,
)
from core.views import (
    AppLoginView,
    AppLogoutView,
    account,
    home,
    reminder_mark_read,
    reminders,
    utility_service_types,
)


urlpatterns = [
    path("", home, name="home"),
    path("account/", account, name="account"),
    path("reminders/", reminders, name="reminders"),
    path("reminders/read/", reminder_mark_read, name="reminder_mark_read"),
    path("settings/", system_configuration, name="system_configuration"),
    path("settings/users/", user_list, name="settings_users"),
    path("settings/users/new/", user_create, name="settings_user_create"),
    path("settings/users/<int:pk>/", user_edit, name="settings_user_edit"),
    path("settings/roles/", role_list, name="settings_roles"),
    path("settings/roles/new/", role_create, name="settings_role_create"),
    path("settings/roles/<int:pk>/", role_edit, name="settings_role_edit"),
    path("settings/roles/<int:pk>/delete/", role_delete, name="settings_role_delete"),
    path("settings/branding/", system_settings_branding, name="system_settings_branding"),
    path("settings/menu/", system_settings_menu_labels, name="system_settings_menu_labels"),
    path("settings/workflow/", system_settings_workflow, name="system_settings_workflow"),
    path(
        "settings/section-labels/",
        system_settings_section_labels,
        name="system_settings_section_labels",
    ),
    path(
        "settings/subsection-labels/",
        system_settings_subsection_labels,
        name="system_settings_subsection_labels",
    ),
    path("settings/email/", system_settings_email, name="system_settings_email"),
    path(
        "settings/utility-services/",
        utility_service_types,
        name="utility_service_types",
    ),
    path("login/", AppLoginView.as_view(), name="login"),
    path("logout/", AppLogoutView.as_view(), name="logout"),
]
