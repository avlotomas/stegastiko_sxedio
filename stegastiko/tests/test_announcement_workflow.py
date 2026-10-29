"""Tests for the 5-stage announcement-driven workflow (Stages 1–2–3, Sect. 4, 5, 6, 7)."""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from cases.models import SubmissionCycle
from core.models import Community
from plot_applications.announcement_workflow import (
    confirm_letter_receipt,
    record_applications_committee_decision,
    refresh_time_based_stages,
    start_applications_committee,
)
from plot_applications.beneficiary_lists import BeneficiaryListError
from plot_applications.models import (
    ApplicationStage,
    ResidenceCategory,
)
from plot_applications.rules import apply_evaluation
from plots.models import Plot
from tests.fixtures.cycles import make_cycle
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


def _incomplete(cycle):
    app = _application(cycle)
    app.attached_documents = []
    apply_evaluation(app)
    app.refresh_from_db()
    return app


@pytest.mark.django_db
class TestAnnouncementWorkflowStages:
    def test_announcement_is_parent_of_applications_and_single_community_plots(
        self, community
    ):
        other = Community.objects.create(
            district="ΛΕΥΚΩΣΙΑΣ",
            name="ΑΛΛΗ",
            contact_email="other@example.org",
            community_folder_code="099",
        )
        p1 = Plot.objects.create(
            community=community, valuation_amount=Decimal("40000"), disposal_price=Decimal("10000")
        )
        p2 = Plot.objects.create(
            community=other, valuation_amount=Decimal("40000"), disposal_price=Decimal("10000")
        )
        ann = make_cycle(
            community,
            plots=[p1],
            announcement_date=date(2026, 9, 1),
            submission_months=1,
            published_at=timezone.now(),
        )
        assert ann.community == community
        with pytest.raises(ValidationError):
            with transaction.atomic():
                ann.plots.add(p2)

        app1 = _evaluated(ann)
        app2 = _evaluated(ann)
        assert set(ann.applications.all()) == {app1, app2}
        assert app1.announcement == ann
        assert app1.community == community

    def test_stage1_to_stage2_requires_all_applications_complete_or_rejected(
        self, cycle
    ):
        complete_app = _evaluated(cycle)
        incomplete_app = _incomplete(cycle)

        with pytest.raises(BeneficiaryListError):
            start_applications_committee(cycle, meeting_date=date(2026, 10, 25))

        # Reject the incomplete application by officer
        incomplete_app.incomplete_rejected = True
        incomplete_app.incomplete_rejection_reason = "Ελλιπή δικαιολογητικά"
        incomplete_app.incomplete_rejected_on = date(2026, 10, 20)
        apply_evaluation(incomplete_app)

        start_applications_committee(cycle, meeting_date=date(2026, 10, 25))
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
        assert cycle.applications_committee_date == date(2026, 10, 25)
        assert complete_app.application_stage == ApplicationStage.PRIORITIZATION

    def test_stage2_committee_decision_sends_emails_and_tracks_postal_only(
        self, cycle, mailoutbox
    ):
        ben1 = _evaluated(cycle, email="ben1@example.org")
        ben2 = _evaluated(
            cycle,
            email="ben2@example.org",
            residence_category=ResidenceCategory.REPATRIATED,
        )
        rejected = _evaluated(cycle, email="rej@example.org", has_dwelling=True)
        postal_app = _evaluated(cycle, email="temp@example.org", has_dwelling=True)
        postal_app.email = ""
        postal_app.save(update_fields=["email"])

        decided_date = date(2026, 11, 1)
        result = record_applications_committee_decision(cycle, decided_on=decided_date)

        assert len(result["sent"]) == 3
        assert [a.pk for a in result["postal_only"]] == [postal_app.pk]
        assert len(mailoutbox) == 3

        by_to = {msg.to[0]: msg for msg in mailoutbox}
        assert "ΔΙΚΑΙΟΥΧΟΣ" in by_to["ben1@example.org"].body
        assert "σειρά προτεραιότητας 1" in by_to["ben1@example.org"].body
        assert "ΔΙΚΑΙΟΥΧΟΣ" in by_to["ben2@example.org"].body
        assert "σειρά προτεραιότητας 2" in by_to["ben2@example.org"].body
        assert "ΜΗ ΔΙΚΑΙΟΥΧΟΣ" in by_to["rej@example.org"].body

        for app in (ben1, ben2, rejected):
            app.refresh_from_db()
            assert app.application_stage == ApplicationStage.OBJECTIONS

    def test_receipt_confirmation_within_5_days_shifts_21_day_deadline_and_auto_advances(
        self, cycle
    ):
        app1 = _evaluated(cycle, email="a1@example.org")
        app2 = _evaluated(cycle, email="a2@example.org")
        decided_date = date(2026, 11, 1)
        result = record_applications_committee_decision(cycle, decided_on=decided_date)
        prelim = result["ranking_list"]

        entry1 = prelim.entries.get(application=app1)
        entry2 = prelim.entries.get(application=app2)
        assert entry1.objection_deadline == date(2026, 11, 22)

        # Confirm within 5 days (day +4 -> deadline becomes Nov 5 + 21 = Nov 26)
        confirm_letter_receipt(entry1, date(2026, 11, 5))
        entry1.refresh_from_db()
        assert entry1.objection_deadline == date(2026, 11, 26)

        # Confirm after 5 days (day +8 -> per Sect. 6 receipt date stays dispatch date Nov 1 -> Nov 22)
        confirm_letter_receipt(entry2, date(2026, 11, 9))
        entry2.refresh_from_db()
        assert entry2.objection_deadline == date(2026, 11, 22)

        # Sending the letters completes Stage 2; the objection window is open in Stage 3.
        cycle.refresh_from_db()
        app1.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        assert app1.application_stage == ApplicationStage.OBJECTIONS

        # On Nov 25, entry1's objection window is still open -> stays open
        assert refresh_time_based_stages(cycle, today=date(2026, 11, 25)) is False
        cycle.refresh_from_db()
        assert cycle.objections_closed_on is None

        # On Nov 27, all deadlines have passed -> the objection period closes
        assert refresh_time_based_stages(cycle, today=date(2026, 11, 27)) is True
        cycle.refresh_from_db()
        app1.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        assert cycle.objections_closed_on == date(2026, 11, 27)
        assert not cycle.objections_closed_early
        assert app1.application_stage == ApplicationStage.OBJECTIONS_COMMITTEE

    def test_advance_announcements_management_command(self, cycle):
        app = _evaluated(cycle, email="cmd@example.org")
        record_applications_committee_decision(
            cycle, decided_on=timezone.localdate() - timedelta(days=30)
        )
        out = StringIO()
        call_command("advance_announcements", stdout=out)
        assert "Ενημερώθηκαν 1 γνωστοποιήσεις" in out.getvalue()
        cycle.refresh_from_db()
        app.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        assert app.application_stage == ApplicationStage.OBJECTIONS_COMMITTEE
