"""Browser E2E: login, new application, verify detail page (UAT §Β.7.5)."""

import re

import pytest
from playwright.sync_api import Page, expect

from applications.models import Application
E2E_PASSWORD = "e2e-secret"
E2E_USERNAME = "e2e_clerk"

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.e2e]


def _login(page: Page, base_url: str):
    page.goto(f"{base_url}/login/")
    page.get_by_label("Όνομα χρήστη").fill(E2E_USERNAME)
    page.get_by_label("Κωδικός").fill(E2E_PASSWORD)
    page.get_by_role("button", name="Είσοδος").click()
    page.wait_for_url(re.compile(r".*/$"))


def test_create_application_through_browser(page: Page, application_cycle, e2e_user, live_server_url):
    cycle = application_cycle["cycle"]
    identity = "E2E-BROWSER-001"
    email = "e2e.browser@example.org"

    _login(page, live_server_url)
    page.goto(f"{live_server_url}/applications/new/")
    expect(page.get_by_role("heading", name="Νέα αίτηση")).to_be_visible()

    page.locator("#id_submission_cycle").select_option(str(cycle.pk))
    page.locator("#id_submitted_on").fill("2026-06-10")
    page.locator("#id_family_type").select_option("other")
    page.locator("#id_applicant_email").fill(email)
    page.locator("#id_person1_identity_number").fill(identity)
    page.locator("#id_person1_first_name").fill("Ελένη")
    page.locator("#id_person1_last_name").fill("Browser")
    page.locator("#id_person1_date_of_birth").fill("1990-05-15")
    page.locator("#id_person1_birth_place").fill("Λευκωσία")
    page.locator("#id_person1_birth_country").fill("Κύπρος")
    page.locator("#id_person1_parents_birth_place").fill("Λευκωσία")
    page.locator("#id_person1_parents_birth_country").fill("Κύπρος")
    page.locator("#id_person1_citizenship_cypriot").check()
    page.locator("#id_person1_residence_community").fill("ΑΓΙΑ ΒΑΡΒΑΡΑ")
    page.locator("#id_person1_residence_address").fill("1 E2E Street")
    page.locator("#id_person1_income").fill("18000")

    page.get_by_role("button", name="Αποθήκευση").click()
    page.wait_for_url(re.compile(r".*/applications/\d+/"))

    app = Application.objects.get(applicant_email=email)
    expect(page.get_by_role("heading", name=f"Αίτηση {app.folder_number}")).to_be_visible()
    assert app.person.identity_number == identity
