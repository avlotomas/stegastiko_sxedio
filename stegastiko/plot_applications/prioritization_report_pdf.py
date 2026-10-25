"""Κατάλογος προτεραιοποίησης αιτήσεων παραχώρησης οικοπέδου ανά Κοινότητα (PDF, A4 landscape).

Ίδια κεφαλίδα και μορφή πινάκων με την εξαγωγή των πινάκων αξιολόγησης (`cases.section6_report_pdf`).
Για τους δικαιούχους αποτυπώνονται τα κριτήρια προτεραιοποίησης (Ενότ. 11) και για τους μη
δικαιούχους ο λόγος (Ενότ. 10, 20 ή χειροκίνητη αλλαγή με αιτιολογία — Ενότ. 6).
"""

from __future__ import annotations

from django.utils import timezone

from cases.pdf_rendering import render_pdf
from plot_applications.prioritization import build_prioritization_list

REPORT_TITLE = "ΚΑΤΑΛΟΓΟΣ ΠΡΟΤΕΡΑΙΟΠΟΙΗΣΗΣ ΑΙΤΗΣΕΩΝ ΠΑΡΑΧΩΡΗΣΗΣ ΟΙΚΟΠΕΔΟΥ"


def prioritization_report_context(community) -> dict:
    return {
        "community": community,
        "prioritization": build_prioritization_list(community),
        "report_title": REPORT_TITLE,
        "issued_at": timezone.localtime(),
    }


def render_prioritization_report_pdf(community) -> bytes:
    return render_pdf(
        "plot_applications/pdf/prioritization_report.html",
        prioritization_report_context(community),
    )


def prioritization_report_pdf_filename(community) -> str:
    code = community.community_folder_code or str(community.pk)
    return f"katalogos_proteraiopoiisis_{code}.pdf"
