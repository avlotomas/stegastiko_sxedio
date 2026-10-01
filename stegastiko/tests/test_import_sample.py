from datetime import date
from pathlib import Path

import pytest
from django.core.management import call_command

from applications.import_reader import parse_import_workbook
from applications.import_services import save_import, validate_import
from cases.models import Case, SubmissionCycle
from core.models import Community, SystemSetting


@pytest.fixture
def import_demo(db):
    call_command("seed_import_demo")
    return SubmissionCycle.objects.get(pk=1)


@pytest.mark.django_db
def test_sample_workbook_import(import_demo):
    sample = (
        Path(__file__).resolve().parents[2] / "application_import_appendix3_v1.0.1_SAMPLE.xlsx"
    )
    if not sample.exists():
        call_command(
            "generate_application_import_sample",
            output=str(sample),
        )
    with sample.open("rb") as fp:
        parsed = parse_import_workbook(fp)
    validation = validate_import(parsed)
    assert not validation.errors
    app = save_import(parsed)
    assert app.folder_number.startswith("12001")
    assert app.person.identity_number == "K123456"
    assert app.dependent_children.count() == 1
