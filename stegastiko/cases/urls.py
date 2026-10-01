from django.urls import path

from cases import views

app_name = "cases"

urlpatterns = [
    path("", views.case_list, name="list"),
    path("new/", views.case_create, name="create"),
    path("<int:pk>/", views.case_detail, name="detail"),
    path("<int:pk>/history/", views.case_history, name="history"),
    path("<int:pk>/section/<str:section>/", views.case_section_edit, name="section_edit"),
    path(
        "<int:pk>/deficiency-email/<int:check_id>/",
        views.case_deficiency_email_create,
        name="deficiency_email_create",
    ),
    path(
        "<int:pk>/deficiency-email/send/<int:communication_id>/",
        views.case_deficiency_email_send,
        name="deficiency_email_send",
    ),
    path("<int:pk>/announcement/new/", views.announcement_create, name="announcement_create"),
    path(
        "<int:pk>/announcement/<int:cycle_id>/",
        views.announcement_detail,
        name="announcement_detail",
    ),
    path(
        "<int:pk>/announcement/<int:cycle_id>/regenerate/",
        views.announcement_regenerate,
        name="announcement_regenerate",
    ),
    path(
        "<int:pk>/announcement/<int:cycle_id>/publish/",
        views.announcement_publish,
        name="announcement_publish",
    ),
]
