from django.urls import path

from core.views import (
    AppLoginView,
    AppLogoutView,
    home,
    reminder_mark_read,
    reminders,
    system_configuration,
    utility_service_types,
)


urlpatterns = [
    path("", home, name="home"),
    path("reminders/", reminders, name="reminders"),
    path("reminders/read/", reminder_mark_read, name="reminder_mark_read"),
    path("settings/", system_configuration, name="system_configuration"),
    path(
        "settings/utility-services/",
        utility_service_types,
        name="utility_service_types",
    ),
    path("login/", AppLoginView.as_view(), name="login"),
    path("logout/", AppLogoutView.as_view(), name="logout"),
]
