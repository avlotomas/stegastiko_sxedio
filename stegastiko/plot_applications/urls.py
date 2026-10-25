from django.urls import path

from plot_applications import views

app_name = "plot_applications"

urlpatterns = [
    path("", views.plot_application_list, name="list"),
    path("new/", views.plot_application_create, name="create"),
    path("prioritization/", views.plot_application_prioritization, name="prioritization"),
    path(
        "prioritization/reorder/",
        views.plot_application_prioritization_reorder,
        name="prioritization_reorder",
    ),
    path(
        "prioritization/reset/",
        views.plot_application_prioritization_reset,
        name="prioritization_reset",
    ),
    path(
        "prioritization/report-pdf/",
        views.plot_application_prioritization_report_pdf,
        name="prioritization_report_pdf",
    ),
    path("persons/lookup/", views.person_lookup, name="person_lookup"),
    path("persons/<int:pk>/edit/", views.person_edit, name="person_edit"),
    path("<int:pk>/", views.plot_application_detail, name="detail"),
    path(
        "<int:pk>/eligibility-report-pdf/",
        views.plot_application_eligibility_report_pdf,
        name="eligibility_report_pdf",
    ),
    path("<int:pk>/edit/", views.plot_application_edit, name="edit"),
    path("<int:pk>/history/", views.plot_application_history, name="history"),
    path(
        "<int:pk>/documents-completeness/",
        views.plot_application_documents_completeness_save,
        name="documents_completeness_save",
    ),
    path(
        "<int:pk>/eligibility-override/",
        views.plot_application_eligibility_override_save,
        name="eligibility_override_save",
    ),
    path(
        "<int:pk>/incomplete-reject/",
        views.plot_application_incomplete_reject,
        name="incomplete_reject",
    ),
    path(
        "<int:pk>/incomplete-reject/revoke/",
        views.plot_application_incomplete_reject_revoke,
        name="incomplete_reject_revoke",
    ),
    path("<int:pk>/delete/", views.plot_application_delete, name="delete"),
    path("<int:pk>/email/send/", views.plot_application_email_send, name="email_send"),
    path(
        "<int:pk>/communications/<int:communication_id>/",
        views.plot_application_communication_detail,
        name="communication_detail",
    ),
]
