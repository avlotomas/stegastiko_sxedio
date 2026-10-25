"""Μετονομασία σταδίων, χειροκίνητη αλλαγή επιλεξιμότητας και κατάλογος προτεραιοποίησης (Ενότ. 6, 11)."""

import json

import pytest
from django.urls import reverse

from core.models import ActionHistory, Role
from core.function_catalog import EDIT, EXPORT, VIEW
from core.permissions import has_access
from plot_applications.models import (
    ApplicationStage,
    EligibilityOverride,
    PlotApplication,
    ResidenceCategory,
)
from plot_applications.prioritization import (
    BENEFICIARIES,
    OTHERS,
    build_prioritization_list,
    save_manual_order,
)
from plot_applications.rules import apply_evaluation
from plot_applications.stage_labels import get_application_stage_label
from tests.test_plot_applications import (  # noqa: F401 (fixtures)
    _application,
    available_plot,
    community,
    cycle,
    staff_client,
)


def _ids(rows):
    return [row.application.pk for row in rows]


def _evaluated(cycle, **extra):
    application = _application(cycle, **extra)
    apply_evaluation(application)
    return application


def _incomplete(cycle):
    application = _application(cycle)
    application.attached_documents = []
    apply_evaluation(application)
    return application


@pytest.fixture
def mixed_applications(cycle):
    """Δικαιούχοι σε αντίστροφη σειρά καταχώρισης ως προς την Ενότ. 11, ένας μη δικαιούχος, ένας ελλιπής."""
    repatriated = _evaluated(cycle, residence_category=ResidenceCategory.REPATRIATED)
    autochthon = _evaluated(cycle)
    not_beneficiary = _evaluated(cycle, has_dwelling=True)
    incomplete = _incomplete(cycle)
    return {
        "repatriated": repatriated,
        "autochthon": autochthon,
        "not_beneficiary": not_beneficiary,
        "incomplete": incomplete,
    }


@pytest.mark.django_db
class TestApplicationStageLabels:
    def test_stage_label_can_be_renamed_from_edit_mode_and_reset(self, client, make_user, cycle):
        client.force_login(make_user("admin_stage", "Διαχειριστής συστήματος"))
        application = _incomplete(cycle)
        assert application.application_stage == ApplicationStage.COLLECTION

        resp = client.post(
            reverse("ui_text_save"),
            {"key": "applicationStageLabel.collection", "value": "Συλλογή στοιχείων"},
        )
        assert resp.status_code == 200, resp.content
        assert get_application_stage_label(ApplicationStage.COLLECTION) == "Συλλογή στοιχείων"

        detail_html = client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert 'data-ui-key="applicationStageLabel.collection"' in detail_html
        assert "Συλλογή στοιχείων" in detail_html

        list_resp = client.get(reverse("plot_applications:list"))
        assert ("collection", "Συλλογή στοιχείων") in list_resp.context["stage_choices"]
        assert "Συλλογή στοιχείων" in list_resp.content.decode()

        person_html = client.get(
            reverse("persons:detail", args=[application.applicant_id])
        ).content.decode()
        assert "Συλλογή στοιχείων" in person_html

        reset = client.post(
            reverse("ui_text_save"),
            {"key": "applicationStageLabel.collection", "value": "", "reset": "1"},
        )
        assert reset.status_code == 200
        assert (
            get_application_stage_label(ApplicationStage.COLLECTION)
            == "Συλλογή πληροφοριών και πιστοποιητικών"
        )

    def test_stage_labels_settings_page(self, client, make_user):
        client.force_login(make_user("admin_stage_settings", "Διαχειριστής συστήματος"))
        url = reverse("system_settings_plot_application_labels")
        assert client.get(url).status_code == 200
        data = {f"stage_{code}": label for code, label in ApplicationStage.choices}
        data["stage_examination"] = "Αξιολόγηση δικαιούχου"
        resp = client.post(url, data)
        assert resp.status_code == 302
        assert get_application_stage_label(ApplicationStage.EXAMINATION) == "Αξιολόγηση δικαιούχου"

    def test_stage_label_rename_requires_permission(self, client, make_user):
        client.force_login(make_user("officer_stage", "Λειτουργός καταχώρισης"))
        resp = client.post(
            reverse("ui_text_save"),
            {"key": "applicationStageLabel.collection", "value": "Χ"},
        )
        assert resp.status_code == 403
        assert (
            get_application_stage_label(ApplicationStage.COLLECTION)
            == "Συλλογή πληροφοριών και πιστοποιητικών"
        )


@pytest.mark.django_db
class TestEligibilityOverride:
    def test_override_fail_to_pass_with_reason(self, staff_client, cycle):
        application = _evaluated(cycle, has_dwelling=True)
        assert application.beneficiary_status == "fail"
        assert application.application_stage == ApplicationStage.PRIORITIZATION

        url = reverse("plot_applications:eligibility_override_save", args=[application.pk])
        missing_reason = staff_client.post(url, {"eligibility_override": EligibilityOverride.PASS})
        assert missing_reason.status_code == 302
        application.refresh_from_db()
        assert application.eligibility_override == ""
        assert application.beneficiary_status == "fail"

        resp = staff_client.post(
            url,
            {
                "eligibility_override": EligibilityOverride.PASS,
                "eligibility_override_reason": "Απόφαση Επιτροπής Εξέτασης: η κατοικία είναι ακατάλληλη.",
            },
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.eligibility_override == EligibilityOverride.PASS
        assert application.eligibility_auto_result == "fail"
        assert application.beneficiary_status == "pass"
        assert application.application_stage == ApplicationStage.PRIORITIZATION
        history = ActionHistory.objects.filter(
            entity_type="PlotApplication", entity_id=str(application.pk)
        )
        assert history.filter(field_name="eligibility_override", new_value="pass").exists()
        assert history.filter(field_name="eligibility_override_reason").exists()

        detail_html = staff_client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()
        assert "data-eligibility-override-form" in detail_html
        assert "data-eligibility-override-summary" in detail_html
        assert "η κατοικία είναι ακατάλληλη" in detail_html

        rows = build_prioritization_list(application.community)
        assert application.pk in _ids(rows.beneficiaries)

        staff_client.post(url, {"eligibility_override": ""})
        application.refresh_from_db()
        assert application.eligibility_override == ""
        assert application.eligibility_override_reason == ""
        assert application.beneficiary_status == "fail"

    def test_override_pass_to_fail_moves_to_others_with_reason(self, staff_client, cycle):
        application = _evaluated(cycle)
        url = reverse("plot_applications:eligibility_override_save", args=[application.pk])
        staff_client.post(
            url,
            {
                "eligibility_override": EligibilityOverride.FAIL,
                "eligibility_override_reason": "Ψευδής δήλωση εισοδήματος.",
            },
        )
        application.refresh_from_db()
        assert application.beneficiary_status == "fail"
        assert application.application_stage == ApplicationStage.PRIORITIZATION
        others = build_prioritization_list(application.community).others
        assert [row.application.pk for row in others] == [application.pk]
        assert "Ψευδής δήλωση εισοδήματος." in others[0].reasons[0]

    def test_override_not_allowed_for_incomplete_application(self, staff_client, cycle):
        application = _incomplete(cycle)
        url = reverse("plot_applications:eligibility_override_save", args=[application.pk])
        resp = staff_client.post(
            url, {"eligibility_override": EligibilityOverride.FAIL, "eligibility_override_reason": "Χ"}
        )
        assert resp.status_code == 302
        application.refresh_from_db()
        assert application.eligibility_override == ""
        assert f'action="{url}"' not in staff_client.get(
            reverse("plot_applications:detail", args=[application.pk])
        ).content.decode()


@pytest.mark.django_db
class TestPrioritizationList:
    def test_list_ranks_beneficiaries_first_by_section_11(self, staff_client, community, mixed_applications):
        apps = mixed_applications
        resp = staff_client.get(reverse("plot_applications:prioritization"), {"community_id": community.pk})
        assert resp.status_code == 200
        prioritization = resp.context["prioritization"]
        assert _ids(prioritization.beneficiaries) == [apps["autochthon"].pk, apps["repatriated"].pk]
        assert _ids(prioritization.others) == [apps["not_beneficiary"].pk]
        assert apps["incomplete"].pk not in _ids(prioritization.beneficiaries + prioritization.others)
        assert prioritization.others[0].reasons
        assert any("11.1" in text for text in prioritization.beneficiaries[0].criteria)

        html = resp.content.decode()
        assert 'data-prioritization-sortable="beneficiaries"' in html
        assert "data-prioritization-report-pdf-link" in html

    def test_reorder_merge_and_reset(self, staff_client, community, cycle, mixed_applications):
        apps = mixed_applications
        url = reverse("plot_applications:prioritization_reorder")
        resp = staff_client.post(
            url,
            json.dumps(
                {
                    "community_id": community.pk,
                    "group": BENEFICIARIES,
                    "order": [apps["repatriated"].pk, apps["autochthon"].pk, apps["not_beneficiary"].pk],
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        listing = build_prioritization_list(community)
        assert _ids(listing.beneficiaries) == [apps["repatriated"].pk, apps["autochthon"].pk]
        assert listing.beneficiaries[0].is_moved
        assert listing.has_manual_order
        # Cross-group ids are ignored: the non-beneficiary stays in its own group.
        assert _ids(listing.others) == [apps["not_beneficiary"].pk]

        newcomer = _evaluated(cycle)
        listing = build_prioritization_list(community)
        assert newcomer.pk in _ids(listing.beneficiaries)

        bad = staff_client.post(
            url,
            json.dumps({"community_id": community.pk, "group": "x", "order": []}),
            content_type="application/json",
        )
        assert bad.status_code == 400

        reset = staff_client.post(
            reverse("plot_applications:prioritization_reset"), {"community_id": community.pk}
        )
        assert reset.status_code == 302
        listing = build_prioritization_list(community)
        assert not listing.has_manual_order
        assert listing.beneficiaries[0].application.pk in (apps["autochthon"].pk, newcomer.pk)

    def test_changing_group_clears_manual_rank(self, community, mixed_applications):
        apps = mixed_applications
        save_manual_order(community, BENEFICIARIES, [apps["repatriated"].pk, apps["autochthon"].pk])
        app = PlotApplication.objects.get(pk=apps["repatriated"].pk)
        assert app.priority_rank == 1
        app.eligibility_override = EligibilityOverride.FAIL
        app.eligibility_override_reason = "Χ"
        apply_evaluation(app)
        app.refresh_from_db()
        assert app.priority_rank is None
        assert app.pk in _ids(build_prioritization_list(community).group(OTHERS))

    def test_pdf_report_is_landscape_with_criteria_and_reasons(self, staff_client, community, mixed_applications):
        from plot_applications.prioritization_report_pdf import prioritization_report_context
        from django.template.loader import render_to_string

        resp = staff_client.get(
            reverse("plot_applications:prioritization_report_pdf"), {"community_id": community.pk}
        )
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert "katalogos_proteraiopoiisis_007.pdf" in resp["Content-Disposition"]

        html = render_to_string(
            "plot_applications/pdf/prioritization_report.html",
            prioritization_report_context(community),
        )
        assert "A4 landscape" in html
        assert "Τόπος διαμονής" in html
        assert "Λόγος" in html
        assert mixed_applications["not_beneficiary"].protocol_number in html

    def test_permissions(self, client, make_user, community, mixed_applications):
        user = make_user("no_access", "Λειτουργός καταχώρισης")
        Role.objects.get(name="Λειτουργός καταχώρισης")
        client.force_login(user)
        can_view = has_access(user, "plot_prioritization", VIEW)
        can_edit = has_access(user, "plot_prioritization", EDIT)
        resp = client.get(reverse("plot_applications:prioritization"), {"community_id": community.pk})
        assert resp.status_code == (200 if can_view else 403)
        reorder = client.post(
            reverse("plot_applications:prioritization_reorder"),
            json.dumps({"community_id": community.pk, "group": BENEFICIARIES, "order": []}),
            content_type="application/json",
        )
        assert reorder.status_code == (200 if can_edit else 403)

    def test_default_roles_receive_grants_and_menu_link(self, staff_client, make_user):
        supervisor = make_user("sup_grants", "Προϊστάμενος ελέγχου")
        for action in (VIEW, EDIT, EXPORT):
            assert has_access(supervisor, "plot_prioritization", action)
        html = staff_client.get(reverse("plot_applications:list")).content.decode()
        assert reverse("plot_applications:prioritization") in html
        assert 'data-ui-key="menuLabel.applications_prioritization"' in html
