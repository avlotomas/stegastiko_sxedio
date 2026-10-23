"""Fixed Person fields (10.3.1): the identity data kept once per ΑΔΤ in the registry."""

# Fields that never change over time and therefore live on Person (10.3.1).
# field_name -> Greek label (UI / import errors)
PERSON_FIELD_LABELS: dict[str, str] = {
    "first_name": "Όνομα",
    "last_name": "Επίθετο",
    "identity_number": "Αρ. Δελτίου Ταυτότητας",
    "date_of_birth": "Ημερομηνία γέννησης",
    "birth_place": "Τόπος γέννησης",
    "birth_country": "Χώρα γέννησης",
    "parents_birth_place": "Τόπος γέννησης γονέων",
    "parents_birth_country": "Χώρα γέννησης γονέων",
}

PERSON_FIXED_FIELD_NAMES: tuple[str, ...] = tuple(PERSON_FIELD_LABELS.keys())
