"""Regression tests for applications fixes: Excel import robustness, income parsing,
Person 2 validation, folder numbering, cycle changes on edit and configurable income limits.
Also covers list / edit / person lookup / person compare views and the import -> confirm flow."""

import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from applications.import_reader import (
    MAX_IMPORT_FILE_SIZE,
    ParsedImport,
    _cell_value,
    _parse_date,
    _parse_decimal,
    parse_import_workbook,
)
from applications.import_services import _income_totals, save_import, validate_import
from applications.management.commands.generate_application_import_sample import (
    SAMPLE_APPLICATION,
    SAMPLE_CHILDREN,
    SAMPLE_DECLARATIONS,
    SAMPLE_INCOME,
    SAMPLE_METADATA,
    SAMPLE_P1,
    SAMPLE_P2,
    SAMPLE_RESIDENCE,
)
from applications.management.commands.generate_application_import_template import (
    build_workbook,
)
from applications.models import Application, EligibilityCheck, Person
from applications.rules import _income_limit, evaluate_eligibility
from applications.services import generate_folder_number, save_with_new_folder_number
from applications.views import IMPORT_SESSION_KEY
from cases.models import SubmissionCycle
from core.configuration_forms import SystemWorkflowSettingsForm
from core.models import Community
from core.services import get_setting, set_setting
from tests.fixtures.golden_application import golden_application_post_data, seed_application_cycle

IMPORT_URL = "applications:import"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def application_cycle(db):
    return seed_application_cycle()


@pytest.fixture
def clerk_client(client, make_user):
    client.force_login(make_user("clerk-fixes", "Λειτουργός καταχώρισης"))
    return client


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("sysadmin-fixes", "Διαχειριστής συστήματος"))
    return client


def _fill_horizontal(ws, values: dict):
    for col_idx, cell in enumerate(ws[2], start=1):
        if cell.value in values:
            ws.cell(row=4, column=col_idx, value=values[cell.value])


def _fill_table(ws, rows: list[dict]):
    keys = [c.value for c in ws[2]]
    for offset, row_data in enumerate(rows):
        for col_idx, key in enumerate(keys, start=1):
            if key in row_data:
                ws.cell(row=4 + offset, column=col_idx, value=row_data[key])


def make_workbook_bytes(
    cycle,
    *,
    metadata=None,
    application=None,
    p1=None,
    p2=None,
    residence=None,
    children=None,
    income=None,
) -> bytes:
    """Appendix 3 workbook based on the sample data, with per-test overrides."""
    wb = build_workbook()
    meta = {**SAMPLE_METADATA, "submission_cycle_id": str(cycle.pk), **(metadata or {})}
    for row in wb["Μεταδεδομένα"].iter_rows(min_row=2):
        if row[0].value in meta:
            row[2].value = meta[row[0].value]
    _fill_horizontal(wb["Αίτηση"], {**SAMPLE_APPLICATION, **(application or {})})
    _fill_horizontal(wb["Πρόσωπο1"], {**SAMPLE_P1, **(p1 or {})})
    _fill_horizontal(wb["Πρόσωπο2"], {**SAMPLE_P2, **(p2 or {})})
    _fill_horizontal(wb["Διαμονή"], {**SAMPLE_RESIDENCE, **(residence or {})})
    _fill_horizontal(wb["Δηλώσεις"], SAMPLE_DECLARATIONS)
    _fill_table(wb["Τέκνα"], SAMPLE_CHILDREN if children is None else children)
    _fill_table(wb["Εισοδήματα"], SAMPLE_INCOME if income is None else income)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, content: bytes, name="import.xlsx"):
    return client.post(
        reverse(IMPORT_URL),
        {"import_file": SimpleUploadedFile(name, content)},
    )


def parse_bytes(content: bytes) -> ParsedImport:
    return parse_import_workbook(BytesIO(content))


def _errors(response) -> list[str]:
    return response.context["validation"].errors


# ---------------------------------------------------------------- 1a corrupt uploads


@pytest.mark.django_db
def test_import_non_xlsx_upload_shows_error_not_500(clerk_client, application_cycle):
    response = upload(clerk_client, b"this is not a spreadsheet", name="notes.txt")
    assert response.status_code == 200
    assert "δεν είναι έγκυρο αρχείο Excel" in response.content.decode()
    assert IMPORT_SESSION_KEY not in clerk_client.session


@pytest.mark.django_db
def test_import_corrupt_zip_upload_shows_error(clerk_client, application_cycle):
    content = make_workbook_bytes(application_cycle["cycle"])[:400]  # truncated zip
    response = upload(clerk_client, content)
    assert response.status_code == 200
    assert "δεν είναι έγκυρο αρχείο Excel" in response.content.decode()


@pytest.mark.django_db
def test_import_oversized_upload_rejected(clerk_client, application_cycle):
    response = upload(clerk_client, b"0" * (MAX_IMPORT_FILE_SIZE + 1))
    assert response.status_code == 200
    assert "μέγιστο επιτρεπτό μέγεθος" in response.content.decode()


# ------------------------------------------------------------- 1b numeric ID cells


def test_cell_value_normalises_numbers_and_dates_to_text():
    assert _cell_value(7654321) == "7654321"
    assert _cell_value(7654321.0) == "7654321"
    assert _cell_value(12.5) == "12.5"
    assert _cell_value(None) == ""
    assert _cell_value(datetime(2020, 1, 2, 10, 30)) == "2020-01-02"
    assert _cell_value(date(2020, 1, 2)) == "2020-01-02"
    assert _cell_value(" K1 ") == "K1"


@pytest.mark.django_db
def test_import_numeric_identity_cells_are_text(clerk_client, application_cycle):
    content = make_workbook_bytes(
        application_cycle["cycle"],
        p1={"p1_identity_number": 7654321, "p1_mailing_postal_code": 2700},
        p2={"p2_identity_number": 1234567.0},
    )
    response = upload(clerk_client, content)
    assert response.status_code == 200
    assert _errors(response) == []
    fields = clerk_client.session[IMPORT_SESSION_KEY]["fields"]
    assert fields["p1_identity_number"] == "7654321"
    assert fields["p2_identity_number"] == "1234567"
    assert fields["p1_mailing_postal_code"] == "2700"

    confirm = clerk_client.post(reverse(IMPORT_URL), {"action": "confirm"})
    assert confirm.status_code == 302
    app = Application.objects.get()
    assert app.person.identity_number == "7654321"
    assert app.person2.identity_number == "1234567"


def test_template_sets_text_format_on_identifier_columns():
    wb = build_workbook()
    ws = wb["Πρόσωπο1"]
    formats = {ws.cell(row=2, column=c).value: ws.cell(row=4, column=c).number_format for c in range(1, ws.max_column + 1)}
    assert formats["p1_identity_number"] == "@"
    assert formats["p1_mobile_phone"] == "@"
    assert formats["p1_mailing_postal_code"] == "@"
    assert formats["p1_first_name"] != "@"
    meta = {row[0].value: row[2].number_format for row in wb["Μεταδεδομένα"].iter_rows(min_row=2)}
    assert meta["community_code"] == "@"


# -------------------------------------------------- 1c blank / bad dates, bad cycle


@pytest.mark.django_db
def test_import_blank_dob_is_validation_error(clerk_client, application_cycle):
    content = make_workbook_bytes(application_cycle["cycle"], p1={"p1_date_of_birth": None})
    response = upload(clerk_client, content)
    assert response.status_code == 200
    assert response.context["can_save"] is False
    assert any("Ημερομηνία γέννησης" in e for e in _errors(response))


@pytest.mark.django_db
def test_import_invalid_dob_is_validation_error(clerk_client, application_cycle):
    content = make_workbook_bytes(application_cycle["cycle"], p1={"p1_date_of_birth": "1988-13-45"})
    response = upload(clerk_client, content)
    assert response.status_code == 200
    assert any("μη έγκυρη ημερομηνία" in e and "1988-13-45" in e for e in _errors(response))


@pytest.mark.django_db
def test_import_invalid_dates_and_cycle_id_collected(clerk_client, application_cycle):
    content = make_workbook_bytes(
        application_cycle["cycle"],
        metadata={"submission_cycle_id": "abc"},
        application={"submitted_on": "14/06/2026"},
        children=[{**SAMPLE_CHILDREN[0], "child_date_of_birth": "κάποτε"}],
    )
    response = upload(clerk_client, content)
    assert response.status_code == 200
    errors = _errors(response)
    assert any("κύκλος υποβολής" in e and "abc" in e for e in errors)
    assert any(e.startswith("Ημερομηνία υποβολής") for e in errors)
    assert any(e.startswith("Τέκνο 1") for e in errors)


@pytest.mark.django_db
def test_import_confirm_with_stale_invalid_session_does_not_500(clerk_client, application_cycle):
    session = clerk_client.session
    session[IMPORT_SESSION_KEY] = {
        "metadata": {"submission_cycle_id": "x"},
        "fields": {"p1_identity_number": "K1", "p1_date_of_birth": "bad"},
    }
    session.save()
    response = clerk_client.post(reverse(IMPORT_URL), {"action": "confirm"})
    assert response.status_code == 200
    assert response.context["can_save"] is False
    assert not Application.objects.exists()


def test_parse_date_returns_date_for_datetime():
    value = _parse_date(datetime(2020, 5, 6, 12, 0))
    assert value == date(2020, 5, 6)
    assert type(value) is date


def test_parse_date_errors_are_validation_errors():
    with pytest.raises(ValidationError):
        _parse_date("")
    with pytest.raises(ValidationError):
        _parse_date("2020-02-30")


# ------------------------------------------------------------------ 2 income parsing


def test_parse_decimal_rejects_unparsable_text():
    assert _parse_decimal("") == Decimal("0")
    assert _parse_decimal("28000") == Decimal("28000")
    assert _parse_decimal("€ 1.234,50") == Decimal("1234.50")
    assert _parse_decimal("1,234.50") == Decimal("1234.50")
    assert _parse_decimal("12,5") == Decimal("12.5")
    for bad in ("είκοσι χιλιάδες", "N/A", "-100", "NaN"):
        with pytest.raises(ValidationError):
            _parse_decimal(bad)


@pytest.mark.django_db
def test_import_unparsable_income_blocks_save(clerk_client, application_cycle):
    income = [{**SAMPLE_INCOME[0], "income_total_gross": "πολλά λεφτά", "income_annual_gross": "πολλά λεφτά"}]
    content = make_workbook_bytes(application_cycle["cycle"], income=income)
    response = upload(clerk_client, content)
    assert response.status_code == 200
    assert response.context["can_save"] is False
    assert any("Εισοδήματα γραμμή 1" in e and "πολλά λεφτά" in e for e in _errors(response))

    with pytest.raises(ValidationError):
        save_import(parse_bytes(content))
    assert not Application.objects.exists()


def test_income_totals_sum_rows_per_role():
    parsed = ParsedImport(
        metadata={},
        fields={},
        income_rows=[
            {"income_role": "applicant", "income_total_gross": "10000"},
            {"income_role": "applicant", "income_total_gross": "", "income_annual_gross": "5000"},
            {"income_role": "spouse", "income_total_gross": "7000"},
            {"income_role": "other_family", "income_total_gross": "1000"},
            {"income_role": "other_family", "income_total_gross": "500"},
        ],
    )
    assert _income_totals(parsed) == (Decimal("15000"), Decimal("7000"), Decimal("1500"))


@pytest.mark.django_db
def test_import_multiple_income_rows_are_summed(application_cycle):
    income = [
        {**SAMPLE_INCOME[0], "income_total_gross": "30000"},
        {**SAMPLE_INCOME[0], "income_total_gross": "20000"},
        SAMPLE_INCOME[1],
    ]
    parsed = parse_bytes(make_workbook_bytes(application_cycle["cycle"], income=income))
    assert validate_import(parsed).errors == []
    app = save_import(parsed)
    assert app.person1_income == Decimal("50000")
    assert app.person2_income == Decimal("22000")
    income_check = app.eligibility_checks.get(criterion=EligibilityCheck.Criterion.INCOME)
    assert income_check.overall_result == EligibilityCheck.Result.FAIL


# --------------------------------------------------------- 3 Person 2 missing fields


@pytest.mark.django_db
def test_form_person2_identity_without_dob_is_form_error(clerk_client, application_cycle):
    data = golden_application_post_data(
        application_cycle["cycle"],
        identity="P2-CHECK-1",
        person2_identity_number="P2-NODOB",
        person2_first_name="Ελένη",
        person2_last_name="Δοκιμή",
    )
    response = clerk_client.post(reverse("applications:create"), data)
    assert response.status_code == 200
    form = response.context["form"]
    assert "person2_date_of_birth" in form.errors
    assert "person2_birth_place" in form.errors
    assert not Person.objects.filter(identity_number="P2-NODOB").exists()
    assert not Application.objects.exists()


@pytest.mark.django_db
def test_form_person2_complete_is_saved(clerk_client, application_cycle):
    data = golden_application_post_data(
        application_cycle["cycle"],
        identity="P2-CHECK-2",
        family_type="couple_no_children",
        person2_identity_number="P2-OK",
        person2_first_name="Ελένη",
        person2_last_name="Δοκιμή",
        person2_date_of_birth="1992-01-01",
        person2_birth_place="Λευκωσία",
        person2_birth_country="Κύπρος",
        person2_parents_birth_place="Λευκωσία",
        person2_parents_birth_country="Κύπρος",
    )
    response = clerk_client.post(reverse("applications:create"), data)
    assert response.status_code == 302
    assert Application.objects.get().person2.identity_number == "P2-OK"


@pytest.mark.django_db
def test_import_person2_missing_dob_is_validation_error(clerk_client, application_cycle):
    content = make_workbook_bytes(application_cycle["cycle"], p2={"p2_date_of_birth": None})
    response = upload(clerk_client, content)
    assert response.status_code == 200
    assert response.context["can_save"] is False
    assert any(e.startswith("Πρόσωπο 2") and "Ημερομηνία γέννησης" in e for e in _errors(response))
    assert not Person.objects.exists()


# --------------------------------------------------------------- 4 folder numbering


@pytest.mark.django_db
def test_folder_number_not_reused_after_deletion(clerk_client, application_cycle):
    cycle = application_cycle["cycle"]
    url = reverse("applications:create")
    for idx in (1, 2):
        r = clerk_client.post(
            url, golden_application_post_data(cycle, identity=f"DEL-{idx}", applicant_email=f"d{idx}@example.org")
        )
        assert r.status_code == 302
    first = Application.objects.get(applicant_email="d1@example.org")
    second = Application.objects.get(applicant_email="d2@example.org")
    assert (first.folder_number, second.folder_number) == ("12001001", "12001002")
    first.delete()

    r = clerk_client.post(url, golden_application_post_data(cycle, identity="DEL-3", applicant_email="d3@example.org"))
    assert r.status_code == 302, r.content.decode()[:500]
    assert Application.objects.get(applicant_email="d3@example.org").folder_number == "12001003"


@pytest.mark.django_db
def test_save_with_new_folder_number_retries_on_clash(application_cycle):
    """A number taken outside this community's sequence is skipped instead of raising."""
    cycle = application_cycle["cycle"]
    other = Community.objects.create(
        district="ΛΕΜΕΣΟΥ",
        municipality_type="Κοινότητα",
        municipality="",
        name="ΑΛΛΗ",
        contact_email="other@example.org",
        community_folder_code="999",
    )
    other_cycle = SubmissionCycle.objects.create(
        community=other,
        announcement_date=date(2026, 6, 1),
        submission_start_date=date(2026, 6, 2),
        submission_end_date=date(2026, 7, 1),
        published_at="2026-06-01T10:00:00Z",
    )
    person = Person.objects.create(
        identity_number="CLASH-1",
        first_name="Α",
        last_name="Β",
        date_of_birth=date(1990, 1, 1),
        birth_place="Λ",
        birth_country="Κ",
        parents_birth_place="Λ",
        parents_birth_country="Κ",
    )
    common = dict(person=person, submitted_on=date(2026, 6, 10), family_type="other", applicant_email="c@example.org")
    # Occupies the number the first community would issue next.
    Application.objects.create(submission_cycle=other_cycle, folder_number="12001001", **common)
    assert generate_folder_number(cycle) == "12001001"

    app = save_with_new_folder_number(Application(submission_cycle=cycle, **common), cycle)
    assert app.pk and app.folder_number == "12001002"


# ------------------------------------------------------------ 5 cycle change on edit


@pytest.mark.django_db
def test_edit_cannot_change_submission_cycle(clerk_client, application_cycle):
    cycle = application_cycle["cycle"]
    other_cycle = SubmissionCycle.objects.create(
        community=application_cycle["community"],
        announcement_date=date(2026, 8, 1),
        submission_start_date=date(2026, 8, 2),
        submission_end_date=date(2026, 9, 1),
        published_at=None,
    )
    clerk_client.post(reverse("applications:create"), golden_application_post_data(cycle, identity="EDIT-CYC"))
    app = Application.objects.get()
    url = reverse("applications:edit", args=[app.pk])

    response = clerk_client.post(
        url, golden_application_post_data(other_cycle, identity="EDIT-CYC", applicant_email="new@example.org")
    )
    assert response.status_code == 200
    assert "submission_cycle" in response.context["form"].errors
    app.refresh_from_db()
    assert app.submission_cycle_id == cycle.pk
    assert app.applicant_email == "golden.applicant@example.org"


@pytest.mark.django_db
def test_application_edit_get_and_post(clerk_client, application_cycle):
    cycle = application_cycle["cycle"]
    clerk_client.post(reverse("applications:create"), golden_application_post_data(cycle, identity="EDIT-OK"))
    app = Application.objects.get()
    url = reverse("applications:edit", args=[app.pk])

    get = clerk_client.get(url)
    assert get.status_code == 200
    assert get.context["form"].initial["person1_identity_number"] == "EDIT-OK"

    data = golden_application_post_data(cycle, identity="EDIT-OK", applicant_email="edited@example.org")
    response = clerk_client.post(url, data)
    assert response.status_code == 302
    folder = app.folder_number
    app.refresh_from_db()
    assert app.applicant_email == "edited@example.org"
    assert app.folder_number == folder


# ------------------------------------------------------ 6 configurable income limits


@pytest.mark.django_db
def test_income_limits_default_to_previous_constants():
    assert [_income_limit(n) for n in (1, 2, 3, 4, 5, 8)] == [
        Decimal("45000"),
        Decimal("45000"),
        Decimal("50000"),
        Decimal("55000"),
        Decimal("65000"),
        Decimal("65000"),
    ]


@pytest.mark.django_db
def test_income_limits_read_from_system_settings():
    set_setting("incomeLimitUpTo2Members", "10000")
    set_setting("incomeLimit5PlusMembers", "not-a-number")
    assert _income_limit(2) == Decimal("10000")
    assert _income_limit(6) == Decimal("65000")  # invalid stored value -> default


@pytest.mark.django_db
def test_income_limit_setting_affects_eligibility(clerk_client, application_cycle):
    set_setting("incomeLimitUpTo2Members", "15000")
    clerk_client.post(
        reverse("applications:create"), golden_application_post_data(application_cycle["cycle"], identity="LIM-1")
    )
    app = Application.objects.get()
    results, *_rest, income_limit = evaluate_eligibility(app)
    assert income_limit == Decimal("15000")
    assert results[EligibilityCheck.Criterion.INCOME] == EligibilityCheck.Result.FAIL


def _workflow_post_data(**overrides):
    form = SystemWorkflowSettingsForm()
    data = {name: "" if f.initial is None else f.initial for name, f in form.fields.items()}
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_income_limits_on_settings_screen(admin_client):
    url = reverse("system_settings_workflow")
    html = admin_client.get(url).content.decode()
    assert "Όριο εισοδήματος 10.4.6" in html

    bad = admin_client.post(url, _workflow_post_data(setting_incomeLimit3Members="-5"))
    assert bad.status_code == 200
    assert "θετικό ποσό" in bad.content.decode()
    assert get_setting("incomeLimit3Members", "") == ""

    ok = admin_client.post(url, _workflow_post_data(setting_incomeLimit3Members="52000.50"))
    assert ok.status_code == 302
    assert get_setting("incomeLimit3Members", "") == "52000.50"
    assert _income_limit(3) == Decimal("52000.50")


# ------------------------------------------------------------ previously untested views


@pytest.mark.django_db
def test_application_list_filters(clerk_client, application_cycle):
    cycle = application_cycle["cycle"]
    url = reverse("applications:create")
    clerk_client.post(url, golden_application_post_data(cycle, identity="LIST-1", applicant_email="l1@example.org"))
    clerk_client.post(url, golden_application_post_data(cycle, identity="LIST-2", applicant_email="l2@example.org"))

    response = clerk_client.get(reverse("applications:list"))
    assert response.status_code == 200
    assert len(response.context["applications"]) == 2

    filtered = clerk_client.get(reverse("applications:list"), {"q": "002", "cycle_id": cycle.pk})
    assert [a.folder_number for a in filtered.context["applications"]] == ["12001002"]
    other = clerk_client.get(reverse("applications:list"), {"community_id": 999999})
    assert len(other.context["applications"]) == 0


@pytest.mark.django_db
def test_application_list_requires_login(client):
    assert client.get(reverse("applications:list")).status_code == 302


@pytest.mark.django_db
def test_person_lookup(clerk_client, application_cycle):
    clerk_client.post(
        reverse("applications:create"), golden_application_post_data(application_cycle["cycle"], identity="LOOK-1")
    )
    url = reverse("applications:person_lookup")
    found = clerk_client.get(url, {"identity": "LOOK-1"}).json()
    assert found["found"] is True
    assert found["person"]["date_of_birth"] == "1990-05-15"
    assert found["applications_count"] == 1
    assert found["latest_prefill"]["person1_income"] == "18000.00"
    assert clerk_client.get(url, {"identity": "NOPE"}).json() == {"found": False}
    assert clerk_client.get(url).json() == {"found": False}


@pytest.mark.django_db
def test_person_lookup_forbidden_without_access(client, make_user):
    client.force_login(make_user("nobody-fixes"))
    assert client.get(reverse("applications:person_lookup"), {"identity": "X"}).status_code == 403


@pytest.mark.django_db
def test_person_compare(clerk_client, application_cycle):
    clerk_client.post(
        reverse("applications:create"), golden_application_post_data(application_cycle["cycle"], identity="CMP-1")
    )
    url = reverse("applications:person_compare")
    payload = {
        "first_name": "Μαρία",
        "last_name": "Άλλο",
        "date_of_birth": "1990-05-15",
        "birth_place": "Λευκωσία",
        "birth_country": "Κύπρος",
        "parents_birth_place": "Λευκωσία",
        "parents_birth_country": "Κύπρος",
        "citizenship_cypriot": True,
    }
    body = clerk_client.post(
        url, json.dumps({"identity_number": "CMP-1", "payload": payload}), content_type="application/json"
    ).json()
    assert body["exists"] is True
    assert [d["field"] for d in body["differences"]] == ["last_name"]
    assert "Επίθετο" in body["message"]

    missing = clerk_client.post(
        url, json.dumps({"identity_number": "NEW-1", "payload": payload}), content_type="application/json"
    ).json()
    assert missing["exists"] is False and missing["differences"] == []

    bad_date = clerk_client.post(
        url,
        json.dumps({"identity_number": "CMP-1", "payload": {**payload, "date_of_birth": "15/05/1990"}}),
        content_type="application/json",
    )
    assert bad_date.status_code == 200
    assert "date_of_birth" in [d["field"] for d in bad_date.json()["differences"]]

    assert clerk_client.post(url, "{not json", content_type="application/json").status_code == 400
    assert clerk_client.post(url, "[1, 2]", content_type="application/json").status_code == 400
    assert (
        clerk_client.post(url, json.dumps({"payload": payload}), content_type="application/json").status_code
        == 400
    )
    assert clerk_client.get(url).status_code == 405


@pytest.mark.django_db
def test_full_import_preview_confirm_flow(clerk_client, application_cycle):
    response = clerk_client.get(reverse(IMPORT_URL))
    assert response.status_code == 200

    content = make_workbook_bytes(application_cycle["cycle"])
    preview = upload(clerk_client, content)
    assert preview.status_code == 200
    assert preview.context["can_save"] is True
    assert "Αποθήκευση αίτησης" in preview.content.decode()
    assert not Application.objects.exists()  # preview only

    confirm = clerk_client.post(reverse(IMPORT_URL), {"action": "confirm"})
    assert confirm.status_code == 302
    app = Application.objects.get()
    assert confirm.url == reverse("applications:detail", args=[app.pk])
    assert app.folder_number == "12001001"
    assert app.person.identity_number == "K123456"
    assert app.person2.identity_number == "K654321"
    assert app.person1_income == Decimal("28000")
    assert app.dependent_children.count() == 1
    assert IMPORT_SESSION_KEY not in clerk_client.session
    assert clerk_client.get(confirm.url).status_code == 200

    # Confirm again without a preview in session.
    again = clerk_client.post(reverse(IMPORT_URL), {"action": "confirm"}, follow=True)
    assert "Η προεπισκόπηση έληξε" in again.content.decode()
    assert Application.objects.count() == 1


@pytest.mark.django_db
def test_import_without_file_shows_error(clerk_client, application_cycle):
    response = clerk_client.post(reverse(IMPORT_URL), {})
    assert response.status_code == 200
    assert "Επιλέξτε αρχείο" in response.content.decode()

