"""Έκθεση ελέγχου κριτηρίων και επιλεξιμότητας αίτησης παραχώρησης οικοπέδου (PDF).

Χρησιμοποιεί την ίδια κεφαλίδα (Κυπριακή Δημοκρατία, Υπουργείο Εσωτερικών, Επαρχιακή Διοίκηση)
με την εξαγωγή PDF των πινάκων αξιολόγησης καταλληλότητας κρατικής γης (`cases.section6_report_pdf`)
και αποτυπώνει αναλυτικά τα κριτήρια πληρότητας της αίτησης (Ενότ. 5, 20.2) και τα κριτήρια
επιλεξιμότητας δικαιούχου (Ενότ. 10, 11, 20.3) με τους λόγους/σημειώσεις και χρωματική κωδικοποίηση
(πράσινο / κόκκινο) όπως στην οθόνη προβολής της αίτησης.
"""

from __future__ import annotations

from django.utils import timezone

from cases.pdf_rendering import render_pdf, safe_case_number
from plot_applications.models import PlotApplication
from plot_applications.rules import evaluate

REPORT_TITLE = "ΕΛΕΓΧΟΣ ΚΡΙΤΗΡΙΩΝ ΚΑΙ ΕΠΙΛΕΞΙΜΟΤΗΤΑΣ ΑΙΤΗΣΗΣ"


def eligibility_report_context(application: PlotApplication) -> dict:
    outcome = evaluate(application)
    return {
        "application": application,
        "outcome": outcome,
        "report_title": REPORT_TITLE,
        "issued_at": timezone.localtime(),
    }


def render_eligibility_report_pdf(application: PlotApplication) -> bytes:
    return render_pdf(
        "plot_applications/pdf/eligibility_report.html",
        eligibility_report_context(application),
    )


def eligibility_report_pdf_filename(application: PlotApplication) -> str:
    return f"elegchos_kritirion_{safe_case_number(application.protocol_number)}.pdf"
