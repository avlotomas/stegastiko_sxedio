"""Προκαταρκτικός / Τελικός Κατάλογος Δικαιούχων και διαχωρισμός των δύο απορρίψεων (Ενότ. 5, 6, 7, 8)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from allocation.models import RankingEntry, RankingList
from core.models import ActionHistory
from core.timeline import build_timeline
from plot_applications.beneficiary_lists import (
    BeneficiaryListError,
    community_lists,
    issue_final_list,
    issue_preliminary_list,
    revoke_final_list,
    revoke_preliminary_list,
)
from plot_applications.models import (
    ApplicationStage,
    EligibilityOverride,
    PlotAllocationStatus,
    ResidenceCategory,
)
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    available_plot,
    community,
    cycle,
    staff_client,
)
from tests.test_plot_prioritization import _evaluated, _incomplete


def _refresh(*apps):
    for app in apps:
        app.refresh_from_db()


@pytest.fixture
def committee_apps(cycle, available_plot):
    """Δύο δικαιούχοι (ένα οικόπεδο) και ένας μη δικαιούχος."""
    first = _evaluated(cycle)
    second = _evaluated(cycle, residence_category=ResidenceCategory.REPATRIATED)
    not_beneficiary = _evaluated(cycle, has_dwelling=True)
    return {"first": first, "second": second, "not_beneficiary": not_beneficiary}


def _page(client, community):
    return client.get(reverse("plot_applications:prioritization"), {"community_id": community.pk})


@pytest.mark.django_db
class TestBeneficiaryLists:
    def test_preliminary_list_is_blocked_while_applications_are_pending(
        self, staff_client, community, committee_apps, cycle
    ):
        pending = _incomplete(cycle)
        resp = _page(staff_client, community)
        html = resp.content.decode()
        assert resp.context["phase"] == "committee"
        assert "data-list-blockers" in html
        assert pending.protocol_number in html

        resp = staff_client.post(
            reverse("plot_applications:preliminary_list_issue"), {"community_id": community.pk}
        )
        assert resp.status_code == 302
        assert not RankingList.objects.exists()

        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[pending.pk]),
            {"incomplete_rejection_reason": "Ελλείψεις πιστοποιητικών."},
        )
        resp = staff_client.post(
            reverse("plot_applications:preliminary_list_issue"), {"community_id": community.pk}
        )
        assert resp.status_code == 302
        preliminary = RankingList.objects.get(list_type=RankingList.ListType.PRELIMINARY)
        assert not preliminary.entries.filter(application=pending).exists()
        pending.refresh_from_db()
        assert pending.application_stage == ApplicationStage.REJECTED

    def test_preliminary_list_starts_objection_period(self, staff_client, community, committee_apps):
        apps = committee_apps
        preliminary = issue_preliminary_list(community, None)
        assert preliminary.objection_deadline == timezone.localdate() + timedelta(days=21)
        entries = {entry.application_id: entry for entry in preliminary.entries.all()}
        assert entries[apps["first"].pk].status == RankingEntry.Status.ELIGIBLE
        assert entries[apps["first"].pk].proposed_rank == 1
        assert entries[apps["second"].pk].proposed_rank == 2
        assert entries[apps["not_beneficiary"].pk].status == RankingEntry.Status.REJECTED

        _refresh(*apps.values())
        for app in apps.values():
            assert app.application_stage == ApplicationStage.OBJECTIONS
            assert app.plot_allocation_status == PlotAllocationStatus.PENDING
        assert apps["first"].beneficiary_label == "ΔΙΚΑΙΟΥΧΟΣ"
        assert apps["not_beneficiary"].beneficiary_label == "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"

        resp = _page(staff_client, community)
        html = resp.content.decode()
        assert resp.context["phase"] == "objections"
        assert "Περίοδος ενστάσεων" in html
        assert "data-final-list-issue" in html
        assert "Προκαταρκτικός Κατάλογος: θέση 1." in html

        detail = staff_client.get(
            reverse("plot_applications:detail", args=[apps["second"].pk])
        ).content.decode()
        assert "Προκαταρκτικός Κατάλογος Δικαιούχων" in detail
        assert "ΔΙΚΑΙΟΥΧΟΣ — θέση 2" in detail
        assert "Προκαταρκτικός κατάλογος — Ενστάσεις" in detail

        with pytest.raises(BeneficiaryListError):
            issue_preliminary_list(community, None)

    def test_change_during_objections_records_the_stage(self, staff_client, community, committee_apps):
        from plot_applications.announcement_workflow import register_objection

        apps = committee_apps
        issue_preliminary_list(community, None)
        target = apps["not_beneficiary"]
        register_objection(target, grounds="Ένσταση επί της απόρριψης (Ενότ. 7).")
        resp = staff_client.post(
            reverse("plot_applications:eligibility_override_save", args=[target.pk]),
            {
                "eligibility_override": EligibilityOverride.PASS,
                "eligibility_override_reason": "Δεκτή ένσταση (Ενότ. 7).",
            },
        )
        assert resp.status_code == 302
        target.refresh_from_db()
        assert target.application_stage == ApplicationStage.OBJECTIONS
        assert target.beneficiary_label == "ΔΙΚΑΙΟΥΧΟΣ"

        entry = ActionHistory.objects.get(
            entity_type="PlotApplication", entity_id=str(target.pk), field_name="eligibility_override"
        )
        assert entry.section_ref == "stage:objections"
        events = build_timeline(
            ActionHistory.objects.filter(entity_type="PlotApplication", entity_id=str(target.pk))
        )
        override_event = next(
            event for event in events
            if any("Δεκτή ένσταση" in str(change) for change in event["changes"])
        )
        assert override_event["stage_label"] == "Προκαταρκτικός κατάλογος — Ενστάσεις"

        listing = _page(staff_client, community).context["prioritization"]
        row = next(row for row in listing.beneficiaries if row.application.pk == target.pk)
        assert row.changed_since_preliminary is True

    def test_officer_rejection_is_not_allowed_after_the_preliminary_list(
        self, staff_client, community, committee_apps
    ):
        issue_preliminary_list(community, None)
        target = committee_apps["first"]
        assert "data-incomplete-reject-form" not in staff_client.get(
            reverse("plot_applications:detail", args=[target.pk])
        ).content.decode()
        staff_client.post(
            reverse("plot_applications:incomplete_reject", args=[target.pk]),
            {"incomplete_rejection_reason": "Χ"},
        )
        target.refresh_from_db()
        assert target.incomplete_rejected is False
        assert target.application_stage == ApplicationStage.OBJECTIONS

    def test_final_list_waits_for_the_objection_deadline(self, staff_client, community, committee_apps):
        preliminary = issue_preliminary_list(community, None)
        with pytest.raises(BeneficiaryListError):
            issue_final_list(community, None)
        staff_client.post(reverse("plot_applications:final_list_issue"), {"community_id": community.pk})
        assert not RankingList.objects.filter(list_type=RankingList.ListType.FINAL).exists()
        assert _page(staff_client, community).context["objections_open"] is True

        issue_final_list(community, None, today=preliminary.objection_deadline + timedelta(days=1))
        assert community_lists(community).phase == "final"

    def test_final_list_allocates_up_to_the_number_of_plots(
        self, staff_client, community, committee_apps
    ):
        apps = committee_apps
        preliminary = issue_preliminary_list(community, None)
        final = issue_final_list(
            community, None, today=preliminary.objection_deadline + timedelta(days=1)
        )
        assert final.plots_count == 1
        _refresh(*apps.values())

        assert apps["first"].application_stage == ApplicationStage.COMPLETED
        assert apps["first"].plot_allocation_status == PlotAllocationStatus.ALLOCATED
        assert apps["second"].application_stage == ApplicationStage.COMPLETED
        assert apps["second"].plot_allocation_status == PlotAllocationStatus.RUNNER_UP
        assert apps["second"].beneficiary_label == "ΔΙΚΑΙΟΥΧΟΣ"

        rejected = apps["not_beneficiary"]
        assert rejected.application_stage == ApplicationStage.COMMITTEE_REJECTED
        assert rejected.application_stage_label == "Απόρριψη από Επιτροπή"
        assert rejected.stage_badge == "fail"
        assert rejected.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED
        assert rejected.beneficiary_label == "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"
        assert rejected.eligibility_label != ""

        list_html = staff_client.get(reverse("plot_applications:list")).content.decode()
        tbody = list_html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        assert "Απόρριψη από Επιτροπή" in tbody
        assert "Επιλαχών" in tbody

        resp = _page(staff_client, community)
        html = resp.content.decode()
        assert resp.context["is_final"] is True
        assert resp.context["movable_beneficiaries"] is False
        assert "data-final-list-revoke" in html
        assert "Πήρε οικόπεδο" in html and "Επιλαχών" in html

        detail = staff_client.get(
            reverse("plot_applications:detail", args=[apps["second"].pk])
        ).content.decode()
        assert "Επιλαχών: τα οικόπεδα δεν επαρκούν" in detail

        pdf = staff_client.get(
            reverse("plot_applications:prioritization_report_pdf"), {"community_id": community.pk}
        )
        assert pdf.status_code == 200

    def test_revoking_lists_moves_applications_back(self, community, committee_apps):
        apps = committee_apps
        preliminary = issue_preliminary_list(community, None)
        issue_final_list(community, None, today=preliminary.objection_deadline + timedelta(days=1))
        with pytest.raises(BeneficiaryListError):
            revoke_preliminary_list(community)

        revoke_final_list(community)
        _refresh(*apps.values())
        assert {app.application_stage for app in apps.values()} == {ApplicationStage.OBJECTIONS}

        revoke_preliminary_list(community)
        _refresh(*apps.values())
        assert {app.application_stage for app in apps.values()} == {ApplicationStage.PRIORITIZATION}
        assert not RankingEntry.objects.exists()
