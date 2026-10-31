"""Στάδια 2–4 της γνωστοποίησης: ολοκλήρωση του Σταδίου 2 με την αποστολή του Προκαταρκτικού
Καταλόγου, ενστάσεις στο Στάδιο 3, κατάρτιση Τελικού Καταλόγου στο Στάδιο 4 (Ενότ. 6(β), 7)."""

import json
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from cases.models import SubmissionCycle
from plot_applications.announcement_workflow import (
    AnnouncementWorkflowError,
    ObjectionPeriodOpenError,
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
)
from plot_applications.models import ApplicationStage, Objection, ResidenceCategory
from plot_applications.prioritization import BENEFICIARIES
from tests.test_objections import _evaluated
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    available_plot,
    community,
    cycle,
    staff_client,
)


def _workspace(client, cycle):
    return client.get(reverse("announcements:detail", args=[cycle.pk])).content.decode()


@pytest.fixture
def apps(cycle):
    return {
        "first": _evaluated(cycle, email="b1@example.org"),
        "second": _evaluated(
            cycle, email="b2@example.org", residence_category=ResidenceCategory.REPATRIATED
        ),
        "rejected": _evaluated(cycle, email="r1@example.org", has_dwelling=True),
    }


@pytest.fixture
def notified_today(cycle, apps):
    """Ο Προκαταρκτικός Κατάλογος στάλθηκε σήμερα· η περίοδος ενστάσεων είναι ανοικτή."""
    record_applications_committee_decision(cycle, decided_on=timezone.localdate())
    cycle.refresh_from_db()
    return apps


@pytest.mark.django_db
class TestStageTwoEndsWithTheEmails:
    def test_sending_the_preliminary_list_moves_to_stage_three(self, cycle, notified_today):
        assert cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        notified_today["first"].refresh_from_db()
        assert notified_today["first"].application_stage == ApplicationStage.OBJECTIONS

    def test_stage_two_shows_only_the_preliminary_list_button_and_modal(
        self, staff_client, cycle, notified_today
    ):
        html = _workspace(staff_client, cycle)
        assert "data-open-preliminary-list" in html
        assert 'id="preliminary-list-dialog"' in html
        assert "data-issue-preliminary-and-email" not in html
        assert "data-stage2-prioritization" not in html
        assert "data-open-prioritization" not in html
        for app in notified_today.values():
            assert f'data-preliminary-email-row="{app.pk}"' in html
        assert "b1@example.org" in html
        assert "Απεστάλη" in html

    def test_preliminary_issued_without_emails_is_sent_from_stage_two(
        self, staff_client, community, cycle, apps, mailoutbox
    ):
        issued_on = timezone.localdate() - timedelta(days=3)
        issue_preliminary_list(community, None, today=issued_on)
        cycle.refresh_from_db()
        html = _workspace(staff_client, cycle)
        assert "data-preliminary-not-notified" in html
        assert "Αποστολή Email Προκαταρκτικού Καταλόγου" in html

        today = timezone.localdate()
        result = record_applications_committee_decision(cycle, decided_on=today)
        assert len(mailoutbox) == 3
        preliminary = result["ranking_list"]
        assert preliminary.notifications_sent_at is not None
        assert {entry.objection_deadline for entry in preliminary.entries.all()} == {
            today + timedelta(days=21)
        }
        with pytest.raises(AnnouncementWorkflowError):
            record_applications_committee_decision(cycle, decided_on=today)


@pytest.mark.django_db
class TestStageThreeShowsOnlyObjections:
    def test_list_is_locked_while_objections_are_examined(
        self, staff_client, community, cycle, notified_today
    ):
        apps = notified_today
        register_objection(apps["second"], grounds="Διαφωνώ με τη σειρά.")
        response = staff_client.post(
            reverse("plot_applications:prioritization_reorder"),
            data=json.dumps(
                {
                    "community_id": community.pk,
                    "group": BENEFICIARIES,
                    "order": [apps["second"].pk, apps["first"].pk],
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "Στάδιο 4" in response.json()["message"]

        page = staff_client.get(
            reverse("plot_applications:prioritization"), {"community_id": community.pk}
        )
        assert page.context["can_reorder"] is False
        assert all(row.locked for row in page.context["prioritization"].beneficiaries)

        html = _workspace(staff_client, cycle)
        assert "data-register-objection-form" in html
        assert "data-final-list-changes" not in html
        assert "data-issue-final-and-email" not in html

    def test_moving_to_the_final_list_requires_decided_objections(self, cycle, notified_today):
        register_objection(notified_today["rejected"], grounds="Δεν έχω κατοικία.")
        with pytest.raises(BeneficiaryListError, match="χωρίς απόφαση"):
            start_final_list(cycle, accept_open_period=True)


@pytest.mark.django_db
class TestObjectionPeriodWarning:
    def test_open_period_needs_an_explicit_accept(self, staff_client, cycle, notified_today):
        html = _workspace(staff_client, cycle)
        assert "data-objection-period-warning" in html
        assert "data-accept-open-period" in html

        with pytest.raises(ObjectionPeriodOpenError):
            start_final_list(cycle)

        staff_client.post(reverse("announcements:start_final_list", args=[cycle.pk]))
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE

        staff_client.post(
            reverse("announcements:start_final_list", args=[cycle.pk]),
            {"accept_open_period": "1"},
        )
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.FINAL_LIST
        assert cycle.objections_closed_early is True
        assert cycle.objections_closed_on == timezone.localdate()

    def test_after_accepting_the_final_list_is_issued_before_the_deadline(
        self, staff_client, cycle, notified_today
    ):
        objection = register_objection(notified_today["rejected"], grounds="Δεν έχω κατοικία.")
        decide_objection(objection, Objection.Status.DISMISSED, "Απορρίφθηκε.")
        start_final_list(cycle, accept_open_period=True)

        with pytest.raises(AnnouncementWorkflowError):
            register_objection(notified_today["first"], grounds="Αργή ένσταση.")

        html = _workspace(staff_client, cycle)
        assert "data-objections-closed-early" in html
        assert "data-open-final-list" in html
        assert "data-final-list-objections" in html
        assert "data-register-objection-form" not in html
        assert "data-decide-objection-form" not in html

        page = staff_client.get(
            reverse("plot_applications:prioritization"),
            {"community_id": cycle.community.pk, "list": "final"},
        )
        assert page.context["can_reorder"] is True
        assert "data-final-list-objections" in page.content.decode()

        issue_final_list_and_notify(cycle)
        cycle.refresh_from_db()
        assert community_lists(cycle).final is not None
        assert cycle.stage == SubmissionCycle.Stage.LOTTERY

    def test_closed_period_moves_without_warning(self, cycle, apps):
        record_applications_committee_decision(cycle, decided_on=date(2026, 9, 1))
        start_final_list(cycle, today=date(2026, 9, 30))
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.FINAL_LIST
        assert cycle.objections_closed_early is False


@pytest.mark.django_db
class TestAnnouncementEmailsPerStage:
    def test_sent_emails_are_visible_per_stage_with_sender_recipient_and_full_text(
        self, staff_client, cycle, available_plot, apps
    ):
        from datetime import datetime

        from django.contrib.auth import get_user_model
        from core.services import set_setting
        from plot_applications.announcement_workflow import (
            complete_lottery,
            invite_to_agreement,
            record_lottery_result,
            schedule_lottery,
        )
        from plot_applications.beneficiary_lists import announcement_communications
        from plot_applications.services import send_plot_application_email

        set_setting("smtpHost", "smtp.example.org")
        set_setting("smtpFromEmail", "stegastiko@example.org")
        User = get_user_model()
        officer = User.objects.get(username="supervisor")
        officer.first_name = "Νίκη"
        officer.last_name = "Παπαδοπούλου"
        officer.save()

        # Stage 2 (Υποβολή αιτήσεων): send a custom application email
        send_plot_application_email(
            apps["first"],
            "Επιβεβαίωση δικαιολογητικών",
            "Αγαπητέ αιτητή, παραλάβαμε τα δικαιολογητικά σας.",
            user=officer,
        )

        # Stage 3 (Επιτροπή Εξέτασης Αιτήσεων): send Preliminary List emails
        record_applications_committee_decision(
            cycle, decided_on=date(2026, 10, 1), user=officer
        )

        # Stage 4 (Ενστάσεις): register and decide an objection -> sends outcome email
        objection = register_objection(
            apps["rejected"],
            submitted_on=date(2026, 10, 5),
            grounds="Δεν κατέχω κατοικία.",
        )
        decide_objection(
            objection,
            Objection.Status.UPHELD,
            decision_notes="Έγινε δεκτή η ένσταση με βάση τη βεβαίωση ΤΚΧ.",
            decided_on=date(2026, 10, 10),
            user=officer,
        )

        # Stage 5 (Τελικός Κατάλογος Δικαιούχων): issue Final List & notify beneficiaries/runner-ups
        start_final_list(cycle, accept_open_period=True, today=date(2026, 10, 12))
        issue_final_list_and_notify(
            cycle, user=officer, decided_on=date(2026, 10, 15)
        )

        # Stage 6 (Στάδιο κλήρωσης): schedule lottery -> sends invitation email
        schedule_lottery(
            cycle,
            datetime(2026, 10, 20, 10, 30),
            "Επαρχιακή Διοίκηση Λευκωσίας",
            user=officer,
        )
        allocations = record_lottery_result(cycle, {apps["first"]: available_plot})
        complete_lottery(cycle)

        # Stage 7 (Υπογραφή συμφωνίας και πληρωμή): invite to agreement -> sends invitation email
        invite_to_agreement(
            allocations[0],
            appointment_at=datetime(2026, 10, 25, 9, 30),
            deadline=date(2026, 11, 5),
            location="Γραφεία Επαρχιακής Διοίκησης",
            user=officer,
        )

        all_emails, by_stage = announcement_communications(cycle)
        assert len(by_stage["submission"]) == 1
        assert len(by_stage["applications_committee"]) == 3
        assert len(by_stage["objections_committee"]) == 1
        assert len(by_stage["final_list"]) == 2
        assert len(by_stage["lottery"]) == 1
        assert len(by_stage["agreements"]) == 1
        assert len(all_emails) == 9
        assert all("Νίκη Παπαδοπούλου (supervisor)" == item.sender_label for item in all_emails)

        # Verify each stage tab renders its stage-specific emails card with sender, recipient & full body
        stage_expectations = {
            "submission": ("b1@example.org", "Αγαπητέ αιτητή, παραλάβαμε τα δικαιολογητικά σας."),
            "applications_committee": ("b1@example.org", "Σας γνωστοποιούμε ότι η αίτησή σας"),
            "objections_committee": ("r1@example.org", "Έγινε δεκτή η ένσταση με βάση τη βεβαίωση ΤΚΧ."),
            "final_list": ("b2@example.org", "κατατάχθηκε στη θέση 2 ως ΕΠΙΛΑΧΩΝ"),
            "lottery": ("b1@example.org", "Επαρχιακή Διοίκηση Λευκωσίας"),
            "agreements": ("b1@example.org", "Γραφεία Επαρχιακής Διοίκησης"),
        }
        for stage_code, (expected_recipient, expected_body_snippet) in stage_expectations.items():
            resp = staff_client.get(
                reverse("announcements:detail", args=[cycle.pk]), {"stage": stage_code}
            )
            assert resp.status_code == 200
            html = resp.content.decode()
            assert f'data-stage-emails-card="{stage_code}"' in html
            assert "Νίκη Παπαδοπούλου (supervisor)" in html
            assert expected_recipient in html
            assert expected_body_snippet in html
            assert 'id="announcement-emails-dialog"' in html

        # Στάδιο 1 (Στοιχεία γνωστοποίησης) has no emails, so no emails card
        details_html = staff_client.get(
            reverse("announcements:detail", args=[cycle.pk]), {"stage": "details"}
        ).content.decode()
        assert "data-stage-emails-card" not in details_html
        # ... and no Στάδιο 1 group in the «Απεσταλμένα Email» dialog of the other stages
        submission_html = staff_client.get(
            reverse("announcements:detail", args=[cycle.pk]), {"stage": "submission"}
        ).content.decode()
        assert 'data-announcement-emails-stage-group="submission"' in submission_html
        assert 'data-announcement-emails-stage-group="details"' not in submission_html

        # Also verify the individual application detail page and JSON modal endpoint return sender + stage
        app_detail_html = staff_client.get(
            reverse("plot_applications:detail", args=[apps["first"].pk])
        ).content.decode()
        assert "Νίκη Παπαδοπούλου (supervisor)" in app_detail_html
        assert "3. Επιτροπή Εξέτασης Αιτήσεων" in app_detail_html
        assert "5. Τελικός Κατάλογος Δικαιούχων" in app_detail_html

        first_comm = by_stage["applications_committee"][0].communication
        json_resp = staff_client.get(
            reverse(
                "plot_applications:communication_detail",
                args=[first_comm.object_id, first_comm.pk],
            ),
            HTTP_ACCEPT="application/json",
        )
        assert json_resp.status_code == 200
        payload = json_resp.json()
        assert payload["sender"] == "Νίκη Παπαδοπούλου (supervisor)"
        assert payload["stage_label"] == "3. Επιτροπή Εξέτασης Αιτήσεων"
        assert payload["recipient"] == first_comm.recipient
        assert payload["body"] == first_comm.body
