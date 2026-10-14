"""Browser E2E: the 9.2 publication table of an announcement (four fixed methods, many «Άλλο»)."""

import os
import re
from datetime import date

import pytest
from playwright.sync_api import Page, expect

from cases.models import SubmissionCycle
from core.models import Community
from tests.fixtures.cycles import make_cycle

E2E_PASSWORD = "e2e-secret"
E2E_USERNAME = "e2e_clerk"

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.e2e]


def _login(page: Page, base_url: str):
    page.goto(f"{base_url}/login/")
    page.get_by_label("Όνομα χρήστη").fill(E2E_USERNAME)
    page.get_by_label("Κωδικός").fill(E2E_PASSWORD)
    page.get_by_role("button", name="Είσοδος").click()
    page.wait_for_url(re.compile(r".*/$"))


def _set_date(page: Page, label: str, published_on: str):
    """The four fixed methods are dated inline in the table: no modal."""
    page.get_by_label(label).fill(published_on)
    expect(page.locator("[data-publication-status]")).to_contain_text(label)


def test_publication_methods_table(page: Page, e2e_user, live_server_url):
    community = Community.objects.create(name="Κοινότητα E2E")
    cycle = make_cycle(
        community,
        announcement_date=date(2027, 6, 1),
    )

    _login(page, live_server_url)
    page.goto(f"{live_server_url}/announcements/{cycle.pk}/")
    table = page.locator("[data-publication-table]")
    rows = table.locator("tr[data-publication-row]")
    expect(rows).to_have_count(4)
    expect(table.locator("input[data-publication-date]")).to_have_count(4)

    _set_date(page, "Έντυπη ανάρτηση στα γραφεία Επαρχιακής Διοίκησης", "2027-06-02")
    _set_date(page, "Ιστοσελίδα ΥΠΕΣ", "2027-06-03")
    assert sorted(cycle.publications.values_list("method", flat=True)) == ["district_office", "ministry_site"]
    expect(page.get_by_label("Ιστοσελίδα ΥΠΕΣ")).to_have_value("2027-06-03")

    page.get_by_label("Ιστοσελίδα ΥΠΕΣ").fill("")
    expect(page.locator("[data-publication-status]")).to_contain_text("Αφαιρέθηκε")
    assert cycle.publications.count() == 1

    # «Άλλο» can be added many times, each with a date and a comment.
    for day, comment in (("2027-06-04", "Εφημερίδα"), ("2027-06-05", "Ραδιόφωνο")):
        page.get_by_role("button", name="Προσθήκη «Άλλο»").click()
        dialog = page.locator("[data-publication-dialog]")
        dialog.locator("#id_published_on").fill(day)
        dialog.locator("#id_notes").fill(comment)
        dialog.get_by_role("button", name="Αποθήκευση").click()
        expect(dialog).to_be_hidden()
    expect(rows).to_have_count(6)

    screenshot = os.environ.get("E2E_SCREENSHOT")
    if screenshot:
        page.locator("[data-publication-container]").screenshot(path=screenshot)

    page.once("dialog", lambda d: d.accept())
    rows.last.get_by_role("button", name="Διαγραφή").click()
    expect(rows).to_have_count(5)
    assert cycle.publications.count() == 2
