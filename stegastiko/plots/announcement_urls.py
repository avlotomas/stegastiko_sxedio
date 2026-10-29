from django.urls import path

from plots import announcement_views as views

app_name = "announcements"

urlpatterns = [
    path("", views.announcement_list, name="list"),
    path("new/", views.announcement_create, name="create"),
    path("<int:pk>/", views.announcement_detail, name="detail"),
    path("<int:pk>/export/", views.announcement_export, name="export"),
    path("<int:pk>/publish/", views.announcement_publish, name="publish"),
    path("<int:pk>/publications/new/", views.publication_form, name="publication_create"),
    path("<int:pk>/publications/<str:method>/date/", views.publication_date, name="publication_date"),
    path(
        "<int:pk>/publications/<int:publication_id>/edit/",
        views.publication_form,
        name="publication_edit",
    ),
    path(
        "<int:pk>/publications/<int:publication_id>/delete/",
        views.publication_delete,
        name="publication_delete",
    ),
    # 6-stage workflow routes
    path("<int:pk>/stage2/start/", views.announcement_start_committee, name="start_committee"),
    path("<int:pk>/stage2/decide/", views.announcement_committee_decision, name="committee_decision"),
    path(
        "<int:pk>/entries/<int:entry_id>/confirm-receipt/",
        views.announcement_confirm_receipt,
        name="confirm_receipt",
    ),
    path(
        "<int:pk>/stage3/objections/new/",
        views.announcement_register_objection,
        name="register_objection",
    ),
    path(
        "<int:pk>/stage3/objections/<int:objection_id>/decide/",
        views.announcement_decide_objection,
        name="decide_objection",
    ),
    path(
        "<int:pk>/stage3/pending/new/",
        views.announcement_add_pending_requirement,
        name="add_pending_requirement",
    ),
    path(
        "<int:pk>/stage3/pending/<int:requirement_id>/toggle/",
        views.announcement_toggle_pending_requirement,
        name="toggle_pending_requirement",
    ),
    path(
        "<int:pk>/final-list/start/",
        views.announcement_start_final_list,
        name="start_final_list",
    ),
    path(
        "<int:pk>/stage3/final-list/issue/",
        views.announcement_issue_final_list,
        name="issue_final_list",
    ),
    path(
        "<int:pk>/stage4/lottery/schedule/",
        views.announcement_schedule_lottery,
        name="schedule_lottery",
    ),
    path(
        "<int:pk>/stage4/lottery/record/",
        views.announcement_record_lottery,
        name="record_lottery",
    ),
    path(
        "<int:pk>/stage4/lottery/complete/",
        views.announcement_complete_lottery,
        name="complete_lottery",
    ),
    path(
        "<int:pk>/stage5/allocations/<int:allocation_id>/invite/",
        views.announcement_invite_agreement,
        name="invite_agreement",
    ),
    path(
        "<int:pk>/stage5/allocations/<int:allocation_id>/agreement-docx/",
        views.announcement_agreement_docx,
        name="agreement_docx",
    ),
    path(
        "<int:pk>/stage5/allocations/<int:allocation_id>/record-signature-payment/",
        views.announcement_record_signature_payment,
        name="record_signature_payment",
    ),
    path(
        "<int:pk>/stage5/allocations/<int:allocation_id>/forfeit/",
        views.announcement_forfeit_allocation,
        name="forfeit_allocation",
    ),
    path(
        "<int:pk>/stage5/promote-runner-up/",
        views.announcement_promote_runner_up,
        name="promote_runner_up",
    ),
    path(
        "<int:pk>/stage5/complete/",
        views.announcement_complete_agreements,
        name="complete_agreements",
    ),
]
