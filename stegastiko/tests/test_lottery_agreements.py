"""Tests for Stage 4 (Manual Plot Lottery) and Stage 5 (Agreement .docx, Payment, Forfeiture & Runner-up Promotion)."""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document

from allocation.models import Agreement, AgreementTemplate, Payment
from cases.models import SubmissionCycle
from core.configuration_forms import AgreementTemplateUploadForm
from core.docx_merge import render_agreement_docx, validate_agreement_template_file
from plot_applications.announcement_workflow import (
    AnnouncementWorkflowError,
    complete_lottery,
    forfeit_allocation,
    invite_to_agreement,
    issue_final_list_and_notify,
    promote_runner_up,
    record_applications_committee_decision,
    record_lottery_result,
    record_signature_and_payment,
    schedule_lottery,
)
from plot_applications.models import (
    ApplicationStage,
    PlotAllocationStatus,
    ResidenceCategory,
)
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


def _make_docx_bytes(*paragraphs: str) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.django_db
class TestLotteryAndAgreements:
    def test_manual_lottery_and_agreement_docx_and_forfeit_runner_up_flow(
        self, community, cycle, available_plot, mailoutbox
    ):
        available_plot.design_number = "ΟΙΚ-101"
        available_plot.parcel_number = "455"
        available_plot.sheet_plan = "21/04"
        available_plot.final_area_sqm = Decimal("350.00")
        available_plot.save()

        # 1 plot, 3 beneficiaries (1 gets plot, 2 runner-ups)
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

        record_applications_committee_decision(cycle, decided_on=date(2026, 10, 1))
        issue_final_list_and_notify(cycle, decided_on=date(2026, 10, 25))
        mailoutbox.clear()

        # Stage 4: Schedule lottery -> sends invitation to top-N beneficiary (`b1`)
        sched = schedule_lottery(
            cycle,
            datetime(2026, 11, 2, 10, 30),
            "Επαρχιακή Διοίκηση Λευκωσίας",
        )
        assert [a.pk for a in sched["sent"]] == [b1.pk]
        assert len(mailoutbox) == 1
        assert "Επαρχιακή Διοίκηση Λευκωσίας" in mailoutbox[0].body

        # Cannot complete lottery before recording result
        with pytest.raises(AnnouncementWorkflowError):
            complete_lottery(cycle)

        # Record manual lottery result for `b1`
        allocations = record_lottery_result(cycle, {b1: available_plot})
        assert len(allocations) == 1
        alloc1 = allocations[0]
        assert alloc1.parcel == available_plot
        assert alloc1.payment.amount == Decimal("10000.00")

        complete_lottery(cycle)
        cycle.refresh_from_db()
        b1.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.AGREEMENTS
        assert b1.application_stage == ApplicationStage.AGREEMENT

        # Stage 5: Invite `b1` to sign agreement and pay
        mailoutbox.clear()
        invite_to_agreement(
            alloc1,
            appointment_at=datetime(2026, 11, 10, 9, 30),
            deadline=date(2026, 11, 20),
            location="Γραφεία Επαρχιακής Διοίκησης",
        )
        assert len(mailoutbox) == 1
        assert "ΟΙΚ-101" in mailoutbox[0].body
        assert "10000.00" in mailoutbox[0].body

        # Upload a custom .docx template and render the agreement for `alloc1`
        docx_bytes = _make_docx_bytes(
            "ΣΥΜΦΩΝΙΑ: {{protocol_number}} — {{parties_names}}",
            "Οικόπεδο: {{plot_number}} ({{plot_area_sqm}} τ.μ.) — Τιμή: € {{disposal_price}}",
            "Κοινότητα: {{community}} ({{district}})",
        )
        form = AgreementTemplateUploadForm(
            data={"name": "Πρότυπο Παράρτημα 4", "version": "1.0", "is_active": True},
            files={
                "template_file": SimpleUploadedFile(
                    "agreement.docx",
                    docx_bytes,
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert form.is_valid(), form.errors
        template = form.save()
        assert AgreementTemplate.objects.filter(pk=template.pk, is_active=True).exists()

        rendered_doc = Document(render_agreement_docx(alloc1))
        rendered_text = "\n".join(p.text for p in rendered_doc.paragraphs)
        assert b1.protocol_number in rendered_text
        assert "ΟΙΚ-101 (350.00 τ.μ.) — Τιμή: € 10000.00" in rendered_text
        assert "ΑΒΓ (ΛΕΥΚΩΣΙΑΣ)" in rendered_text

        # `b1` fails to pay / sign -> forfeit allocation!
        forfeit_info = forfeit_allocation(
            alloc1,
            reason="Δεν προσήλθε για πληρωμή και υπογραφή εντός της προθεσμίας.",
            agreement_status=Agreement.Status.NO_SHOW,
            payment_status=Payment.Status.UNPAID,
        )
        b1.refresh_from_db()
        assert b1.application_stage == ApplicationStage.FORFEITED
        assert b1.plot_allocation_status == PlotAllocationStatus.NOT_ALLOCATED
        assert forfeit_info["proposed_runner_up"] == b2
        assert forfeit_info["available_runner_ups"] == [b2, b3]

        # Choosing `b3` (skipping `b2`) without justification is refused (Sect. 8)
        with pytest.raises(AnnouncementWorkflowError):
            promote_runner_up(cycle, available_plot, b3, justification="")

        # Promoting `b2` (the next runner-up in rank order) succeeds without justification
        mailoutbox.clear()
        promo = promote_runner_up(
            cycle,
            available_plot,
            b2,
            replaces_allocation=alloc1,
            appointment_at=datetime(2026, 11, 25, 10, 0),
            deadline=date(2026, 12, 5),
        )
        alloc2 = promo["allocation"]
        b2.refresh_from_db()
        assert b2.application_stage == ApplicationStage.AGREEMENT
        assert b2.plot_allocation_status == PlotAllocationStatus.ALLOCATED
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["b2@example.org"]
        assert "ΟΙΚ-101" in mailoutbox[0].body

        # `b2` pays and signs -> application completes and announcement closes!
        record_signature_and_payment(
            alloc2,
            signed=True,
            signed_on=date(2026, 11, 25),
            paid=True,
            paid_on=date(2026, 11, 25),
        )
        b2.refresh_from_db()
        cycle.refresh_from_db()
        assert b2.application_stage == ApplicationStage.COMPLETED
        assert cycle.stage == SubmissionCycle.Stage.CLOSED

    def test_agreement_template_validation_rejects_unknown_placeholders(self):
        bad_bytes = _make_docx_bytes("Συμφωνία {{applicant_name}} και {{unknown_field_xyz}}")
        with pytest.raises(ValidationError) as exc_info:
            validate_agreement_template_file(bad_bytes)
        assert "unknown_field_xyz" in str(exc_info.value)

    def test_default_appendix4_agreement_docx_replaces_all_fields(
        self, community, cycle, available_plot, client, make_user
    ):
        from django.urls import reverse
        from core.services import get_setting

        admin_user = make_user("sysadmin_agr", "Διαχειριστής συστήματος")
        client.force_login(admin_user)

        # Configure the parametric District Officer field via Settings
        resp = client.post(
            reverse("system_settings_agreement_templates"),
            {
                "save_agreement_settings": "1",
                "setting_agreementDistrictOfficer": "Λευκωσίας κ. Ανδρέα Χατζηχάννα",
            },
        )
        assert resp.status_code == 302
        assert get_setting("agreementDistrictOfficer") == "Λευκωσίας κ. Ανδρέα Χατζηχάννα"

        available_plot.design_number = "ΟΙΚ-205"
        available_plot.parcel_number = "789"
        available_plot.sheet_plan = "30/12"
        available_plot.final_area_sqm = Decimal("360.00")
        available_plot.valuation_amount = Decimal("40000.00")
        available_plot.disposal_price = Decimal("10000.00")
        available_plot.save()

        app = _evaluated(
            cycle,
            email="couple@example.org",
            submitted_on=date(2026, 9, 15),
            residence_street="Λεωφ. Ελευθερίας",
            residence_number="24",
            residence_postal_code="2100",
            residence_community="ΑΒΓ",
        )
        app.applicant.first_name = "Γιώργος"
        app.applicant.last_name = "Παπαδόπουλος"
        app.applicant.save()
        app.spouse.first_name = "Ελένη"
        app.spouse.last_name = "Παπαδοπούλου"
        app.spouse.save()
        record_applications_committee_decision(cycle, decided_on=date(2026, 10, 1))
        issue_final_list_and_notify(cycle, decided_on=date(2026, 10, 25))
        schedule_lottery(
            cycle,
            datetime(2026, 11, 2, 10, 30),
            "Επαρχιακή Διοίκηση Λευκωσίας",
        )
        allocations = record_lottery_result(cycle, {app: available_plot})
        alloc = allocations[0]
        complete_lottery(cycle)

        # Before custom location is set, location defaults to «Επαρχιακή Διοίκηση»
        initial_doc = Document(render_agreement_docx(alloc))
        initial_text = "\n".join(p.text for p in initial_doc.paragraphs)
        assert "στην Επαρχιακή Διοίκηση μεταξύ:" in initial_text

        # Invite to agreement with specific appointment date and location
        invite_to_agreement(
            alloc,
            appointment_at=datetime(2026, 11, 14, 11, 0),
            deadline=date(2026, 11, 28),
            location="Επαρχιακή Διοίκηση Λευκωσίας",
        )
        alloc.refresh_from_db()

        doc = Document(render_agreement_docx(alloc))
        body_text = "\n".join(p.text for p in doc.paragraphs)
        table_text = "\n".join(
            p.text
            for t in doc.tables
            for row in t.rows
            for cell in row.cells
            for p in cell.paragraphs
            if p.text.strip()
        )

        # Verify all fields from the user specification
        assert f"Αρ. Φακ. {app.protocol_number}" in body_text
        assert (
            "Συμφωνία που γίνεται σήμερα στις 14/11/2026 στην Επαρχιακή Διοίκηση Λευκωσίας μεταξύ:"
            in body_text
        )
        assert (
            "του Επάρχου Λευκωσίας κ. Ανδρέα Χατζηχάννα εκ μέρους της Κυπριακής"
            in body_text
        )
        applicant_full = f"{app.applicant.first_name} {app.applicant.last_name}"
        spouse_full = f"{app.spouse.first_name} {app.spouse.last_name}"
        assert (
            f"των {applicant_full} με Α.Δ.Τ. {app.applicant.identity_number} "
            f"και {spouse_full} με Α.Δ.Τ. {app.spouse.identity_number}"
            in body_text
        )
        assert (
            "με μόνιμη διεύθυνση διαμονής στην οδό Λεωφ. Ελευθερίας 24, 2100, ΑΒΓ"
            in body_text
        )
        assert (
            f"Γ. ΕΠΕΙΔΗ ο/η Έπαρχος Λευκωσίας κ. Ανδρέα Χατζηχάννα ανακοίνωσε στις {cycle.announcement_date:%d/%m/%Y} την έναρξη"
            in body_text
        )
        assert (
            f"Δ. ΕΠΕΙΔΗ ο Δικαιούχος υπέβαλε στις 15/09/2026 αίτηση για συμμετοχή στο Σχέδιο, "
            f"η οποία έλαβε τον αριθμό αίτησης {app.protocol_number}"
            in body_text
        )
        assert "Κοινότητα/Δημοτικό Διαμέρισμα ΑΒΓ," in body_text
        assert "€40000.00 (40000.00 Ευρώ)" in body_text
        assert (
            f"Οι {applicant_full} και {spouse_full} "
            "(ονοματεπώνυμο Αιτητή/Αιτήτριας και Συζύγου/Συμβίου, ό,τι ισχύει), "
            "οι οποίοι έχει οριστεί να καλούνται"
            in body_text
        )
        assert "Επάρχου Λευκωσίας κ. Ανδρέα Χατζηχάννα" in table_text
        assert applicant_full in table_text
        assert f"Α.Δ.Τ. {app.applicant.identity_number}" in table_text
        assert spouse_full in table_text
        assert f"Α.Δ.Τ. {app.spouse.identity_number}" in table_text

        # Verify filled-in runs are bold, italic, and in a distinct font (Times New Roman vs Arial)
        from core.docx_merge import FILLED_FIELD_FONT_NAME

        all_runs = [
            r
            for p in doc.paragraphs
            for r in p.runs
            if r.text.strip()
        ]
        for expected_filled in (
            app.protocol_number,
            "14/11/2026",
            "Επαρχιακή Διοίκηση Λευκωσίας",
            "Λευκωσίας κ. Ανδρέα Χατζηχάννα",
            applicant_full,
            spouse_full,
            app.applicant.identity_number,
            app.spouse.identity_number,
            "Λεωφ. Ελευθερίας 24, 2100, ΑΒΓ",
            "15/09/2026",
            "ΑΒΓ",
        ):
            matching_runs = [r for r in all_runs if r.text == expected_filled]
            assert matching_runs, f"Expected a dedicated run for {expected_filled!r}"
            for r in matching_runs:
                assert r.bold is True
                assert r.italic is True
                assert r.font.name == FILLED_FIELD_FONT_NAME
                assert r.font.name != "Arial"

        # Surrounding static labels remain in the original font (Arial) without bold/italic
        static_runs = [r for r in doc.paragraphs[0].runs if "Αρ. Φακ." in r.text]
        assert static_runs
        assert static_runs[0].font.name == "Arial"
        assert not static_runs[0].bold
        assert not static_runs[0].italic

        # Single-parent application (no spouse/partner): Article 11 changes to singular
        from plot_applications.models import PlotApplication

        app.family_status = PlotApplication.FamilyStatus.SINGLE_PARENT
        app.single_parent_status = PlotApplication.SingleParentStatus.UNMARRIED
        app.spouse = None
        app.save()
        alloc.refresh_from_db()

        single_doc = Document(render_agreement_docx(alloc))
        single_text = "\n".join(p.text for p in single_doc.paragraphs)
        assert (
            f"Ο/Η {applicant_full} (ονοματεπώνυμο Αιτητή/Αιτήτριας), "
            "ο/η οποίος/α έχει οριστεί να καλείται, στο πλαίσιο της παρούσας Συμφωνίας, "
            "ως «ο Δικαιούχος», υπέχει"
            in single_text
        )
        assert spouse_full not in single_text

    def test_unallocated_plots_are_released_when_announcement_completes_final_stage(
        self, community, cycle, available_plot, staff_client
    ):
        from django.urls import reverse
        from tests.fixtures.cycles import make_cycle

        extra_plot = Plot.objects.create(
            community=community,
            design_number="ΟΙΚ-102",
            valuation_amount=Decimal("40000"),
            disposal_price=Decimal("10000"),
        )
        cycle.plots.add(extra_plot)

        # While `cycle` is active, neither plot is available and `community` is hidden in New Announcement
        assert not Plot.objects.available().exists()
        step1_html = staff_client.get(reverse("announcements:create")).content.decode()
        assert f'data-community-group="{community.pk}"' not in step1_html

        # 2 plots offered (`available_plot`, `extra_plot`), but only 1 beneficiary (`b1`) and 0 runner-ups
        b1 = _evaluated(cycle, email="b1@example.org")
        record_applications_committee_decision(cycle, decided_on=date(2026, 10, 1))
        issue_final_list_and_notify(cycle, decided_on=date(2026, 10, 25))
        allocations = record_lottery_result(cycle, {b1: available_plot})
        complete_lottery(cycle)
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.AGREEMENTS
        # Still in Stage 7 (agreements not yet signed/paid) -> still active, plots not yet released
        assert not Plot.objects.available().exists()

        # `b1` signs and pays -> Stage 7 completes (`CLOSED`), `extra_plot` (not given) is released!
        record_signature_and_payment(
            allocations[0],
            signed=True,
            signed_on=date(2026, 11, 10),
            paid=True,
            paid_on=date(2026, 11, 10),
        )
        cycle.refresh_from_db()
        assert cycle.stage == SubmissionCycle.Stage.CLOSED
        assert not cycle.is_active
        assert list(Plot.objects.available()) == [extra_plot]

        # Stage 7 view of `cycle` shows `extra_plot` as released
        detail_html = staff_client.get(
            reverse("announcements:detail", args=[cycle.pk]), {"stage": "agreements"}
        ).content.decode()
        assert "data-released-plots-card" in detail_html
        assert f'data-released-plot="{extra_plot.pk}"' in detail_html

        # Step 1 of New Announcement now shows `community` with 1 available plot (`extra_plot`)
        step1_after = staff_client.get(reverse("announcements:create")).content.decode()
        assert f'data-community-group="{community.pk}"' in step1_after
        assert f'name="plots" value="{extra_plot.pk}"' in step1_after
        assert f'name="plots" value="{available_plot.pk}"' not in step1_after

        # Now create a 2nd announcement with `extra_plot` and another plot `third_plot`,
        # where 1 beneficiary signs/pays and the 2nd beneficiary forfeits with no runner-ups
        third_plot = Plot.objects.create(
            community=community,
            design_number="ΟΙΚ-103",
            valuation_amount=Decimal("40000"),
            disposal_price=Decimal("10000"),
        )
        cycle2 = make_cycle(
            community,
            plots=[extra_plot, third_plot],
            announcement_date=date(2026, 12, 1),
            submission_months=1,
            published_at=cycle.published_at,
        )
        assert not Plot.objects.available().exists()

        app_keep = _evaluated(cycle2, email="keep@example.org", submitted_on=date(2026, 12, 5))
        app_forfeit = _evaluated(
            cycle2,
            email="forfeit@example.org",
            submitted_on=date(2026, 12, 5),
            residence_category=ResidenceCategory.REPATRIATED,
        )
        record_applications_committee_decision(cycle2, decided_on=date(2027, 1, 5))
        issue_final_list_and_notify(cycle2, decided_on=date(2027, 1, 30))
        allocs2 = record_lottery_result(cycle2, {app_keep: extra_plot, app_forfeit: third_plot})
        complete_lottery(cycle2)

        alloc_keep = next(a for a in allocs2 if a.parcel_id == extra_plot.pk)
        alloc_forfeit = next(a for a in allocs2 if a.parcel_id == third_plot.pk)

        # `app_keep` signs and pays first; `cycle2` stays in AGREEMENTS while `alloc_forfeit` is pending
        record_signature_and_payment(
            alloc_keep,
            signed=True,
            signed_on=date(2027, 2, 10),
            paid=True,
            paid_on=date(2027, 2, 10),
        )
        cycle2.refresh_from_db()
        assert cycle2.stage == SubmissionCycle.Stage.AGREEMENTS
        assert not Plot.objects.available().exists()

        # `app_forfeit` forfeits and there are no runner-ups -> `cycle2` closes and `third_plot` is released!
        forfeit_allocation(
            alloc_forfeit,
            reason="Μη προσέλευση εντός προθεσμίας.",
            agreement_status=Agreement.Status.NO_SHOW,
            payment_status=Payment.Status.UNPAID,
        )
        cycle2.refresh_from_db()
        assert cycle2.stage == SubmissionCycle.Stage.CLOSED
        assert list(Plot.objects.available()) == [third_plot]

    def test_complete_announcement_button_releases_unallocated_plots_in_stage2_stage6_and_stage7(
        self, community, available_plot, staff_client
    ):
        from django.urls import reverse
        from django.utils import timezone
        from tests.fixtures.cycles import make_cycle

        # 1. Stage 2 (`submission`) with 0 complete applications: can complete announcement after accepting open period
        cycle_empty = make_cycle(
            community,
            plots=[available_plot],
            announcement_date=timezone.localdate(),
            submission_months=2,
            published_at=timezone.now(),
        )
        assert not Plot.objects.available().exists()
        sub_html = staff_client.get(
            reverse("announcements:detail", args=[cycle_empty.pk]), {"stage": "submission"}
        ).content.decode()
        assert "data-complete-empty-submission-form" in sub_html
        assert "data-complete-agreements-btn" in sub_html

        # Without accepting open submission period, remains in SUBMISSION
        staff_client.post(reverse("announcements:complete_agreements", args=[cycle_empty.pk]), {})
        cycle_empty.refresh_from_db()
        assert cycle_empty.stage == SubmissionCycle.Stage.SUBMISSION

        # Accepting open submission period closes the announcement and releases `available_plot`
        staff_client.post(
            reverse("announcements:complete_agreements", args=[cycle_empty.pk]),
            {"accept_open_submission": "1"},
        )
        cycle_empty.refresh_from_db()
        assert cycle_empty.stage == SubmissionCycle.Stage.CLOSED
        assert list(Plot.objects.available()) == [available_plot]

        # 2. Stage 6 (`lottery`) when Final List has 0 eligible beneficiaries (all rejected):
        cycle_no_ben = make_cycle(
            community,
            plots=[available_plot],
            announcement_date=date(2026, 9, 1),
            submission_months=1,
            published_at=timezone.now(),
        )
        _evaluated(cycle_no_ben, email="rej@example.org", has_dwelling=True, submitted_on=date(2026, 9, 10))
        record_applications_committee_decision(cycle_no_ben, decided_on=date(2026, 10, 1))
        issue_final_list_and_notify(cycle_no_ben, decided_on=date(2026, 10, 25))
        cycle_no_ben.refresh_from_db()
        assert cycle_no_ben.stage == SubmissionCycle.Stage.LOTTERY

        lot_html = staff_client.get(
            reverse("announcements:detail", args=[cycle_no_ben.pk]), {"stage": "lottery"}
        ).content.decode()
        assert "data-complete-agreements-btn" in lot_html
        staff_client.post(reverse("announcements:complete_agreements", args=[cycle_no_ben.pk]))
        cycle_no_ben.refresh_from_db()
        assert cycle_no_ben.stage == SubmissionCycle.Stage.CLOSED
        assert list(Plot.objects.available()) == [available_plot]

        # 3. Stage 7 (`agreements`) with unallocated plot and remaining runner-up:
        # Officer clicks "Ολοκλήρωση Γνωστοποίησης & Απελευθέρωση Αδιάθετων Οικοπέδων"
        plot_b = Plot.objects.create(
            community=community,
            design_number="ΟΙΚ-200",
            valuation_amount=Decimal("40000"),
            disposal_price=Decimal("10000"),
        )
        cycle_s7 = make_cycle(
            community,
            plots=[available_plot, plot_b],
            announcement_date=date(2026, 9, 1),
            submission_months=1,
            published_at=timezone.now(),
        )
        b1 = _evaluated(cycle_s7, email="b1@example.org", submitted_on=date(2026, 9, 10))
        b2 = _evaluated(cycle_s7, email="b2@example.org", submitted_on=date(2026, 9, 10))
        b3 = _evaluated(
            cycle_s7,
            email="b3@example.org",
            submitted_on=date(2026, 9, 10),
            residence_category=ResidenceCategory.REPATRIATED,
        )
        record_applications_committee_decision(cycle_s7, decided_on=date(2026, 10, 1))
        issue_final_list_and_notify(cycle_s7, decided_on=date(2026, 10, 25))
        allocs_s7 = record_lottery_result(cycle_s7, {b1: available_plot, b2: plot_b})
        complete_lottery(cycle_s7)

        alloc_b1 = next(a for a in allocs_s7 if a.application_id == b1.pk)
        alloc_b2 = next(a for a in allocs_s7 if a.application_id == b2.pk)

        # `b1` signs and pays; `b2` forfeits; `b3` is a runner-up -> `cycle_s7` stays in `AGREEMENTS`
        record_signature_and_payment(alloc_b1, signed=True, paid=True)
        forfeit_allocation(alloc_b2, reason="Δεν προσήλθε.")
        cycle_s7.refresh_from_db()
        assert cycle_s7.stage == SubmissionCycle.Stage.AGREEMENTS

        agr_html = staff_client.get(
            reverse("announcements:detail", args=[cycle_s7.pk]), {"stage": "agreements"}
        ).content.decode()
        assert "data-complete-agreements-btn" in agr_html
        assert "data-header-complete-btn" in agr_html

        # Clicking the complete button closes `cycle_s7` and releases `plot_b` (`available_plot` remains allocated to `b1`)
        staff_client.post(reverse("announcements:complete_agreements", args=[cycle_s7.pk]))
        cycle_s7.refresh_from_db()
        assert cycle_s7.stage == SubmissionCycle.Stage.CLOSED
        assert list(Plot.objects.available()) == [plot_b]

