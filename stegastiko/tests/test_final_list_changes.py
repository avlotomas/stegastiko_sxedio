"""Προκαταρκτικός Κατάλογος «παγωμένος» μετά τη γνωστοποίηση, Τελικός Κατάλογος υπό κατάρτιση και
αλλαγές έναντι του Προκαταρκτικού (Ενότ. 6(β), 7)."""

import json
from datetime import date

import pytest
from django.urls import reverse

from allocation.models import RankingList
from plot_applications.announcement_workflow import (
    decide_objection,
    issue_final_list_and_notify,
    record_applications_committee_decision,
    register_objection,
    start_final_list,
)
from plot_applications.beneficiary_lists import (
    BeneficiaryListError,
    community_lists,
    issue_preliminary_list,
    list_changes,
    revoke_preliminary_list,
)
from plot_applications.models import EligibilityOverride, Objection, ResidenceCategory
from plot_applications.prioritization import BENEFICIARIES
from tests.test_objections import _evaluated
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    available_plot,
    community,
    cycle,
    staff_client,
)

DECIDED_ON = date(2026, 10, 1)
AFTER_DEADLINE = date(2026, 10, 25)


def _page(client, community, list_view=None):
    params = {"community_id": community.pk}
    if list_view:
        params["list"] = list_view
    return client.get(reverse("plot_applications:prioritization"), params)


def _ids(rows):
    return [row.application.pk for row in rows]


def _reorder(client, community, order):
    return client.post(
        reverse("plot_applications:prioritization_reorder"),
        data=json.dumps({"community_id": community.pk, "group": BENEFICIARIES, "order": order}),
        content_type="application/json",
    )


@pytest.fixture
def notified(cycle):
    """Δύο δικαιούχοι και ένας μη δικαιούχος, με Προκαταρκτικό Κατάλογο που γνωστοποιήθηκε (Ενότ. 6(β))."""
    first = _evaluated(cycle, email="b1@example.org")
    second = _evaluated(
        cycle, email="b2@example.org", residence_category=ResidenceCategory.REPATRIATED
    )
    rejected = _evaluated(cycle, email="r1@example.org", has_dwelling=True)
    record_applications_committee_decision(cycle, decided_on=DECIDED_ON)
    return {"first": first, "second": second, "rejected": rejected}


def _uphold_objections(client, apps):
    rank_objection = register_objection(
        apps["second"], submitted_on=date(2026, 10, 10), grounds="Διαφωνώ με τη σειρά."
    )
    rejection_objection = register_objection(
        apps["rejected"], submitted_on=date(2026, 10, 12), grounds="Δεν έχω κατοικία."
    )
    decide_objection(rank_objection, Objection.Status.UPHELD, "Δεκτή η ένσταση σειράς.")
    decide_objection(rejection_objection, Objection.Status.UPHELD, "Τεκμηριώθηκε.")
    start_final_list(apps["rejected"].announcement, today=AFTER_DEADLINE)
    client.post(
        reverse("plot_applications:eligibility_override_save", args=[apps["rejected"].pk]),
        {
            "eligibility_override": EligibilityOverride.PASS,
            "eligibility_override_reason": "Δεκτή ένσταση (Ενότ. 7).",
        },
    )


@pytest.mark.django_db
class TestPreliminaryListIsFrozen:
    def test_notified_preliminary_list_cannot_be_revoked(self, staff_client, community, notified):
        preliminary = community_lists(community).preliminary
        assert preliminary.notifications_sent_at is not None

        with pytest.raises(BeneficiaryListError):
            revoke_preliminary_list(community)
        staff_client.post(
            reverse("plot_applications:preliminary_list_revoke"), {"community_id": community.pk}
        )
        assert RankingList.objects.filter(pk=preliminary.pk).exists()

        html = _page(staff_client, community).content.decode()
        assert "data-preliminary-list-revoke" not in html
        assert "data-preliminary-list-issue" not in html
        assert "data-preliminary-locked" in html

    def test_preliminary_list_with_objections_cannot_be_revoked(self, community, cycle):
        app = _evaluated(cycle, has_dwelling=True)
        issue_preliminary_list(community, None, today=DECIDED_ON)
        register_objection(app, submitted_on=date(2026, 10, 5), grounds="Ένσταση.")
        with pytest.raises(BeneficiaryListError):
            revoke_preliminary_list(community)

    def test_software_order_reset_is_refused_after_the_preliminary_list(
        self, staff_client, community, notified
    ):
        assert "Επαναφορά σειράς λογισμικού" not in _page(staff_client, community).content.decode()
        staff_client.post(
            reverse("plot_applications:prioritization_reset"), {"community_id": community.pk}
        )
        assert not any(
            app.priority_rank
            for app in community_lists(community).cycle.applications.all()
        )


@pytest.mark.django_db
class TestFinalListChanges:
    def test_upheld_objections_change_the_final_draft_not_the_preliminary(
        self, staff_client, community, notified
    ):
        apps = notified
        _uphold_objections(staff_client, apps)

        resp = _reorder(staff_client, community, [apps["second"].pk, apps["first"].pk])
        assert resp.status_code == 200 and resp.json()["ok"] is True

        final_draft = _page(staff_client, community).context
        assert final_draft["list_view"] == "final"
        beneficiaries = final_draft["prioritization"].beneficiaries
        assert _ids(beneficiaries)[0] == apps["second"].pk
        assert apps["rejected"].pk in _ids(beneficiaries)
        assert {row.application.pk: row.locked for row in beneficiaries} == {
            apps["first"].pk: True,
            apps["second"].pk: False,
            apps["rejected"].pk: False,
        }

        preliminary = _page(staff_client, community, "preliminary").context["prioritization"]
        assert _ids(preliminary.beneficiaries) == [apps["first"].pk, apps["second"].pk]
        assert _ids(preliminary.others) == [apps["rejected"].pk]
        assert preliminary.others[0].list_status == "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"
        assert not any("Χειροκίνητη" in reason for reason in preliminary.others[0].reasons)

        changes = {
            change.application.pk: change
            for change in _page(staff_client, community, "changes").context["changes"]
        }
        assert changes[apps["second"].pk].kind == "Αλλαγή θέσης"
        assert changes[apps["second"].pk].final_text.startswith("ΔΙΚΑΙΟΥΧΟΣ — θέση 1")
        assert changes[apps["rejected"].pk].kind == "Αλλαγή αποτελέσματος"
        assert changes[apps["rejected"].pk].preliminary_text == "ΜΗ ΔΙΚΑΙΟΥΧΟΣ"
        assert any("Ικανοποιήθηκε" in reason for reason in changes[apps["rejected"].pk].reasons)
        assert changes[apps["first"].pk].is_direct is False

    def test_non_objectors_keep_their_order_and_the_reason_is_returned(
        self, staff_client, community, notified
    ):
        apps = notified
        objection = register_objection(
            apps["rejected"], submitted_on=date(2026, 10, 12), grounds="Δεν έχω κατοικία."
        )
        decide_objection(objection, Objection.Status.DISMISSED, "Απορρίφθηκε.")
        start_final_list(apps["rejected"].announcement, today=AFTER_DEADLINE)
        resp = _reorder(staff_client, community, [apps["second"].pk, apps["first"].pk])
        assert resp.status_code == 400
        assert "ένσταση" in resp.json()["message"]
        assert "data-row-locked" in _page(staff_client, community).content.decode()

    def test_preliminary_final_and_changes_stay_visible_after_the_final_list(
        self, staff_client, community, cycle, notified
    ):
        apps = notified
        _uphold_objections(staff_client, apps)
        _reorder(staff_client, community, [apps["second"].pk, apps["first"].pk])
        before = {change.application.pk: change.kind for change in list_changes(community_lists(community))}

        issue_final_list_and_notify(cycle, decided_on=date(2026, 10, 25))
        state = community_lists(community)
        assert state.final.notifications_sent_at is not None

        after = {change.application.pk: change.kind for change in list_changes(state)}
        assert after == before

        preliminary = _page(staff_client, community, "preliminary").context["prioritization"]
        assert _ids(preliminary.beneficiaries) == [apps["first"].pk, apps["second"].pk]
        final = _page(staff_client, community, "final").context
        assert final["is_final"] is True and final["can_reorder"] is False
        assert _ids(final["prioritization"].beneficiaries)[0] == apps["second"].pk

        workspace = staff_client.get(
            reverse("announcements:detail", args=[cycle.pk]), {"stage": "final_list"}
        ).content.decode()
        assert "data-final-list-changes" in workspace
        assert apps["rejected"].protocol_number in workspace

    def test_pdf_exports_the_selected_list(self, staff_client, community, notified):
        url = reverse("plot_applications:prioritization_report_pdf")
        draft = staff_client.get(url, {"community_id": community.pk})
        assert draft.status_code == 200
        assert "schedio_telikou_katalogou_dikaiouchon_007.pdf" in draft["Content-Disposition"]
        preliminary = staff_client.get(url, {"community_id": community.pk, "list": "preliminary"})
        assert "prokatarktikos_katalogos_dikaiouchon_007.pdf" in preliminary["Content-Disposition"]
