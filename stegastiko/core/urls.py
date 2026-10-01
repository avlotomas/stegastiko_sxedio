from django.urls import path

from core.views import AppLoginView, AppLogoutView, home, system_configuration


urlpatterns = [
    path("", home, name="home"),
    path("settings/", system_configuration, name="system_configuration"),
    path("login/", AppLoginView.as_view(), name="login"),
    path("logout/", AppLogoutView.as_view(), name="logout"),
]
