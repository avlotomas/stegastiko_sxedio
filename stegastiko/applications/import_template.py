"""Appendix 3 operator import template (§9.2). Version must match sheet «Μεταδεδομένα»."""

TEMPLATE_VERSION = "1.0.1"

# First release: one active SubmissionCycle row in the database (see §9, example ABΓ).
DEFAULT_SUBMISSION_CYCLE_ID = 1

# (field_key, Greek label, optional hint)
METADATA_FIELDS = [
    ("template_version", "Έκδοση προτύπου", f"Μη τροποποιείται — {TEMPLATE_VERSION}"),
    (
        "submission_cycle_id",
        "Κύκλος υποβολής (Ενότητα 9)",
        f"Προς το παρόν σταθερό = {DEFAULT_SUBMISSION_CYCLE_ID} — μη τροποποιείτε",
    ),
    ("community_code", "Κωδικός Κοινότητας / Δ.Δ. (Παράρτημα 1)", ""),
    ("community_name", "Κοινότητα παραχώρησης οικοπέδου", "Όπως στο Παράρτημα 3"),
    ("protocol_number", "Αρ. πρωτοκόλλησης (επίσημη χρήση)", "Προαιρετικό"),
    ("received_on", "Ημερομηνία παραλαβής", "YYYY-MM-DD"),
]

APPLICATION_FIELDS = [
    ("submitted_on", "Ημερομηνία υποβολής αίτησης", "YYYY-MM-DD · 10.1"),
    ("applicant_email", "Ηλεκτρονική διεύθυνση αιτητή", "10.1 · επίσημη επικοινωνία"),
    (
        "family_type",
        "Τύπος οικογένειας",
        "with_children | couple_no_children | single_parent | other",
    ),
    ("family_type_other", "Τύπος οικογένειας — Άλλο (κείμενο)", "Αν family_type=other"),
    ("declared_children_count", "Αριθμός τέκνων (δήλωση)", "Ακέραιος"),
    ("family_married", "Έγγαμος", "Ναι | Όχι"),
    ("family_civil_union", "Σύμφωνο συμβίωσης", "Ναι | Όχι"),
    ("family_single_parent", "Μονογονεϊκή οικογένεια", "Ναι | Όχι"),
    ("family_widow", "Χήρος/α", "Ναι | Όχι"),
    ("family_divorced", "Διαζευγμένος/η", "Ναι | Όχι"),
    ("comments", "Σχόλια λειτουργού", ""),
]

PERSON1_FIELDS = [
    ("p1_first_name", "Όνομα αιτητή/αιτήτριας", ""),
    ("p1_last_name", "Επίθετο", ""),
    ("p1_identity_number", "Αρ. Δελτίου Ταυτότητας", "Υποχρεωτικό"),
    ("p1_social_insurance_number", "Αρ. Κοινωνικών Ασφαλίσεων", ""),
    ("p1_refugee_id", "Αρ. Προσφυγικής Ταυτότητας", "Όπου εφαρμόζεται"),
    ("p1_citizenship_cypriot", "Κύπριος Πολίτης", "Ναι | Όχι"),
    ("p1_citizenship_repatriated", "Επαναπατρισθείς/είσα Κύπριος/α", "Ναι | Όχι"),
    ("p1_date_of_birth", "Ημερομηνία γέννησης", "YYYY-MM-DD"),
    ("p1_birth_place", "Τόπος γέννησης", ""),
    ("p1_birth_country", "Χώρα γέννησης", ""),
    ("p1_parents_birth_place", "Τόπος γέννησης γονέων", ""),
    ("p1_parents_birth_country", "Χώρα γέννησης γονέων", ""),
    ("p1_mobile_phone", "Τηλέφωνο κινητό", ""),
    ("p1_landline_phone", "Τηλέφωνο σταθερό", ""),
    ("p1_mailing_street", "Διεύθυνση αλληλογραφίας — Οδός", ""),
    ("p1_mailing_number", "Διεύθυνση αλληλογραφίας — Αριθμός", ""),
    ("p1_mailing_apartment", "Διεύθυνση αλληλογραφίας — Διαμέρισμα", ""),
    ("p1_mailing_community", "Διεύθυνση αλληλογραφίας — Κοινότητα/Δ.Δ.", ""),
    ("p1_mailing_postal_code", "Διεύθυνση αλληλογραφίας — Ταχ. κωδ.", ""),
    ("p1_mailing_district", "Διεύθυνση αλληλογραφίας — Επαρχία", ""),
    ("p1_employment_self_employed", "Επαγγελματική κατάσταση — Αυτοτελώς εργαζόμενος", "Ναι | Όχι"),
    ("p1_employment_employee", "Επαγγελματική κατάσταση — Μισθωτός", "Ναι | Όχι"),
    ("p1_employment_unemployed", "Επαγγελματική κατάσταση — Άνεργος", "Ναι | Όχι"),
    ("p1_employment_disability", "Επαγγελματική κατάσταση — Άτομο με αναπηρία", "Ναι | Όχι"),
    ("p1_employer_info", "Εργοδότης (πληροφορίες)", ""),
]

PERSON2_FIELDS = [
    ("p2_first_name", "Όνομα συζύγου/συμβίου", ""),
    ("p2_last_name", "Επίθετο", ""),
    ("p2_identity_number", "Αρ. Δελτίου Ταυτότητας", ""),
    ("p2_social_insurance_number", "Αρ. Κοινωνικών Ασφαλίσεων", ""),
    ("p2_refugee_id", "Αρ. Προσφυγικής Ταυτότητας", ""),
    ("p2_alien_registration", "Alien Registration Certificate", "Όπου εφαρμόζεται"),
    ("p2_citizenship_cypriot", "Κύπριος Πολίτης", "Ναι | Όχι"),
    ("p2_citizenship_eu", "Πολίτης κράτους μέλους ΕΕ", "Ναι | Όχι"),
    ("p2_citizenship_other", "Άλλη υπηκοότητα (κείμενο)", ""),
    ("p2_citizenship_repatriated", "Επαναπατρισθείς/είσα Κύπριος/α", "Ναι | Όχι"),
    ("p2_date_of_birth", "Ημερομηνία γέννησης", "YYYY-MM-DD"),
    ("p2_birth_place", "Τόπος γέννησης", ""),
    ("p2_birth_country", "Χώρα γέννησης", ""),
    ("p2_parents_birth_place", "Τόπος γέννησης γονέων", ""),
    ("p2_parents_birth_country", "Χώρα γέννησης γονέων", ""),
    ("p2_mobile_phone", "Τηλέφωνο κινητό", ""),
    ("p2_landline_phone", "Τηλέφωνο σταθερό", ""),
    ("p2_employment_self_employed", "Επαγγελματική κατάσταση — Αυτοτελώς εργαζόμενος", "Ναι | Όχι"),
    ("p2_employment_employee", "Επαγγελματική κατάσταση — Μισθωτός", "Ναι | Όχι"),
    ("p2_employment_unemployed", "Επαγγελματική κατάσταση — Άνεργος", "Ναι | Όχι"),
    ("p2_employment_disability", "Επαγγελματική κατάσταση — Άτομο με αναπηρία", "Ναι | Όχι"),
    ("p2_employer_info", "Εργοδότης (πληροφορίες)", ""),
]

RESIDENCE_DECLARATION_FIELDS = [
    (
        "residence_category",
        "Κατηγορία διαμονής (10.4.3)",
        "A | B | C | D (Αυτόχθονας/Εκτοπισθείς | Απόδημος εσωτερικού | Επαναπατρισθείς/απόδημος εξωτερικού | Γειτονική κοινότητα)",
    ),
    ("p1_residence_street", "Τόπος διαμονής Π1 — Οδός", "10.3.4"),
    ("p1_residence_number", "Τόπος διαμονής Π1 — Αριθμός", ""),
    ("p1_residence_apartment", "Τόπος διαμονής Π1 — Διαμέρισμα", ""),
    ("p1_residence_community", "Τόπος διαμονής Π1 — Κοινότητα/Δ.Δ.", ""),
    ("p1_residence_postal_code", "Τόπος διαμονής Π1 — Ταχ. κωδ.", ""),
    ("p1_residence_start", "Τόπος διαμονής Π1 — Έναρξη διαμονής", "YYYY-MM-DD"),
    ("p1_residence_period_notes", "Π1 — Περιγραφή περιόδων διαμονής / διακοπών", "Ενότητα 2 Παράρτημα 3"),
    ("p1_residence_origin_parent", "Π1 — Καταγωγή από κοινότητα (ποιος γονέας)", "Κατηγορία Β"),
    ("p1_residence_past_community_address", "Π1 — Διεύθυνση στην κοινότητα (παλαιά διαμονή)", "Κατηγορία Β"),
    ("p1_residence_past_period", "Π1 — Περίοδος μόνιμης κατοίκησης στην κοινότητα", "από-μέχρι"),
    ("p1_residence_three_year_period", "Π1 — Τριετής διαμονή (κατ. Γ α)", "από-μέχρι"),
    ("p1_residence_ten_year_abroad", "Π1 — Δεκαετής παραμονή εξωτερικού (κατ. Γ β)", "από-μέχρι"),
    ("neighbor_community_name", "Γειτονική κοινότητα (κατ. Δ)", "Από κατάλογο 15 χλμ."),
    ("p2_residence_community", "Τόπος διαμονής Π2 — Κοινότητα/Δ.Δ.", ""),
    ("p2_residence_address", "Τόπος διαμονής Π2 — Διεύθυνση (πλήρης)", ""),
    ("p2_residence_start", "Τόπος διαμονής Π2 — Έναρξη διαμονής", "YYYY-MM-DD"),
]

CHILDREN_COLUMNS = [
    ("child_seq", "Α/Α", ""),
    ("child_first_name", "Όνομα", ""),
    ("child_last_name", "Επίθετο", ""),
    ("child_date_of_birth", "Ημερομηνία γέννησης", "YYYY-MM-DD"),
    ("child_identity_number", "Αρ. Δελτίου Ταυτότητας", ""),
    (
        "child_status",
        "Κατάσταση",
        "minor | student | national_guard | adult_disability",
    ),
    ("child_is_recognized_dependent", "Αναγνωρισμένο εξαρτώμενο τέκνο (10.3.2)", "Ναι | Όχι"),
]

INCOME_COLUMNS = [
    ("income_role", "Ρόλος", "applicant | spouse | other_family"),
    ("income_employee", "Μισθωτός εργαζόμενος", "Ναι | Όχι"),
    ("income_self_employed", "Αυτοτελώς εργαζόμενος", "Ναι | Όχι"),
    ("income_unemployed", "Άνεργος", "Ναι | Όχι"),
    ("income_annual_gross", "Ετήσιο ακαθάριστο εισόδημα (μισθός)", "€ · 10.4.6"),
    ("income_other_source_1", "Εισόδημα άλλες πηγές 1", "€"),
    ("income_other_source_2", "Εισόδημα άλλες πηγές 2", "€"),
    ("income_other_source_3", "Εισόδημα άλλες πηγές 3", "€"),
    ("income_total_gross", "Συνολικό ακαθάριστο εισόδημα", "€"),
]

OTHER_DECLARATIONS_FIELDS = [
    ("property_residence_yes", "Άλλη ακίνητη ιδιοκτησία (α) κατοικία — Ναι", "Ναι | Όχι · 10.4.4"),
    ("property_residence_explanation", "Άλλη ακίνητη ιδιοκτησία (α) — επεξήγηση", ""),
    ("property_land_yes", "Άλλη ακίνητη ιδιοκτησία (β) οικόπεδο/γη — Ναι", "Ναι | Όχι"),
    ("property_land_explanation", "Άλλη ακίνητη ιδιοκτησία (β) — επεξήγηση", ""),
    ("property_alienation_yes", "Αποξένωση τελευταία 3 έτη (γ) — Ναι", "Ναι | Όχι · 10.4.5"),
    ("property_alienation_explanation", "Αποξένωση (γ) — επεξήγηση", ""),
    ("previous_housing_aid_yes", "Προηγούμενη κρατική στεγαστική βοήθεια — Ναι", "Ναι | Όχι · 10.4.7"),
    ("previous_housing_aid_explanation", "Προηγούμενη στεγαστική βοήθεια — επεξήγηση", ""),
    ("other_application_pref_1", "Άλλη αίτηση — 1η επιλογή (κοινότητα)", ""),
    ("other_application_pref_2", "Άλλη αίτηση — 2η επιλογή", ""),
    ("other_application_pref_3", "Άλλη αίτηση — 3η επιλογή", ""),
    ("other_applications_notes", "Άλλες αιτήσεις — πρόσθετες πληροφορίες", ""),
    ("affidavit_signed_on", "Ενόρκως — ημερομηνία υπογραφής αίτησης", "YYYY-MM-DD · αρχείο μόνο"),
    ("affidavit_district_office", "Ενόρκως — Έπαρχος (κείμενο)", ""),
]

SUPPORTING_DOC_COLUMNS = [
    ("document_code", "Κωδικός δικαιολογητικού (10.2.2)", "Από κατάλογο συστήματος"),
    ("document_status", "Κατάσταση", "ΝΑΙ | ΟΧΙ | ΔΕΝ ΑΠΑΙΤΕΙΤΑΙ"),
    ("document_comments", "Σχόλια", ""),
]

INSTRUCTIONS_GREEK = """Οδηγίες συμπλήρωσης (Παράρτημα 3 · αρχείο εισαγωγής λειτουργού §9)

1. Συμπληρώστε ένα αρχείο ανά αίτηση πολίτη (μία γραμμή στα φύλλα Αίτηση, Πρόσωπο1, Πρόσωπο2, Δηλώσεις).
2. Στο φύλλο «Μεταδεδομένα» μην αλλάξετε template_version ούτε submission_cycle_id (προς το παρόν πάντα 1)· η Κοινότητα δηλώνεται με community_code / community_name.
3. Ημερομηνίες: YYYY-MM-DD. Ναι/Όχι: γράψτε ακριβώς «Ναι» ή «Όχι» (ή ΝΑΙ/ΟΧΙ για δικαιολογητικά).
4. Τέκνα: μία γραμμή ανά τέκνο στο φύλλο «Τέκνα».
5. Εισοδήματα: μία γραμμή ανά πρόσωπο (αιτητής, σύζυγος, άλλο μέλος) στο φύλλο «Εισοδήματα».
6. Δικαιολογητικά: κωδικοί από τον επίσημο κατάλογο 10.2.2 — μία γραμμή ανά δικαιολογητικό.
7. Το αρχείο δεν αντικαθιστά το πρωτότυπο έντυπο Παράρτημα 3· μετά το upload γίνεται προεπισκόπηση πριν την αποθήκευση.

Έκδοση προτύπου: {version}
"""
