"""Shared POST payload for applicant application create (UAT §Β.7.5 golden path)."""

from datetime import date

from cases.models import Case, SubmissionCycle
from core.models import Community, SystemSetting


def seed_application_cycle(db=None):
    """Community, case, published submission cycle, and folder numbering settings."""
    community = Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        municipality="",
        name="ΑΓΙΑ ΒΑΡΒΑΡΑ",
        contact_email="community-0001@example.org",
        community_folder_code="001",
    )
    case = Case.objects.create(
        community=community,
        case_number="CASE-GOLD-001",
        start_date=date(2026, 1, 1),
        contact_email="case@example.org",
    )
    cycle = SubmissionCycle.objects.create(
        community=community,
        announcement_date=date(2026, 6, 1),
        submission_start_date=date(2026, 6, 2),
        submission_end_date=date(2026, 7, 1),
        published_at="2026-06-01T10:00:00Z",
    )
    cycle.cases.add(case)
    SystemSetting.objects.update_or_create(
        key="applicationFolderPrefix",
        defaults={"value": "12", "description": "prefix"},
    )
    SystemSetting.objects.update_or_create(
        key="folderSequenceDigits",
        defaults={"value": "3", "description": "digits"},
    )
    return {"community": community, "case": case, "cycle": cycle}


def golden_application_post_data(cycle: SubmissionCycle, identity: str = "GOLD-APP-001", **overrides):
    """Minimal valid POST body for applications:create (includes empty child formset)."""
    data = {
        "submission_cycle": str(cycle.pk),
        "submitted_on": "2026-06-10",
        "family_type": "other",
        "family_type_other": "",
        "applicant_email": "golden.applicant@example.org",
        "comments": "UAT golden path — HTTP/E2E fixture",
        "is_family_type_correct": "",
        "corrected_family_type": "",
        "signatures_status": "",
        "completeness_result": "",
        "completeness_comments": "",
        "person1_identity_number": identity,
        "person1_first_name": "Μαρία",
        "person1_last_name": "Δοκιμή",
        "person1_date_of_birth": "1990-05-15",
        "person1_birth_place": "Λευκωσία",
        "person1_birth_country": "Κύπρος",
        "person1_parents_birth_place": "Λευκωσία",
        "person1_parents_birth_country": "Κύπρος",
        "person1_refugee_identity_number": "",
        "person1_citizenship_cypriot": "on",
        "person1_citizenship_repatriated": "",
        "person1_citizenship_eu": "",
        "person1_citizenship_other": "",
        "person2_identity_number": "",
        "person2_first_name": "",
        "person2_last_name": "",
        "person2_date_of_birth": "",
        "person2_birth_place": "",
        "person2_birth_country": "",
        "person2_parents_birth_place": "",
        "person2_parents_birth_country": "",
        "person2_refugee_identity_number": "",
        "person2_citizenship_cypriot": "",
        "person2_citizenship_repatriated": "",
        "person2_citizenship_eu": "",
        "person2_citizenship_other": "",
        "person1_relationship": "Αιτητής",
        "person2_relationship": "",
        "person1_residence_community": "ΑΓΙΑ ΒΑΡΒΑΡΑ",
        "person2_residence_community": "",
        "person1_residence_address": "1 Δοκιμαστική",
        "person2_residence_address": "",
        "person1_residence_start": "",
        "person2_residence_start": "",
        "residence_category": "",
        "person1_has_property": "",
        "person2_has_property": "",
        "person1_non_alienation_clear": "on",
        "person2_non_alienation_clear": "on",
        "person1_previous_aid_clear": "on",
        "person2_previous_aid_clear": "on",
        "person1_income": "18000.00",
        "person2_income": "0",
        "children_income": "0",
        "children-TOTAL_FORMS": "1",
        "children-INITIAL_FORMS": "0",
        "children-MIN_NUM_FORMS": "0",
        "children-MAX_NUM_FORMS": "1000",
        "children-0-full_name": "",
        "children-0-date_of_birth": "",
        "children-0-category": "",
        "children-0-is_recognized_dependent": "",
        "children-0-DELETE": "",
    }
    data.update(overrides)
    return data
