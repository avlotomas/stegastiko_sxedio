"""Browser E2E: actions on the announcement workspace keep the reader at the card they worked in."""

import os
import re
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import Page, expect

from plot_applications.announcement_workflow import (
    record_applications_committee_decision,
    register_objection,
)
from tests.test_objections import _evaluated
from tests.test_plot_applications import available_plot, community, cycle  # noqa: F401

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.e2e]

PASSWORD = "e2e-secret"


def _login(page: Page, base_url: str, username: str):
    page.goto(f"{base_url}/login/")
    page.get_by_label("Όνομα χρήστη").fill(username)
    page.get_by_label("Κωδικός").fill(PASSWORD)
    page.get_by_role("button", name="Είσοδος").click()
    page.wait_for_url(re.compile(r".*/$"))


def _card_top(page: Page, selector: str) -> float:
    return page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect().top")


def test_objection_actions_return_to_the_objection_card(page: Page, cycle, live_server_url):
    get_user_model().objects.create_superuser("supervisor", password=PASSWORD)
    _evaluated(cycle, email="b1@example.org")
    rejected = _evaluated(cycle, email="r1@example.org", has_dwelling=True)
    record_applications_committee_decision(cycle, decided_on=date(2026, 10, 1))
    objection = register_objection(rejected, submitted_on=date(2026, 10, 10), grounds="Ένσταση E2E")
    card = f'[data-scroll-anchor="objection-{objection.pk}"]'

    _login(page, live_server_url, "supervisor")
    page.goto(f"{live_server_url}/announcements/{cycle.pk}/")
    page.locator(card).scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, -120)")
    top_before = _card_top(page, card)
    assert page.evaluate("window.scrollY") > 0

    page.locator(f"#pending_desc_{objection.pk}").fill("Πιστοποιητικό ΤΚΧ")
    page.get_by_role("button", name="Προσθήκη εκκρεμότητας (Pending)").click()
    floating = page.locator(".messages-stack--floating")
    expect(floating).to_contain_text("Προστέθηκε εκκρεμότητα")
    assert abs(_card_top(page, card) - top_before) <= 2
    screenshot = os.environ.get("E2E_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot)

    page.locator(f"{card} [data-pending-checkbox]").click()
    expect(page.locator(".messages-stack--floating")).to_contain_text("Ενημερώθηκε η κατάσταση")
    expect(page.locator(f"{card} [data-pending-checkbox]")).to_be_checked()
    assert abs(_card_top(page, card) - top_before) <= 2


def test_ui_edit_mode_makes_all_non_data_texts_editable_on_announcement_stages(
    page: Page, cycle, live_server_url
):
    get_user_model().objects.create_superuser("supervisor", password=PASSWORD)
    _evaluated(cycle, email="b1@example.org")
    _evaluated(cycle, email="r1@example.org", has_dwelling=True)
    record_applications_committee_decision(cycle, decided_on=date(2026, 10, 28))

    _login(page, live_server_url, "supervisor")
    page.goto(f"{live_server_url}/announcements/{cycle.pk}/?stage=objections_committee")

    # Toggle UI Edit Mode on
    page.locator("[data-ui-edit-mode-toggle]").click()
    expect(page.locator("body")).to_have_class(re.compile(r"\bui-edit-mode\b"))

    # 1. All 7 stage tabs in the wizard stepper (both enabled and disabled) have edit icons
    assert page.locator(".wizard-steps__link [data-ui-edit-trigger]").count() == 7

    # 2. Stage 4 heading has an edit icon and was NOT overwritten by Case Section 4
    stage_title = page.locator('[data-announcement-stage="objections_committee"] h2.card__title').first
    expect(stage_title).to_contain_text("4. Ενστάσεις (Ενότ. 7)")
    expect(stage_title.locator("[data-ui-edit-trigger]")).to_be_visible()

    # 3. Helptext paragraph with inline <code>PENDING</code> has an edit icon and preserves <code>
    helptext = page.locator('[data-announcement-stage="objections_committee"] > p.helptext').first
    expect(helptext.locator("code")).to_have_text("PENDING")
    expect(helptext.locator("[data-ui-edit-trigger]")).to_be_visible()

    # 4. Objection period line: "Περίοδος ενστάσεων:", "λήξη", and badge "σε εξέλιξη" each have edit icons
    period_p = page.locator("[data-objection-period]")
    assert period_p.locator("[data-ui-edit-trigger]").count() == 3

    # 5. Editing "Αιτήσεις (2)" edits only the static text "Αιτήσεις" and preserves the dynamic count "(2)"
    apps_btn = page.locator("[data-open-applications-modal]")
    apps_btn.locator("[data-ui-edit-trigger]").click()
    dialog = page.locator("#ui-text-edit-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("[data-ui-text-input]")).to_have_value("Αιτήσεις")
    dialog.locator("[data-ui-text-input]").fill("Αιτήσεις Πολιτών")
    dialog.locator("[data-ui-text-save]").click()
    expect(dialog).to_be_hidden()
    expect(apps_btn).to_contain_text("Αιτήσεις Πολιτών (2)")

    # Reset back to default
    apps_btn.locator("[data-ui-edit-trigger]").click()
    dialog.locator("[data-ui-text-reset]").click()
    expect(dialog).to_be_hidden()
    expect(apps_btn).to_contain_text("Αιτήσεις (2)")

    screenshot = os.environ.get("E2E_UI_EDIT_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)

