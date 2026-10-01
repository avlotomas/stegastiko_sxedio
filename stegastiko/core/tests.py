from core.forms import label_without_section_reference, split_section_reference


def test_split_section_reference_single():
    assert split_section_reference("8.1 Ημερομηνία ανάθεσης μελέτης") == (
        "8.1",
        "Ημερομηνία ανάθεσης μελέτης",
    )


def test_split_section_reference_compound_consultation_fields():
    assert split_section_reference("5 / 8.4 Τμήμα / Υπηρεσία") == (
        "8.4",
        "Τμήμα / Υπηρεσία",
    )
    assert label_without_section_reference("5 / 8.4 Θέμα διαβούλευσης") == "Θέμα διαβούλευσης"
