"""Shared helpers of the case views: section configuration, access checks, navigation."""

from django.http import Http404
from django.shortcuts import get_object_or_404

from cases import section_refs as refs
from cases.forms import (
    LandPlotDecisionFormSet,
    Section1Form,
    Section2Form,
    Section3Form,
    Section4Form,
    Section6Form,
    Section7Form,
)
from cases.models import Case
from cases.section_labels import case_section_heading
from cases.subsection_labels import CASE_SUBSECTION_LABEL_KEYS, case_subsection_heading
from core.function_catalog import DELETE, EDIT, FUNCTIONS_BY_CODE, VIEW, case_section_function
from core.permissions import has_access, require_access

# Each entry drives one action screen of the Κ.Σ./Δ.Δ. application: the label shown on
# the case folder, a short description, the main Case form and its inline formsets
# (prefix, formset class, legend / subsection label key).
SECTIONS = {
    refs.SECTION_1: {
        "title": "Ενότητα 1 — Δεδομένα αίτησης Κ.Σ. / Δ.Δ.",
        "action": "Βασικά στοιχεία και προτεραιότητα",
        "summary": "1.1 στοιχεία υπόθεσης, 1.2 χαρακτηριστικά προτεραιότητας, 1.3 σχόλια.",
        "form": Section1Form,
        "formsets": (),
    },
    refs.SECTION_2: {
        "title": "Ενότητα 2 — Έλεγχος πληρότητας αίτησης Κ.Σ.",
        "action": "Έλεγχος πληρότητας",
        "summary": "Επαναλαμβανόμενος πίνακας ελέγχων με ελλείψεις και email.",
        "form": Section2Form,
        "formsets": (),
    },
    refs.SECTION_3: {
        "title": "Ενότητα 3 — Στοιχεία τεμαχίων",
        "action": "Στοιχεία τεμαχίων",
        "summary": "3.1 πίνακας τεμαχίων, 3.2 έλεγχος επάρκειας κρατικής γης, 3.3 σχόλια.",
        "form": Section3Form,
        # 3.1 plots are edited one at a time from the grid modal (land_plot_form).
        "formsets": (),
    },
    refs.SECTION_4: {
        "title": "Ενότητα 4 — Τεχνική αξιολόγηση καταλληλότητας",
        "action": "Τεχνική αξιολόγηση",
        "summary": "4.1 αξιολόγηση ανά τεμάχιο, 4.2 υπηρεσίες, 4.3 πρόσβαση, 4.4 αρχεία, 4.5 σχόλια, 4.6 επίσκεψη.",
        "form": Section4Form,
        # 4.1 rows follow the 3.1 plots (land_plot_evaluation_form); 4.2 rows have their own
        # grid modal (utility_service_form).
        "formsets": (),
    },
    refs.SECTION_5: {
        "title": "Ενότητα 5 — Διαβουλεύσεις με Τμήματα / Υπηρεσίες",
        "action": "Διαβουλεύσεις καταλληλότητας",
        "summary": "Μία γραμμή ανά διαβούλευση· η κατάσταση είναι αυτόματη.",
        "form": None,
        # Rows are edited one at a time from the grid modal (consultation_form).
        "formsets": (),
    },
    refs.SECTION_6: {
        "title": "Ενότητα 6 — Αξιολόγηση καταλληλότητας",
        "action": "Απόφαση καταλληλότητας",
        "summary": "6.1–6.5 συνοπτικοί πίνακες, 6.6 απόφαση ανά τεμάχιο, 6.7 λήψη απόφασης από υπουργό.",
        "form": Section6Form,
        "formsets": (
            ("plot_decisions", LandPlotDecisionFormSet, refs.REF_PLOT_DECISIONS),
        ),
    },
    refs.SECTION_7: {
        "title": "Ενότητα 7 — Σχεδιασμός και υλοποίηση διαχωρισμού (7.1–7.7)",
        "action": "Σχεδιασμός και υλοποίηση διαχωρισμού",
        "summary": "Ανάθεση μελέτης, ΤΠΟ, κατασκευαστικά σχέδια και διαβουλεύσεις, διαγωνισμός, έλεγχοι κατασκευαστικών εργασιών και αίτηση στο ΤΚΧ.",
        "form": Section7Form,
        # 7.3, 7.4 and 7.6 rows are edited from their grid modals.
        "formsets": (),
    },
}

SECTION_ORDER = list(SECTIONS)


def wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def disable_fields(form):
    for field in form.fields.values():
        field.disabled = True


def delete_action_for(section):
    """«Διαγραφή» where the section defines it, otherwise «Επεξεργασία»."""
    function = FUNCTIONS_BY_CODE[case_section_function(section)]
    return DELETE if DELETE in function.actions else EDIT


def case_for_section(request, pk, section, action=VIEW):
    """The case of a section screen, after the access check of `action` on that section."""
    require_access(request.user, case_section_function(section), action)
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    if section not in case.applicable_sections:
        raise Http404("Η ενότητα δεν ισχύει για αυτόν τον τύπο διαδικασίας.")
    return case


def _resolve_formset_legend(legend: str) -> str:
    if legend in CASE_SUBSECTION_LABEL_KEYS:
        return case_subsection_heading(legend)
    return legend


def build_formsets(section_key, case, data=None, files=None):
    """Instantiate the inline formsets of a section, scoped to the case."""
    formsets = []
    for prefix, formset_class, legend in SECTIONS[section_key]["formsets"]:
        legend = _resolve_formset_legend(legend)
        kwargs = {"instance": case, "prefix": prefix}
        formsets.append((legend, formset_class(data, files, **kwargs)))
    return formsets


def section_screens_for(case):
    """Sections of this case that are edited through the generic section screen."""
    applicable = case.applicable_sections
    return [key for key in SECTION_ORDER if key in applicable]


def case_nav_items(case, user, active_key=None):
    """Sidebar navigation for case work screens (sections 1–7) the user may view."""
    return [
        {
            "key": key,
            "action": case_section_heading(key),
            "summary": SECTIONS[key]["summary"],
            "title": case_section_heading(key),
            "is_active": active_key == key,
        }
        for key in section_screens_for(case)
        if has_access(user, case_section_function(key))
    ]
