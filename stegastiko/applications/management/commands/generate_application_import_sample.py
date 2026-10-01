from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from applications.import_template import TEMPLATE_VERSION
from applications.management.commands.generate_application_import_template import build_workbook


SAMPLE_METADATA = {
    "template_version": TEMPLATE_VERSION,
    "submission_cycle_id": "1",
    "community_code": "001",
    "community_name": "ΑΓΙΑ ΒΑΡΒΑΡΑ",
    "protocol_number": "ΠΡΩΤ-2026-0042",
    "received_on": "2026-06-15",
}

SAMPLE_APPLICATION = {
    "submitted_on": "2026-06-14",
    "applicant_email": "andreas.papadopoulos@example.cy",
    "family_type": "with_children",
    "family_type_other": "",
    "declared_children_count": "1",
    "family_married": "Ναι",
    "family_civil_union": "Όχι",
    "family_single_parent": "Όχι",
    "family_widow": "Όχι",
    "family_divorced": "Όχι",
    "comments": "Δείγμα αρχείου εισαγωγής — δοκιμή συστήματος",
}

SAMPLE_P1 = {
    "p1_first_name": "Ανδρέας",
    "p1_last_name": "Παπαδόπουλος",
    "p1_identity_number": "K123456",
    "p1_social_insurance_number": "1234567890",
    "p1_refugee_id": "",
    "p1_citizenship_cypriot": "Ναι",
    "p1_citizenship_repatriated": "Όχι",
    "p1_date_of_birth": "1988-03-12",
    "p1_birth_place": "Λευκωσία",
    "p1_birth_country": "Κύπρος",
    "p1_parents_birth_place": "Πάφος",
    "p1_parents_birth_country": "Κύπρος",
    "p1_mobile_phone": "99123456",
    "p1_landline_phone": "22456789",
    "p1_mailing_street": "Λεωφόρος Αρχιεπισκόπου Μακαρίου",
    "p1_mailing_number": "45",
    "p1_mailing_apartment": "",
    "p1_mailing_community": "Αγία Βαρβάρα",
    "p1_mailing_postal_code": "2700",
    "p1_mailing_district": "Λευκωσία",
    "p1_employment_self_employed": "Όχι",
    "p1_employment_employee": "Ναι",
    "p1_employment_unemployed": "Όχι",
    "p1_employment_disability": "Όχι",
    "p1_employer_info": "Δήμος Λευκωσίας",
}

SAMPLE_P2 = {
    "p2_first_name": "Μαρία",
    "p2_last_name": "Παπαδόπουλου",
    "p2_identity_number": "K654321",
    "p2_social_insurance_number": "0987654321",
    "p2_refugee_id": "",
    "p2_alien_registration": "",
    "p2_citizenship_cypriot": "Ναι",
    "p2_citizenship_eu": "Όχι",
    "p2_citizenship_other": "",
    "p2_citizenship_repatriated": "Όχι",
    "p2_date_of_birth": "1990-07-22",
    "p2_birth_place": "Λεμεσός",
    "p2_birth_country": "Κύπρος",
    "p2_parents_birth_place": "Λεμεσός",
    "p2_parents_birth_country": "Κύπρος",
    "p2_mobile_phone": "99765432",
    "p2_landline_phone": "",
    "p2_employment_self_employed": "Όχι",
    "p2_employment_employee": "Ναι",
    "p2_employment_unemployed": "Όχι",
    "p2_employment_disability": "Όχι",
    "p2_employer_info": "Ιδιωτικός τομέας",
}

SAMPLE_RESIDENCE = {
    "residence_category": "A",
    "p1_residence_street": "Κεντρική",
    "p1_residence_number": "12",
    "p1_residence_apartment": "",
    "p1_residence_community": "Αγία Βαρβάρα",
    "p1_residence_postal_code": "2700",
    "p1_residence_start": "2015-01-01",
    "p1_residence_period_notes": "",
    "p1_residence_origin_parent": "",
    "p1_residence_past_community_address": "",
    "p1_residence_past_period": "",
    "p1_residence_three_year_period": "",
    "p1_residence_ten_year_abroad": "",
    "neighbor_community_name": "",
    "p2_residence_community": "Αγία Βαρβάρα",
    "p2_residence_address": "Κεντρική 12",
    "p2_residence_start": "2015-01-01",
}

SAMPLE_DECLARATIONS = {
    "property_residence_yes": "Όχι",
    "property_residence_explanation": "",
    "property_land_yes": "Όχι",
    "property_land_explanation": "",
    "property_alienation_yes": "Όχι",
    "property_alienation_explanation": "",
    "previous_housing_aid_yes": "Όχι",
    "previous_housing_aid_explanation": "",
    "other_application_pref_1": "Αγία Βαρβάρα (παρούσα αίτηση)",
    "other_application_pref_2": "",
    "other_application_pref_3": "",
    "other_applications_notes": "",
    "affidavit_signed_on": "2026-06-14",
    "affidavit_district_office": "Λευκωσίας",
}

SAMPLE_CHILDREN = [
    {
        "child_seq": "1",
        "child_first_name": "Χριστίνα",
        "child_last_name": "Παπαδόπουλου",
        "child_date_of_birth": "2014-11-05",
        "child_identity_number": "",
        "child_status": "minor",
        "child_is_recognized_dependent": "Ναι",
    }
]

SAMPLE_INCOME = [
    {
        "income_role": "applicant",
        "income_employee": "Ναι",
        "income_self_employed": "Όχι",
        "income_unemployed": "Όχι",
        "income_annual_gross": "28000",
        "income_other_source_1": "",
        "income_other_source_2": "",
        "income_other_source_3": "",
        "income_total_gross": "28000",
    },
    {
        "income_role": "spouse",
        "income_employee": "Ναι",
        "income_self_employed": "Όχι",
        "income_unemployed": "Όχι",
        "income_annual_gross": "22000",
        "income_other_source_1": "",
        "income_other_source_2": "",
        "income_other_source_3": "",
        "income_total_gross": "22000",
    },
]


def _fill_metadata(ws):
    for row in ws.iter_rows(min_row=2):
        key = row[0].value
        if key in SAMPLE_METADATA:
            row[2].value = SAMPLE_METADATA[key]


def _fill_horizontal(ws, values: dict):
    for col_idx, cell in enumerate(ws[2], start=1):
        key = cell.value
        if key in values:
            ws.cell(row=4, column=col_idx, value=values[key])


def _fill_table(ws, rows: list[dict]):
    keys = [c.value for c in ws[2]]
    for row_offset, row_data in enumerate(rows):
        for col_idx, key in enumerate(keys, start=1):
            if key in row_data:
                ws.cell(row=4 + row_offset, column=col_idx, value=row_data[key])


class Command(BaseCommand):
    help = "Write a filled sample Excel for application import testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="Output path (default: project root sample xlsx)",
        )

    def handle(self, *args, **options):
        out = options["output"]
        if not out:
            out = (
                Path(settings.BASE_DIR).parent
                / f"application_import_appendix3_v{TEMPLATE_VERSION}_SAMPLE.xlsx"
            )
        else:
            out = Path(out)

        wb = build_workbook()
        _fill_metadata(wb["Μεταδεδομένα"])
        _fill_horizontal(wb["Αίτηση"], SAMPLE_APPLICATION)
        _fill_horizontal(wb["Πρόσωπο1"], SAMPLE_P1)
        _fill_horizontal(wb["Πρόσωπο2"], SAMPLE_P2)
        _fill_horizontal(wb["Διαμονή"], SAMPLE_RESIDENCE)
        _fill_horizontal(wb["Δηλώσεις"], SAMPLE_DECLARATIONS)
        _fill_table(wb["Τέκνα"], SAMPLE_CHILDREN)
        _fill_table(wb["Εισοδήματα"], SAMPLE_INCOME)
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out)
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))
