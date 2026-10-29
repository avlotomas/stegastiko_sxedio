"""Ροή 7 σταδίων της γνωστοποίησης: καρτέλες ανά στάδιο, Στάδιο 1 πάντα επεξεργάσιμο, κλείδωμα
αιτήσεων μετά την προθεσμία υποβολής, πρόωρη μετάβαση στο Στάδιο 3 και πίνακας ελέγχου (Ενότ. 4, 5)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from allocation.models import Allocation
from cases.models import SubmissionCycle
from core.views import submission_deadlines
from plot_applications.announcement_workflow import (
    SubmissionPeriodOpenError,
    record_applications_committee_decision,
    start_applications_committee,
)
from plot_applications.models import PlotApplication
from plots.models import Plot
from tests.fixtures.cycles import make_cycle
from tests.test_objections import _evaluated
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    _post_data,
    available_plot,
    community,
    cycle,
    staff_client,
)


def _detail(client, cycle, **params):
    return client.get(reverse("announcements:detail", args=[cycle.pk]), params)


def _expired_cycle(community):
    """Γνωστοποίηση της οποίας η προθεσμία υποβολής έληξε πριν από 40 ημέρες περίπου."""
    plot = Plot.objects.create(
        community=community, valuation_amount=Decimal("40000"), disposal_price=Decimal("10000")
    )
    return make_cycle(
        community,
        plots=[plot],
        announcement_date=timezone.localdate() - timedelta(days=70),
        submission_months=1,
        published_at=timezone.now(),
    )


@pytest.mark.django_db
class TestStageTabs:
    def test_unpublished_announcement_starts_at_stage_one(self, community):
        draft = make_cycle(community, announcement_date=timezone.localdate())
        assert draft.stage == SubmissionCycle.Stage.DETAILS
        draft.published_at = timezone.now()
        draft.save()
        assert draft.stage == SubmissionCycle.Stage.SUBMISSION

    def test_current_stage_is_the_default_and_future_stages_fall_back(self, staff_client, cycle):
        response = _detail(staff_client, cycle)
        assert response.context["selected_stage"] == "submission"
        assert "data-announcement-summary-header" in response.content.decode()

        assert _detail(staff_client, cycle, stage="lottery").context["selected_stage"] == "submission"

        details = _detail(staff_client, cycle, stage="details")
        assert details.context["selected_stage"] == "details"
        assert "data-announcement-summary-header" not in details.content.decode()

        steps = {step["code"]: step for step in response.context["stage_stepper"]}
        assert steps["details"]["available"] and steps["details"]["done"]
        assert steps["submission"]["current"]
        assert not steps["final_list"]["available"]
        assert f'?stage=details' in response.content.decode()

    def test_stage_four_has_the_modal_buttons(self, staff_client, cycle):
        _evaluated(cycle, email="b1@example.org")
        record_applications_committee_decision(cycle, decided_on=timezone.localdate())
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        html = _detail(staff_client, cycle).content.decode()
        assert "data-objections-modals-toolbar" in html
        assert "data-open-preliminary-list" in html
        assert "data-open-applications-modal" in html
        assert "data-open-announcement-details-modal" in html
        assert 'id="applications-dialog"' in html
        assert 'id="announcement-details-dialog"' in html
        assert 'data-ui-suffix=" (1)"' in html
        assert '<span data-ui-text>λήξη</span>' in html
        assert "4. Ενστάσεις (Ενότ. 7)" in html
        assert '<h2 class="card__title" style="margin-bottom: 0;" data-ui-skip>' not in html



@pytest.mark.django_db
class TestStageOneStaysEditable:
    def _post(self, client, cycle, plots, announcement_date="2026-09-18", months="12"):
        return client.post(
            reverse("announcements:detail", args=[cycle.pk]),
            {
                "cycle-plots": [plot.pk for plot in plots],
                "cycle-announcement_date": announcement_date,
                "cycle-submission_months": months,
            },
        )

    def test_an_allocated_plot_cannot_be_removed(self, staff_client, community, cycle, available_plot):
        extra = Plot.objects.create(
            community=community, valuation_amount=Decimal("40000"), disposal_price=Decimal("10000")
        )
        cycle.plots.add(extra)
        application = _evaluated(cycle)
        Allocation.objects.create(application=application, parcel=available_plot)

        response = self._post(staff_client, cycle, [extra])
        assert response.status_code == 400
        assert "έχει ήδη δοθεί σε αιτητή" in response.content.decode()
        assert set(cycle.plots.all()) == {available_plot, extra}

        assert self._post(staff_client, cycle, [available_plot]).status_code == 302
        assert list(cycle.plots.all()) == [available_plot]

    def test_the_period_must_cover_the_existing_applications(self, staff_client, cycle, available_plot):
        _evaluated(cycle)
        response = self._post(staff_client, cycle, [available_plot], announcement_date="2026-10-05")
        assert response.status_code == 400
        assert "πρέπει να καλύπτει τις ημερομηνίες υποβολής" in response.content.decode()
        cycle.refresh_from_db()
        assert cycle.announcement_date.isoformat() == "2026-09-18"


@pytest.mark.django_db
class TestSubmissionDeadline:
    def test_new_applications_are_refused_after_the_deadline(self, staff_client, community):
        expired = _expired_cycle(community)
        submitted_on = (expired.announcement_date + timedelta(days=5)).isoformat()
        response = staff_client.post(
            reverse("plot_applications:create"),
            _post_data(expired, **{"main-submitted_on": submitted_on}),
        )
        assert response.status_code == 200
        assert "Η προθεσμία υποβολής αιτήσεων της γνωστοποίησης έληξε" in response.content.decode()
        assert not PlotApplication.objects.filter(announcement=expired).exists()

    def test_applications_cannot_be_edited_after_the_deadline(self, staff_client, community):
        expired = _expired_cycle(community)
        application = _evaluated(
            expired, submitted_on=expired.announcement_date + timedelta(days=5)
        )
        response = staff_client.get(reverse("plot_applications:edit", args=[application.pk]))
        assert response.status_code == 302
        assert response["Location"] == reverse("plot_applications:detail", args=[application.pk])
        assert application.submission_locked
        detail = staff_client.get(response["Location"]).content.decode()
        assert reverse("plot_applications:edit", args=[application.pk]) not in detail

    def test_open_period_needs_acceptance_to_move_to_stage_three(self, staff_client, cycle):
        _evaluated(cycle)
        today = timezone.localdate()
        with pytest.raises(SubmissionPeriodOpenError):
            start_applications_committee(cycle, today=today)

        url = reverse("announcements:start_committee", args=[cycle.pk])
        staff_client.post(url, {})
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.SUBMISSION

        html = _detail(staff_client, cycle).content.decode()
        assert "data-submission-period-warning" in html
        assert "data-accept-open-submission" in html

        staff_client.post(url, {"accept_open_submission": "1"})
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
        assert cycle.submission_closed_early is True
        assert not cycle.submission_open()


@pytest.mark.django_db
class TestDashboard:
    def test_deadline_card_lists_open_announcements(self, staff_client, cycle):
        html = staff_client.get(reverse("home")).content.decode()
        assert "data-submission-deadlines-card" in html
        assert "data-submission-deadline-row" in html
        assert "data-submission-deadline-alert" not in html
        assert 'class="tile-grid"' not in html
        assert "data-dashboard-kpis" in html
        assert 'data-kpi-card="cases"' in html
        assert 'data-kpi-card="plots"' in html
        assert 'data-kpi-card="announcements"' in html
        assert 'data-kpi-card="allocations"' in html
        assert "data-dashboard-announcements-pipeline" in html
        assert f'data-dashboard-announcement-row="{cycle.pk}"' in html
        assert "data-dashboard-cases-pipeline" in html

    def test_warning_x_days_before_the_deadline(self, staff_client, community, cycle):
        rows = submission_deadlines(today=cycle.submission_end_date - timedelta(days=3))
        assert [(row["days_remaining"], row["warning"]) for row in rows] == [(3, True)]

        near = make_cycle(
            community,
            announcement_date=timezone.localdate() - timedelta(days=25),
            submission_months=1,
            published_at=timezone.now(),
        )
        assert 0 <= near.submission_days_remaining() <= 14
        html = staff_client.get(reverse("home")).content.decode()
        assert "data-submission-deadline-alert" in html
        assert "Λήγει" in html or "λήγει" in html
