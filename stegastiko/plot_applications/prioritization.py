"""Κατάλογος προτεραιοποίησης αιτήσεων παραχώρησης οικοπέδου ανά Κοινότητα (Ενότ. 6, 11).

Περιλαμβάνει όλες τις πλήρεις ανοικτές αιτήσεις της Κοινότητας (στάδια 2 και 3), δικαιούχους
και μη. Οι δικαιούχοι προηγούνται και κατατάσσονται από το λογισμικό κατά την πρωτεύουσα
(τόπος διαμονής, Ενότ. 11.1) και τη δευτερεύουσα σειρά (σύνθεση οικογένειας, Ενότ. 11.2).
Ο λειτουργός μπορεί να αλλάξει τη σειρά (drag and drop) μόνο εντός της ίδιας ομάδας· η
χειροκίνητη σειρά αποθηκεύεται στο `PlotApplication.priority_rank`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from plot_applications.models import (
    ApplicationStage,
    EligibilityOverride,
    EligibilityResult,
    PlotApplication,
)
from plot_applications.rules import SECONDARY_LABELS

PRIORITIZATION_STAGES = (ApplicationStage.EXAMINATION, ApplicationStage.PRIORITIZATION)
BENEFICIARIES = "beneficiaries"
OTHERS = "others"
GROUPS = (BENEFICIARIES, OTHERS)

_UNRANKED = 99


@dataclass
class PrioritizationRow:
    application: PlotApplication
    group: str
    position: int = 0
    auto_position: int = 0
    criteria: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    tied_with: list[str] = field(default_factory=list)

    @property
    def is_moved(self) -> bool:
        return self.position != self.auto_position

    @property
    def primary_label(self) -> str:
        return self.application.get_residence_category_display() or "—"

    @property
    def secondary_label(self) -> str:
        return SECONDARY_LABELS.get(self.application.priority_secondary, "—")


@dataclass
class PrioritizationList:
    community: object
    beneficiaries: list[PrioritizationRow]
    others: list[PrioritizationRow]

    @property
    def has_manual_order(self) -> bool:
        return any(row.application.priority_rank for row in (*self.beneficiaries, *self.others))

    def group(self, name: str) -> list[PrioritizationRow]:
        return self.beneficiaries if name == BENEFICIARIES else self.others


def prioritization_queryset(community):
    return (
        PlotApplication.objects.filter(
            community=community, application_stage__in=PRIORITIZATION_STAGES
        )
        .select_related("community", "applicant", "spouse")
        .order_by("id")
    )


def application_group(application: PlotApplication) -> str:
    return BENEFICIARIES if application.is_beneficiary else OTHERS


def _auto_key(application: PlotApplication) -> tuple:
    """Σειρά λογισμικού (Ενότ. 11)· η ημερομηνία υποβολής μόνο σταθεροποιεί την εμφάνιση των ισοψηφιών."""
    status_order = 0
    if application_group(application) == OTHERS:
        status_order = 0 if application.beneficiary_status == EligibilityResult.PENDING else 1
    return (
        status_order,
        application.priority_primary or _UNRANKED,
        application.priority_secondary or _UNRANKED,
        application.submitted_on or date.max,
        application.protocol_number,
        application.pk,
    )


def _merge_manual_order(auto_sorted: list[PlotApplication]) -> list[PlotApplication]:
    """Χειροκίνητη σειρά για όσες αιτήσεις μετακινήθηκαν· οι νέες αιτήσεις παρεμβάλλονται κατά τη σειρά λογισμικού."""
    auto_index = {app.pk: index for index, app in enumerate(auto_sorted)}
    ranked = sorted(
        (app for app in auto_sorted if app.priority_rank),
        key=lambda app: (app.priority_rank, auto_index[app.pk]),
    )
    unranked = [app for app in auto_sorted if not app.priority_rank]
    merged: list[PlotApplication] = []
    i = j = 0
    while i < len(ranked) and j < len(unranked):
        if auto_index[unranked[j].pk] < auto_index[ranked[i].pk]:
            merged.append(unranked[j])
            j += 1
        else:
            merged.append(ranked[i])
            i += 1
    return merged + ranked[i:] + unranked[j:]


def _criterion_text(item: dict) -> str:
    note = (item.get("note") or "").strip()
    text = f"{item.get('label', '')} (Ενότ. {item.get('section', '')})"
    return f"{text}: {note}" if note else text


def beneficiary_criteria(application: PlotApplication) -> list[str]:
    criteria = [
        f"Τόπος διαμονής (Ενότ. 11.1): {application.get_residence_category_display() or '—'}",
        f"Σύνθεση οικογένειας (Ενότ. 11.2): {SECONDARY_LABELS.get(application.priority_secondary, '—')}",
        f"Τέκνα κατά Ενότ. 10.Α: {application.recognized_children_count}",
    ]
    if application.eligibility_override == EligibilityOverride.PASS:
        criteria.append(
            "Χειροκίνητη αλλαγή σε ΔΙΚΑΙΟΥΧΟΣ: " + (application.eligibility_override_reason or "—")
        )
    return criteria


def non_beneficiary_reasons(application: PlotApplication) -> list[str]:
    details = application.eligibility_details or []
    if application.eligibility_override == EligibilityOverride.FAIL:
        reasons = [
            "Χειροκίνητη αλλαγή σε ΜΗ ΔΙΚΑΙΟΥΧΟΣ: " + (application.eligibility_override_reason or "—")
        ]
        reasons += [_criterion_text(item) for item in details if item.get("result") == EligibilityResult.FAIL]
        return reasons
    if application.eligibility_result == EligibilityResult.FAIL:
        return [_criterion_text(item) for item in details if item.get("result") == EligibilityResult.FAIL]
    pending = [_criterion_text(item) for item in details if item.get("result") == EligibilityResult.PENDING]
    return ["Εκκρεμεί έλεγχος: " + text for text in pending] or [
        "Εκκρεμεί η εξέταση επιλεξιμότητας."
    ]


def _mark_ties(rows: list[PrioritizationRow]) -> None:
    """Ισοψηφία στην πρωτεύουσα και δευτερεύουσα σειρά → κλήρωση από τον Έπαρχο (Ενότ. 8, 11.3)."""
    by_key: dict[tuple, list[PrioritizationRow]] = {}
    for row in rows:
        app = row.application
        by_key.setdefault((app.priority_primary, app.priority_secondary), []).append(row)
    for same in by_key.values():
        if len(same) < 2:
            continue
        for row in same:
            row.tied_with = [
                other.application.protocol_number for other in same if other is not row
            ]


def _build_group(applications: list[PlotApplication], group: str) -> list[PrioritizationRow]:
    auto_sorted = sorted(applications, key=_auto_key)
    auto_positions = {app.pk: index for index, app in enumerate(auto_sorted, start=1)}
    rows = []
    for position, app in enumerate(_merge_manual_order(auto_sorted), start=1):
        row = PrioritizationRow(
            application=app,
            group=group,
            position=position,
            auto_position=auto_positions[app.pk],
        )
        if group == BENEFICIARIES:
            row.criteria = beneficiary_criteria(app)
        else:
            row.reasons = non_beneficiary_reasons(app)
        rows.append(row)
    if group == BENEFICIARIES:
        _mark_ties(rows)
    return rows


def build_prioritization_list(community) -> PrioritizationList:
    applications = list(prioritization_queryset(community))
    return PrioritizationList(
        community=community,
        beneficiaries=_build_group(
            [app for app in applications if application_group(app) == BENEFICIARIES], BENEFICIARIES
        ),
        others=_build_group(
            [app for app in applications if application_group(app) == OTHERS], OTHERS
        ),
    )


@transaction.atomic
def save_manual_order(community, group: str, requested_ids: list[int]) -> list[PlotApplication]:
    """Αποθηκεύει τη σειρά της ομάδας όπως ορίστηκε με drag and drop (θέσεις 1..n)."""
    rows = build_prioritization_list(community).group(group)
    apps_by_id = {row.application.pk: row.application for row in rows}
    ordered = [apps_by_id[app_id] for app_id in dict.fromkeys(requested_ids) if app_id in apps_by_id]
    ordered += [row.application for row in rows if row.application not in ordered]
    for position, app in enumerate(ordered, start=1):
        if app.priority_rank != position:
            app.priority_rank = position
            app.save()
    return ordered


@transaction.atomic
def reset_manual_order(community) -> int:
    """Επαναφορά στη σειρά του λογισμικού για όλες τις αιτήσεις του καταλόγου της Κοινότητας."""
    count = 0
    for app in prioritization_queryset(community).filter(priority_rank__isnull=False):
        app.priority_rank = None
        app.save()
        count += 1
    return count
