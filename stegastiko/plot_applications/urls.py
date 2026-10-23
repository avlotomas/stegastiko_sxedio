from django.urls import path

from plot_applications import views

app_name = "plot_applications"

urlpatterns = [
    path("", views.plot_application_list, name="list"),
    path("new/", views.plot_application_create, name="create"),
    path("persons/lookup/", views.person_lookup, name="person_lookup"),
    path("persons/<int:pk>/edit/", views.person_edit, name="person_edit"),
    path("<int:pk>/", views.plot_application_detail, name="detail"),
    path("<int:pk>/edit/", views.plot_application_edit, name="edit"),
    path("<int:pk>/delete/", views.plot_application_delete, name="delete"),
    path("<int:pk>/email/send/", views.plot_application_email_send, name="email_send"),
    path(
        "<int:pk>/communications/<int:communication_id>/",
        views.plot_application_communication_detail,
        name="communication_detail",
    ),
]
