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
        "<int:pk>/section/4/blank-pdf/",
        views.section_4_blank_pdf,
        name="section_4_blank_pdf",
    ),
    path(
        "<int:pk>/section/6/report-pdf/",
        views.section_6_report_pdf,
        name="section_6_report_pdf",
    ),
    path(
        "<int:pk>/completeness-checks/new/",
        views.completeness_check_form,
        name="completeness_check_create",
    ),
    path(
        "<int:pk>/completeness-checks/<int:check_id>/",
        views.completeness_check_form,
        name="completeness_check_edit",
    ),
    path(
        "<int:pk>/completeness-checks/<int:check_id>/delete/",
        views.completeness_check_delete,
        name="completeness_check_delete",
    ),
    path(
        "<int:pk>/completeness-checks/<int:check_id>/deficiency-email/send/",
        views.case_deficiency_email_send,
        name="deficiency_email_send",
    ),
    path(
        "<int:pk>/communications/<int:communication_id>/",
        views.case_communication_detail,
        name="communication_detail",
    ),
    path("<int:pk>/land-plots/new/", views.land_plot_form, name="land_plot_create"),
    path(
        "<int:pk>/land-plots/<int:plot_id>/edit/",
        views.land_plot_form,
        name="land_plot_edit",
    ),
    path(
        "<int:pk>/land-plots/<int:plot_id>/delete/",
        views.land_plot_delete,
        name="land_plot_delete",
    ),
    path(
        "<int:pk>/land-plots/<int:plot_id>/evaluation/",
        views.land_plot_evaluation_form,
        name="land_plot_evaluation",
    ),
    path(
        "<int:pk>/utility-services/new/",
        views.utility_service_form,
        name="utility_service_create",
    ),
    path(
        "<int:pk>/utility-services/<int:service_id>/edit/",
        views.utility_service_form,
        name="utility_service_edit",
    ),
    path(
        "<int:pk>/utility-services/<int:service_id>/delete/",
        views.utility_service_delete,
        name="utility_service_delete",
    ),
    path(
        "<int:pk>/suitability-consultations/new/",
        views.suitability_consultation_form,
        name="suitability_consultation_create",
    ),
    path(
        "<int:pk>/suitability-consultations/<int:consultation_id>/edit/",
        views.suitability_consultation_form,
        name="suitability_consultation_edit",
    ),
    path(
        "<int:pk>/suitability-consultations/<int:consultation_id>/delete/",
        views.suitability_consultation_delete,
        name="suitability_consultation_delete",
    ),
    path(
        "<int:pk>/attachments/<int:attachment_id>/",
        views.case_attachment_download,
        name="attachment_download",
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
