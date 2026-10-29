"""Κατάλογος προτεραιοποίησης / Προκαταρκτικός / Τελικός Κατάλογος Δικαιούχων ανά Γνωστοποίηση / Κοινότητα (PDF, A4 landscape).

Ίδια κεφαλίδα και μορφή πινάκων με την εξαγωγή των πινάκων αξιολόγησης (`cases.section6_report_pdf`).
Για τους δικαιούχους αποτυπώνονται τα κριτήρια προτεραιοποίησης (Ενότ. 11) και για τους μη
δικαιούχους ο λόγος (Ενότ. 10, 20 ή χειροκίνητη αλλαγή με αιτιολογία — Ενότ. 6).
Μετά την έκδοσή τους, ο Προκαταρκτικός και ο Τελικός Κατάλογος εξάγονται όπως εκδόθηκαν (Ενότ. 6, 7, 8)·
στην περίοδο ενστάσεων εξάγεται είτε ο Προκαταρκτικός είτε το σχέδιο του Τελικού Καταλόγου.
"""

from __future__ import annotations

from django.utils import timezone

from cases.pdf_rendering import render_pdf
from plot_applications.beneficiary_lists import (
    LIST_VIEW_PRELIMINARY,
    PHASE_COMMITTEE,
    community_lists,
    final_listing,
    snapshot_listing,
)
from plot_applications.prioritization import (
    build_prioritization_list,
    resolve_announcement_and_community,
)

REPORT_TITLE = "ΚΑΤΑΛΟΓΟΣ ΠΡΟΤΕΡΑΙΟΠΟΙΗΣΗΣ ΑΙΤΗΣΕΩΝ ΠΑΡΑΧΩΡΗΣΗΣ ΟΙΚΟΠΕΔΟΥ"
PRELIMINARY_TITLE = "ΠΡΟΚΑΤΑΡΚΤΙΚΟΣ ΚΑΤΑΛΟΓΟΣ ΔΙΚΑΙΟΥΧΩΝ"
FINAL_TITLE = "ΤΕΛΙΚΟΣ ΚΑΤΑΛΟΓΟΣ ΔΙΚΑΙΟΥΧΩΝ"
FINAL_DRAFT_TITLE = "ΣΧΕΔΙΟ ΤΕΛΙΚΟΥ ΚΑΤΑΛΟΓΟΥ ΔΙΚΑΙΟΥΧΩΝ (ΔΕΝ ΕΧΕΙ ΕΚΔΟΘΕΙ)"


def _report_kind(lists, list_view: str) -> str:
    if lists.phase == PHASE_COMMITTEE:
        return "committee"
    if list_view == LIST_VIEW_PRELIMINARY:
        return "preliminary"
    return "final" if lists.final is not None else "final_draft"


def prioritization_report_context(target, list_view: str = "") -> dict:
    cycle, community = resolve_announcement_and_community(target)
    lists = community_lists(target)
    kind = _report_kind(lists, list_view)
    ranking_list = None
    if kind == "preliminary":
        ranking_list = lists.preliminary
        title = PRELIMINARY_TITLE
        prioritization = snapshot_listing(ranking_list)
    elif kind == "final":
        ranking_list = lists.final
        title = FINAL_TITLE
        prioritization = final_listing(lists)
    elif kind == "final_draft":
        title = FINAL_DRAFT_TITLE
        prioritization = final_listing(lists)
    else:
        title = REPORT_TITLE
        prioritization = build_prioritization_list(target)
    return {
        "community": community,
        "announcement": cycle,
        "prioritization": prioritization,
        "report_title": title,
        "ranking_list": ranking_list,
        "is_final": kind == "final",
        "is_final_draft": kind == "final_draft",
        "lists": lists,
        "issued_at": timezone.localtime(),
    }


def render_prioritization_report_pdf(target, list_view: str = "") -> bytes:
    return render_pdf(
        "plot_applications/pdf/prioritization_report.html",
        prioritization_report_context(target, list_view),
    )


def prioritization_report_pdf_filename(target, list_view: str = "") -> str:
    cycle, community = resolve_announcement_and_community(target)
    code = (
        (community.community_folder_code or str(community.pk))
        if community is not None
        else (str(cycle.pk) if cycle is not None else "0")
    )
    kind = _report_kind(community_lists(target), list_view)
    return {
        "final": f"telikos_katalogos_dikaiouchon_{code}.pdf",
        "final_draft": f"schedio_telikou_katalogou_dikaiouchon_{code}.pdf",
        "preliminary": f"prokatarktikos_katalogos_dikaiouchon_{code}.pdf",
    }.get(kind, f"katalogos_proteraiopoiisis_{code}.pdf")
