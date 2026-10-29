"""Απόρριψη αίτησης από τον λειτουργό με υποχρεωτικό λόγο σε modal (Ενότ. 5(β), 6, 20)."""

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import ActionHistory, Role
from plot_applications.models import (
    ApplicationCompleteness,
    ApplicationStage,
    DocumentsCompleteness,
    EligibilityResult,
    PlotAllocationStatus,
)
from plot_applications.prioritization import build_prioritization_list
from plot_applications.rules import apply_evaluation
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    _application,
    available_plot,
    community,
    cycle,
    staff_client,
)

REASON = "Λείπει ο λογαριασμός ΑΗΚ και η βεβαίωση Κοινότητας."


def _incomplete(cycle):
    application = _application(cycle)
    application.attached_documents = []
    apply_evaluation(application)
    application.refresh_from_db()
    return application


def _incomplete_missing_fields(cycle):
    application = _application(cycle, email="", submitted_on=None)
    apply_evaluation(application)
    application.refresh_from_db()
    return application


def _detail_html(client, application):
    return client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()


@pytest.mark.django_db
class TestIncompleteRejection:
    def test_incomplete_application_is_pending_in_stage_1_with_reject_modal(self, staff_client, cycle):
        application = _incomplete(cycle)
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.documents_completeness == DocumentsCompleteness.INCOMPLETE
        assert application.application_stage == ApplicationStage.COLLECTION
        assert application.beneficiary_status == "pending"

        html = _detail_html(staff_client, application)
        assert "Εκκρεμεί λόγω ελλείψεων" in html
        assert "data-incomplete-reject-open" in html
        assert 'id="plot-application-incomplete-reject-dialog"' in html
        assert "data-incomplete-reject-form" in html

    def test_reject_requires_reason(self, staff_client, cycle):
        application = _incomplete(cycle)
        url = reverse("plot_applications:incomplete_reject", args=[application.pk])
        resp = staff_client.post(url, {"incomplete_rejection_reason": "   "})
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is False
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.application_stage == ApplicationStage.COLLECTION

    def test_reject_due_to_missing_documents_keeps_completeness_incomplete_and_sets_stage_rejected(
        self, staff_client, cycle
    ):
        application = _incomplete(cycle)
        resp = staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is True
        assert application.incomplete_rejection_reason == REASON
        assert application.incomplete_rejected_on == timezone.localdate()
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.get_completeness_result_display() == "Ελλιπής"
        assert application.documents_completeness == DocumentsCompleteness.INCOMPLETE
        assert application.get_documents_completeness_display() == "Ελλιπής"
        assert application.application_stage == ApplicationStage.REJECTED
        assert application.application_stage_label == "Απόρριψη από λειτουργό"
        assert application.stage_badge == "fail"
        assert application.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED
        assert application.beneficiary_status == ""
        assert application.beneficiary_label == ""
        assert application.eligibility_label == ""
        assert application.plot_allocation_label == ""

        history = ActionHistory.objects.filter(
            entity_type="PlotApplication", entity_id=str(application.pk)
        )
        assert history.filter(field_name="incomplete_rejected").exists()
        assert history.filter(field_name="incomplete_rejection_reason", new_value=REASON).exists()

        html = _detail_html(staff_client, application)
        assert "Απόρριψη" in html
        assert REASON in html
        assert "data-incomplete-reject-form" not in html
        assert "data-incomplete-reject-revoke-form" in html

    def test_reject_due_to_missing_fields_keeps_both_completeness_and_documents_incomplete_and_sets_stage_rejected(
        self, staff_client, cycle
    ):
        application = _incomplete_missing_fields(cycle)
        resp = staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": "Λείπουν η ημερομηνία υποβολής και το email."},
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is True
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.get_completeness_result_display() == "Ελλιπής"
        assert application.documents_completeness == DocumentsCompleteness.INCOMPLETE
        assert application.get_documents_completeness_display() == "Ελλιπής"
        assert application.application_stage == ApplicationStage.REJECTED
        assert application.application_stage_label == "Απόρριψη από λειτουργό"
        assert application.stage_badge == "fail"
        assert application.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED

    def test_rejected_with_pending_eligibility_shows_no_beneficiary_or_plot_allocation(
        self, staff_client, cycle
    ):
        application = _incomplete_missing_fields(cycle)
        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": "Λείπουν η ημερομηνία υποβολής και το email."},
        )
        application.refresh_from_db()
        assert application.application_stage == ApplicationStage.REJECTED
        assert application.eligibility_result == EligibilityResult.PENDING
        assert application.beneficiary_label == ""
        assert application.plot_allocation_label == ""

        url = reverse("plot_applications:list")
        list_html = staff_client.get(url).content.decode()
        list_tbody = list_html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        assert "ΔΙΚΑΙΟΥΧΟΣ" not in list_tbody
        assert "Δεν πήρε οικόπεδο" not in list_tbody
        for params in (
            {"beneficiary": "fail"},
            {"beneficiary": "pending"},
            {"plot_allocation": PlotAllocationStatus.NOT_ALLOCATED},
        ):
            assert application not in staff_client.get(url, params).context["applications"]

        detail_html = _detail_html(staff_client, application)
        assert "data-application-beneficiary-badge" not in detail_html
        assert "data-application-plot-allocation-badge" not in detail_html

    def test_rejected_application_stays_rejected_when_completed_later(self, staff_client, cycle):
        application = _incomplete(cycle)
        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        application.refresh_from_db()
        application.attached_documents = _application(cycle).attached_documents
        apply_evaluation(application)
        application.refresh_from_db()
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.documents_completeness == DocumentsCompleteness.INCOMPLETE
        assert application.application_stage == ApplicationStage.REJECTED
        rows = build_prioritization_list(application.community)
        assert application.pk not in [
            row.application.pk for row in (*rows.beneficiaries, *rows.others)
        ]

    def test_complete_application_can_also_be_rejected_with_free_text_reason(self, staff_client, cycle):
        application = _application(cycle)
        apply_evaluation(application)
        application.refresh_from_db()
        assert application.completeness_result == ApplicationCompleteness.COMPLETE
        assert application.documents_completeness == DocumentsCompleteness.COMPLETE
        assert "data-incomplete-reject-open" in _detail_html(staff_client, application)
        assert "data-incomplete-reject-form" in _detail_html(staff_client, application)

        other_reason = "Ανακριβή στοιχεία στην ένορκη δήλωση."
        resp = staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": other_reason},
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is True
        assert application.incomplete_rejection_reason == other_reason
        assert application.completeness_result == ApplicationCompleteness.COMPLETE
        assert application.documents_completeness == DocumentsCompleteness.COMPLETE
        assert application.application_stage == ApplicationStage.REJECTED
        assert application.application_stage_label == "Απόρριψη από λειτουργό"
        assert application.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED
        assert application.beneficiary_status == ""
        assert application.eligibility_label == ""

        list_html = staff_client.get(reverse("plot_applications:list")).content.decode()
        list_tbody = list_html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        assert "Απόρριψη από λειτουργό" in list_tbody
        assert "ΜΗ ΔΙΚΑΙΟΥΧΟΣ" not in list_tbody
        assert "data-application-eligibility-badge" not in list_tbody

    def test_revoke_returns_application_to_pending(self, staff_client, cycle):
        application = _incomplete(cycle)
        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        resp = staff_client.post(
            reverse("plot_applications:incomplete_reject_revoke", args=[application.pk])
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is False
        assert application.incomplete_rejection_reason == ""
        assert application.incomplete_rejected_on is None
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.documents_completeness == DocumentsCompleteness.INCOMPLETE
        assert application.application_stage == ApplicationStage.COLLECTION
        assert application.plot_allocation_status == PlotAllocationStatus.PENDING

    def test_list_filters_keep_officer_rejection_out_of_beneficiary_filters(self, staff_client, cycle):
        pending = _incomplete(cycle)
        rejected = _incomplete(cycle)
        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[rejected.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        url = reverse("plot_applications:list")
        fail_list = list(staff_client.get(url, {"beneficiary": "fail"}).context["applications"])
        pending_list = list(staff_client.get(url, {"beneficiary": "pending"}).context["applications"])
        rejected_stage_list = list(
            staff_client.get(url, {"stage": ApplicationStage.REJECTED}).context["applications"]
        )
        incomplete_list = list(
            staff_client.get(url, {"completeness": ApplicationCompleteness.INCOMPLETE}).context["applications"]
        )
        docs_incomplete_list = list(
            staff_client.get(
                url, {"documents_completeness": DocumentsCompleteness.INCOMPLETE}
            ).context["applications"]
        )
        assert rejected not in fail_list and pending not in fail_list
        assert pending in pending_list and rejected not in pending_list
        assert rejected_stage_list == [rejected]
        assert rejected in incomplete_list and pending in incomplete_list
        assert rejected in docs_incomplete_list and pending in docs_incomplete_list

    def test_reject_requires_eligibility_edit_permission(self, client, make_user, cycle):
        application = _incomplete(cycle)
        role = Role.objects.create(
            name="Επεξεργασία χωρίς έλεγχο κριτηρίων",
            grants=[
                "plot_applications:view",
                "plot_applications:edit",
                "plot_app_eligibility:view",
                "plot_app_documents:view",
                "plot_app_documents:edit",
            ],
        )
        user = make_user("no_elig_edit")
        role.members.add(user)
        client.force_login(user)
        assert "data-incomplete-reject-form" not in _detail_html(client, application)
        resp = client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        assert resp.status_code == 403
        application.refresh_from_db()
        assert application.incomplete_rejected is False
