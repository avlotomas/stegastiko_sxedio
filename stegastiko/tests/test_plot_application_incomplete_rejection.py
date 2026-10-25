"""Ελλιπής αίτηση: εκκρεμεί λόγω ελλείψεων ή απορρίπτεται από τον λειτουργό (Ενότ. 5(β), 20.2)."""

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import ActionHistory, Role
from plot_applications.models import (
    ApplicationCompleteness,
    ApplicationStage,
    PlotAllocationStatus,
)
from plot_applications.prioritization import build_prioritization_list
from plot_applications.rules import apply_evaluation
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    _application,
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


def _detail_html(client, application):
    return client.get(reverse("plot_applications:detail", args=[application.pk])).content.decode()


@pytest.mark.django_db
class TestIncompleteRejection:
    def test_incomplete_application_is_pending_in_stage_1_with_reject_form(self, staff_client, cycle):
        application = _incomplete(cycle)
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE
        assert application.application_stage == ApplicationStage.COLLECTION
        assert application.beneficiary_status == "pending"

        html = _detail_html(staff_client, application)
        assert "Εκκρεμεί λόγω ελλείψεων" in html
        assert "data-incomplete-reject-form" in html
        assert "Δικαιολογητικά:" in html  # pre-filled reason lists the failing criteria

    def test_reject_requires_reason(self, staff_client, cycle):
        application = _incomplete(cycle)
        url = reverse("plot_applications:incomplete_reject", args=[application.pk])
        resp = staff_client.post(url, {"incomplete_rejection_reason": "   "})
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is False
        assert application.completeness_result == ApplicationCompleteness.INCOMPLETE

    def test_reject_closes_application_as_not_allocated_and_is_audited(self, staff_client, cycle):
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
        assert application.completeness_result == ApplicationCompleteness.REJECTED
        assert application.application_stage == ApplicationStage.COMPLETED
        assert application.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED
        assert application.beneficiary_status == "fail"
        assert application.beneficiary_label == "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"

        history = ActionHistory.objects.filter(
            entity_type="PlotApplication", entity_id=str(application.pk)
        )
        assert history.filter(field_name="incomplete_rejected").exists()
        assert history.filter(field_name="incomplete_rejection_reason", new_value=REASON).exists()

        html = _detail_html(staff_client, application)
        assert "Απορρίφθηκε λόγω ελλείψεων" in html
        assert REASON in html
        assert "data-incomplete-reject-form" not in html
        assert "data-incomplete-reject-revoke-form" in html

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
        assert application.completeness_result == ApplicationCompleteness.REJECTED
        assert application.application_stage == ApplicationStage.COMPLETED
        rows = build_prioritization_list(application.community)
        assert application.pk not in [
            row.application.pk for row in (*rows.beneficiaries, *rows.others)
        ]

    def test_complete_application_cannot_be_rejected(self, staff_client, cycle):
        application = _application(cycle)
        apply_evaluation(application)
        assert "data-incomplete-reject-form" not in _detail_html(staff_client, application)
        resp = staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[application.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.incomplete_rejected is False
        assert application.completeness_result == ApplicationCompleteness.COMPLETE
        assert application.application_stage != ApplicationStage.COMPLETED

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
        assert application.application_stage == ApplicationStage.COLLECTION
        assert application.plot_allocation_status == PlotAllocationStatus.PENDING

    def test_list_filters_treat_rejected_as_not_beneficiary(self, staff_client, cycle):
        pending = _incomplete(cycle)
        rejected = _incomplete(cycle)
        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[rejected.pk]),
            {"incomplete_rejection_reason": REASON},
        )
        url = reverse("plot_applications:list")
        fail_list = list(staff_client.get(url, {"beneficiary": "fail"}).context["applications"])
        pending_list = list(staff_client.get(url, {"beneficiary": "pending"}).context["applications"])
        rejected_list = list(
            staff_client.get(url, {"completeness": ApplicationCompleteness.REJECTED}).context["applications"]
        )
        assert rejected in fail_list and pending not in fail_list
        assert pending in pending_list and rejected not in pending_list
        assert rejected_list == [rejected]

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
