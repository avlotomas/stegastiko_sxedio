"""Named section / subsection references of the Κ.Σ./Δ.Δ. application (Ενότητες 1–7).

`section_ref` values are written to the action history and to `Attachment.section_ref`,
so changing a value here changes what is stored: keep them stable.
"""

# Top-level sections (keys of the section screens and of `case_section_<n>` functions).
SECTION_1 = "1"
SECTION_2 = "2"
SECTION_3 = "3"
SECTION_4 = "4"
SECTION_5 = "5"
SECTION_6 = "6"
SECTION_7 = "7"
SECTION_8 = "8"

# Ενότητα 2
REF_COMPLETENESS_CHECKS = "2.1"
REF_DEFICIENCY_EMAIL = "2.2"

# Ενότητα 3
REF_LAND_PLOTS = "3.1"
REF_LAND_PLOT_EMAIL = "3.1-email"

# Ενότητα 4
REF_PLOT_EVALUATION = "4.1"
REF_UTILITY_SERVICES = "4.2"
REF_TECHNICAL_FILES = "4.4"

# Ενότητα 5 (suitability consultations keep the bare section number)
REF_SUITABILITY_CONSULTATIONS = SECTION_5

# Ενότητα 6
REF_PLOT_DECISIONS = "6.6"
REF_MINISTRY_DECISIONS = "6.7"
REF_MINISTRY_RECOMMENDATION_FILES = "6.7-rec"
REF_MINISTRY_RESPONSE_FILES = "6.7-res"

# Ενότητα 7
REF_DIVISION_DESIGN = "7.2"
REF_APPROVED_DESIGN_PLOTS = "7.3"
REF_TPO_APPLICATION = "7.3"
REF_DIVISION_CONSULTATIONS = "7.4"
REF_INFRASTRUCTURE_CHECKS = "7.6"
REF_DLS_APPLICATION = "7.7"

# Ενότητα 8
REF_TKX_NUMBERING = "8.1"
REF_PLOT_MAPPING = "8.2"
# Subsection label keys of the Ενότητα 8 inline formsets (see cases.subsection_labels).
LABEL_FIELDS = "8.2-fields"
LABEL_VALUATION_REFERRALS = "8.2-referrals"
