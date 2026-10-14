"""Παράρτημα 1 του Σχεδίου: κατάλογος Κοινοτήτων / Περιοχών ανά Επαρχία.

Τα δεδομένα βρίσκονται στο `core/data/appendix1_communities.json` (district, municipality, name) και
προέρχονται από το έγγραφο του Παραρτήματος 1. Αν το ΥΠΕΣ τροποποιήσει τον κατάλογο (Ενότ. 19),
αντικαθίσταται μόνο το αρχείο.
"""

import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "appendix1_communities.json"


@lru_cache(maxsize=1)
def appendix1_communities() -> tuple[dict, ...]:
    with DATA_FILE.open(encoding="utf-8") as fp:
        return tuple(json.load(fp))


def appendix1_choices() -> list:
    """Επιλογές για ChoiceField, ομαδοποιημένες ανά Επαρχία· τιμή = όνομα όπως στο Παράρτημα 1."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for entry in appendix1_communities():
        label = entry["name"] + (f" ({entry['municipality']})" if entry["municipality"] else "")
        groups.setdefault(entry["district"], []).append((entry["name"], label))
    return [("", "---------")] + [(f"Επαρχία {district}", items) for district, items in groups.items()]
