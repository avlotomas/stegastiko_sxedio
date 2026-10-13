"""Browser E2E: the 9.2 publication methods of an announcement are a grid edited in a modal."""

import os
import re
from datetime import date

import pytest
from playwright.sync_api import Page, expect

from cases.models import SubmissionCycle
from core.models import Community

E2E_PASSWORD = "e2e-secret"
E2E_USERNAME = "e2e_clerk"

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.e2e]


def _login(page: Page, base_url: str):
    page.goto(f"{base_url}/login/")
    page.get_by_label("Όνομα χρήστη").fill(E2E_USERNAME)
    page.get_by_label("Κωδικός").fill(E2E_PASSWORD)
    page.get_by_role("button", name="Είσοδος").click()
    page.wait_for_url(re.compile(r".*/$"))


def _add_publication(page: Page, method: str, published_on: str):
    page.get_by_role("button", name="Προσθήκη τρόπου δημοσίευσης").click()
    dialog = page.locator("[data-publication-dialog]")
    expect(dialog.get_by_role("heading", name="Νέος τρόπος δημοσίευσης")).to_be_visible()
    dialog.locator("#id_method").select_option(method)
    dialog.locator("#id_published_on").fill(published_on)
    dialog.get_by_role("button", name="Αποθήκευση").click()
    expect(dialog).to_be_hidden()


def test_publication_methods_grid(page: Page, e2e_user, live_server_url):
    community = Community.objects.create(name="Κοινότητα E2E")
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2027, 6, 1),
        submission_start_date=date(2027, 6, 2),
        submission_end_date=date(2027, 7, 1),
    )

    _login(page, live_server_url)
    page.goto(f"{live_server_url}/announcements/{cycle.pk}/")
    table = page.locator("[data-publication-table]")
    expect(table).to_contain_text("Δεν έχουν καταχωριστεί τρόποι δημοσίευσης.")

    _add_publication(page, "district_office", "2027-06-02")
    _add_publication(page, "ministry_site", "2027-06-03")
    rows = table.locator("tr[data-publication-row]")
    expect(rows).to_have_count(2)
    expect(rows.first).to_contain_text("Έντυπη ανάρτηση στα γραφεία Επαρχιακής Διοίκησης")
    expect(page.locator("[data-publication-status]")).to_contain_text("Προστέθηκε")

    screenshot = os.environ.get("E2E_SCREENSHOT")
    if screenshot:
        page.locator("[data-publication-container]").screenshot(path=screenshot)

    page.once("dialog", lambda d: d.accept())
    rows.last.get_by_role("button", name="Διαγραφή").click()
    expect(rows).to_have_count(1)
    assert cycle.publications.count() == 1
