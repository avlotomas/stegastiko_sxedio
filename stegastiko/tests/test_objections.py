"""Tests for Stage 3 (Objections Committee): objection scope, pending items, outcome emails, and final list emails."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from plot_applications.announcement_workflow import (
    AnnouncementWorkflowError,
    add_pending_requirement,
    decide_objection,
    issue_final_list_and_notify,
    record_applications_committee_decision,
    refresh_time_based_stages,
    register_objection,
    start_final_list,
    toggle_pending_requirement,
)
from plot_applications.beneficiary_lists import BeneficiaryListError
from plot_applications.models import (
    ApplicationStage,
    EligibilityOverride,
    Objection,
    PlotAllocationStatus,
    ResidenceCategory,
)
from plot_applications.prioritization import BENEFICIARIES, save_manual_order
from plot_applications.rules import apply_evaluation
from plots.models import Plot
from tests.test_plot_applications import (  # noqa: F401
    _application,
    available_plot,
    community,
    cycle,
    staff_client,
)


def _evaluated(cycle, **extra):
    app = _application(cycle, **extra)
    apply_evaluation(app)
    app.refresh_from_db()
    return app


@pytest.mark.django_db
class TestObjectionsCommitteeWorkflow:
    def test_objection_deadline_enforced_and_only_objectors_can_be_modified(
        self, staff_client, cycle
    ):
        ben1 = _evaluated(cycle, email="b1@example.org")
        ben2 = _evaluated(
            cycle,
            email="b2@example.org",
            residence_category=ResidenceCategory.REPATRIATED,
        )
        rejected = _evaluated(cycle, email="r1@example.org", has_dwelling=True)

        decided_on = date(2026, 10, 1)
        record_applications_committee_decision(cycle, decided_on=decided_on)

        # Submitting an objection after the 21-day deadline (Oct 22) is refused
        with pytest.raises(AnnouncementWorkflowError):
            register_objection(
                rejected,
                submitted_on=date(2026, 10, 25),
                grounds="Εκπρόθεσμη ένσταση",
            )

        # Registering within the 21-day window succeeds for `rejected`, while `ben1` and `ben2` have no objection
        obj = register_objection(
            rejected,
            submitted_on=date(2026, 10, 15),
            grounds="Το ακίνητο δεν είναι κατοικία.",
        )
        assert obj.objection_type == Objection.ObjectionType.REJECTION

        refresh_time_based_stages(cycle, today=date(2026, 10, 25))
        decide_objection(obj, Objection.Status.UPHELD, "Δεκτή.")
        start_final_list(cycle, today=date(2026, 10, 25))

        # Reordering non-objectors (`ben1` and `ben2`) is refused
        with pytest.raises(BeneficiaryListError):
            save_manual_order(cycle, BENEFICIARIES, [ben2.pk, ben1.pk])

        # Changing eligibility override on `ben1` (no objection) is refused
        staff_client.post(
            reverse("plot_applications:eligibility_override_save", args=[ben1.pk]),
            {
                "eligibility_override": EligibilityOverride.FAIL,
                "eligibility_override_reason": "Χωρίς ένσταση",
            },
        )
        ben1.refresh_from_db()
        assert ben1.eligibility_override == ""

        # Changing eligibility override on `rejected` (has registered objection) succeeds!
        staff_client.post(
            reverse("plot_applications:eligibility_override_save", args=[rejected.pk]),
            {
                "eligibility_override": EligibilityOverride.PASS,
                "eligibility_override_reason": "Δεκτή ένσταση (Ενότ. 7).",
            },
        )
        rejected.refresh_from_db()
        assert rejected.eligibility_override == EligibilityOverride.PASS
        assert rejected.is_beneficiary is True

    def test_pending_requirements_checkboxes_and_objection_outcome_emails(
        self, cycle, mailoutbox
    ):
        ben = _evaluated(cycle, email="ben@example.org")
        rej = _evaluated(cycle, email="rej@example.org", has_dwelling=True)
        record_applications_committee_decision(cycle, decided_on=date(2026, 10, 1))

        obj_upheld = register_objection(
            rej,
            submitted_on=date(2026, 10, 10),
            grounds="Προσκομίζω βεβαίωση ΤΚΧ.",
        )
        obj_dismissed = register_objection(
            ben,
            submitted_on=date(2026, 10, 12),
            grounds="Διαφωνώ με τη σειρά.",
        )
        refresh_time_based_stages(cycle, today=date(2026, 10, 25))
        mailoutbox.clear()

        # Request 2 extra items (checkboxes) for `rej`
        req1 = add_pending_requirement(
            rej, "Πρόσφατο πιστοποιητικό έρευνας ΤΚΧ", objection=obj_upheld
        )
        req2 = add_pending_requirement(
            rej, "Βεβαίωση Κοινοτικού Συμβουλίου", objection=obj_upheld
        )
        assert rej.is_pending_extra_info is True
        assert len(rej.open_pending_requirements) == 2

        # Cannot decide the objection or issue final list while any checkbox is unchecked
        with pytest.raises(AnnouncementWorkflowError):
            decide_objection(obj_upheld, Objection.Status.UPHELD, "Δεκτή")
        with pytest.raises(BeneficiaryListError):
            issue_final_list_and_notify(
                cycle, decided_on=date(2026, 10, 26)
            )

        # Check only the first checkbox -> still pending!
        toggle_pending_requirement(req1, True)
        assert rej.is_pending_extra_info is True
        assert [r.description for r in rej.open_pending_requirements] == [
            "Βεβαίωση Κοινοτικού Συμβουλίου"
        ]

        # Check the second checkbox -> no longer pending!
        toggle_pending_requirement(req2, True)
        assert rej.is_pending_extra_info is False

        # Decide both objections -> sends distinct emails
        decide_objection(
            obj_upheld,
            Objection.Status.UPHELD,
            decision_notes="Τεκμηριώθηκε η μη κατοχή κατοικίας.",
        )
        decide_objection(
            obj_dismissed,
            Objection.Status.DISMISSED,
            decision_notes="Η κατάταξη είναι ορθή.",
        )

        assert len(mailoutbox) == 2
        by_to = {m.to[0]: m for m in mailoutbox}
        assert "Ικανοποιήθηκε η ένστασή σας" in by_to["rej@example.org"].body
        assert "Δεν ικανοποιήθηκε η ένστασή σας" in by_to["ben@example.org"].body

    def test_final_list_sends_different_emails_to_plot_beneficiaries_and_runner_ups(
        self, community, cycle, available_plot, mailoutbox
    ):
        # Offer 2 plots on the announcement, and have 3 eligible beneficiaries + 1 rejected
        second_plot = Plot.objects.create(
            community=community,
            valuation_amount=Decimal("40000"),
            disposal_price=Decimal("10000"),
        )
        cycle.plots.add(second_plot)
        assert cycle.plots.count() == 2

        b1 = _evaluated(cycle, email="b1@example.org")
        b2 = _evaluated(
            cycle,
            email="b2@example.org",
            residence_category=ResidenceCategory.REPATRIATED,
        )
        b3 = _evaluated(
            cycle,
            email="b3@example.org",
            residence_category=ResidenceCategory.REPATRIATED,
        )
        rej = _evaluated(cycle, email="rej@example.org", has_dwelling=True)

        record_applications_committee_decision(cycle, decided_on=date(2026, 10, 1))
        mailoutbox.clear()

        result = issue_final_list_and_notify(cycle, decided_on=date(2026, 10, 25))
        assert [a.pk for a in result["sent_beneficiaries"]] == [b1.pk, b2.pk]
        assert [a.pk for a in result["sent_runner_ups"]] == [b3.pk]
        assert len(mailoutbox) == 3

        by_to = {m.to[0]: m for m in mailoutbox}
        assert "Δικαιούχος Οικοπέδου" in by_to["b1@example.org"].subject
        assert "Δικαιούχος Οικοπέδου" in by_to["b2@example.org"].subject
        assert "Επιλαχών" in by_to["b3@example.org"].subject
        assert "ΕΠΙΛΑΧΩΝ" in by_to["b3@example.org"].body

        b1.refresh_from_db()
        b3.refresh_from_db()
        rej.refresh_from_db()
        assert b1.application_stage == ApplicationStage.LOTTERY
        assert b1.plot_allocation_status == PlotAllocationStatus.ALLOCATED
        assert b3.plot_allocation_status == PlotAllocationStatus.RUNNER_UP
        assert rej.application_stage == ApplicationStage.COMMITTEE_REJECTED
