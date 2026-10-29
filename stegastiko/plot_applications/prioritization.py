"""Κατάλογος προτεραιοποίησης αιτήσεων παραχώρησης οικοπέδου ανά Γνωστοποίηση / Κοινότητα (Ενότ. 6, 11).

Περιλαμβάνει όλες τις πλήρεις ανοικτές αιτήσεις της γνωστοποίησης, δικαιούχους και μη.
Οι δικαιούχοι προηγούνται και κατατάσσονται από το λογισμικό κατά την πρωτεύουσα
(τόπος διαμονής, Ενότ. 11.1) και τη δευτερεύουσα σειρά (σύνθεση οικογένειας, Ενότ. 11.2).
Ο λειτουργός μπορεί να αλλάξει τη σειρά (drag and drop) μόνο εντός της ίδιας ομάδας· η
χειροκίνητη σειρά αποθηκεύεται στο `PlotApplication.priority_rank`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.db.models import Q

from cases.models import SubmissionCycle
from core.models import ActionHistory, Community
from plot_applications.models import (
    ApplicationStage,
    EligibilityOverride,
    EligibilityResult,
    PlotApplication,
    ResidenceCategory,
)
from plot_applications.rules import parameter

PRIORITIZATION_STAGES = (
    ApplicationStage.EXAMINATION,
    ApplicationStage.PRIORITIZATION,
    ApplicationStage.OBJECTIONS,
    ApplicationStage.OBJECTIONS_COMMITTEE,
)
OBJECTION_STAGES = (
    ApplicationStage.OBJECTIONS,
    ApplicationStage.OBJECTIONS_COMMITTEE,
)
BENEFICIARIES = "beneficiaries"
OTHERS = "others"
GROUPS = (BENEFICIARIES, OTHERS)

_UNRANKED = 99

NEIGHBOURING_PRIORITY = 5
PRIMARY_ORDER = {
    ResidenceCategory.AUTOCHTHON: 1,
    ResidenceCategory.DISPLACED: 2,
    ResidenceCategory.INTERNAL_EMIGRANT: 3,
    ResidenceCategory.REPATRIATED: 4,
    ResidenceCategory.NEIGHBOURING: NEIGHBOURING_PRIORITY,
}
SECONDARY_LABELS = {
    1: "Πολύτεκνη οικογένεια",
    2: "Οικογένεια μη πολύτεκνη",
    3: "Μονογονεϊκή οικογένεια",
    4: "Ζεύγος χωρίς τέκνα",
}


def resolve_announcement_and_community(target) -> tuple[SubmissionCycle | None, Community | None]:
    """Δέχεται είτε `SubmissionCycle` (γνωστοποίηση) είτε `Community` και επιστρέφει (cycle, community)."""
    if target is None:
        return None, None
    if isinstance(target, SubmissionCycle):
        return target, target.community
    if isinstance(target, Community):
        cycle = (
            SubmissionCycle.for_community(target)
            .exclude(stage=SubmissionCycle.Stage.CLOSED)
            .first()
            or SubmissionCycle.objects.filter(plots__community=target)
            .exclude(stage=SubmissionCycle.Stage.CLOSED)
            .order_by("-published_at", "-announcement_date", "-pk")
            .first()
            or SubmissionCycle.for_community(target).first()
            or SubmissionCycle.objects.filter(plots__community=target)
            .order_by("-published_at", "-announcement_date", "-pk")
            .first()
            or SubmissionCycle.objects.order_by("-published_at", "-announcement_date", "-pk").first()
        )
        if cycle is not None and cycle.community is None:
            cycle._fallback_community = target
        return cycle, target
    return None, None


def primary_priority_rank(application: PlotApplication) -> int | None:
    """Ενότ. 11.1: πρωτεύουσα σειρά κατά τόπο διαμονής μεταξύ των αιτήσεων της Κοινότητας."""
    return PRIMARY_ORDER.get(application.residence_category)


def secondary_priority_rank(application: PlotApplication) -> int | None:
    """Ενότ. 11.2: δευτερεύουσα σειρά κατά σύνθεση οικογένειας σε περίπτωση ισοψηφίας."""
    if not application.residence_category:
        return None
    if application.recognized_children_count >= parameter("plotApp.largeFamilyChildren"):
        return 1
    if application.is_couple and application.recognized_children_count > 0:
        return 2
    if application.family_status == PlotApplication.FamilyStatus.SINGLE_PARENT:
        return 3
    return 4


@dataclass
class PrioritizationRow:
    application: PlotApplication
    group: str
    position: int = 0
    auto_position: int = 0
    criteria: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    tied_with: list[str] = field(default_factory=list)
    preliminary_note: str = ""
    changed_since_preliminary: bool = False
    list_status: str = ""
    list_status_badge: str = ""
    has_objection: bool = False
    is_pending: bool = False
    pending_items: list[str] = field(default_factory=list)
    locked: bool = False
    snapshot: dict = field(default_factory=dict)

    @property
    def is_moved(self) -> bool:
        return self.position != self.auto_position

    @property
    def primary_label(self) -> str:
        if "primary_label" in self.snapshot:
            return self.snapshot["primary_label"]
        return self.application.get_residence_category_display() or "—"

    @property
    def secondary_label(self) -> str:
        if "secondary_label" in self.snapshot:
            return self.snapshot["secondary_label"]
        return SECONDARY_LABELS.get(secondary_priority_rank(self.application), "—")

    @property
    def children_count(self) -> int:
        if "children_count" in self.snapshot:
            return self.snapshot["children_count"]
        return self.application.recognized_children_count

    @property
    def override_pass_reason(self) -> str | None:
        """Αιτιολογία χειροκίνητης αλλαγής σε ΔΙΚΑΙΟΥΧΟΣ (Ενότ. 6, 7), ή `None` αν δεν έγινε."""
        if "override_pass_reason" in self.snapshot:
            return self.snapshot["override_pass_reason"]
        if self.application.eligibility_override == EligibilityOverride.PASS:
            return self.application.eligibility_override_reason or "—"
        return None

    @property
    def objection_labels(self) -> list[str]:
        return [
            f"Ένσταση: {objection.get_status_display()}"
            for objection in self.application.objections.all()
        ]


def row_snapshot(row: PrioritizationRow) -> dict:
    """Τα στοιχεία της γραμμής που «παγώνουν» με την έκδοση του καταλόγου (`RankingEntry.snapshot`)."""
    return {
        "primary_label": row.primary_label,
        "secondary_label": row.secondary_label,
        "children_count": row.children_count,
        "override_pass_reason": row.override_pass_reason,
        "criteria": list(row.criteria),
        "reasons": list(row.reasons),
    }


@dataclass
class PrioritizationList:
    community: object
    beneficiaries: list[PrioritizationRow]
    others: list[PrioritizationRow]
    announcement: SubmissionCycle | None = None

    @property
    def has_manual_order(self) -> bool:
        return any(row.application.priority_rank for row in (*self.beneficiaries, *self.others))

    def group(self, name: str) -> list[PrioritizationRow]:
        return self.beneficiaries if name == BENEFICIARIES else self.others


def prioritization_queryset(target):
    cycle, community = resolve_announcement_and_community(target)
    qs = PlotApplication.objects.filter(application_stage__in=PRIORITIZATION_STAGES)
    if cycle is not None:
        qs = qs.filter(announcement=cycle)
    elif community is not None:
        qs = qs.filter(announcement__plots__community=community).distinct()
    else:
        return PlotApplication.objects.none()
    return (
        qs.select_related("announcement", "applicant", "spouse")
        .prefetch_related("objections", "pending_requirements", "announcement__plots__community")
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
        primary_priority_rank(application) or _UNRANKED,
        secondary_priority_rank(application) or _UNRANKED,
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
        f"Σύνθεση οικογένειας (Ενότ. 11.2): {SECONDARY_LABELS.get(secondary_priority_rank(application), '—')}",
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
        by_key.setdefault(
            (primary_priority_rank(app), secondary_priority_rank(app)), []
        ).append(row)
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
        pending_reqs = app.open_pending_requirements
        row = PrioritizationRow(
            application=app,
            group=group,
            position=position,
            auto_position=auto_positions[app.pk],
            has_objection=app.has_registered_objection,
            is_pending=bool(pending_reqs),
            pending_items=[req.description for req in pending_reqs],
        )
        if group == BENEFICIARIES:
            row.criteria = beneficiary_criteria(app)
        else:
            row.reasons = non_beneficiary_reasons(app)
        rows.append(row)
    if group == BENEFICIARIES:
        _mark_ties(rows)
    return rows


def mark_preliminary(rows: list[PrioritizationRow], entries: dict) -> None:
    """Σύγκριση με τον Προκαταρκτικό Κατάλογο, για τις αλλαγές της περιόδου ενστάσεων (Ενότ. 7)."""
    for row in rows:
        entry = entries.get(row.application.pk)
        if entry is None:
            row.preliminary_note = "Δεν περιλαμβάνεται στον Προκαταρκτικό Κατάλογο."
            row.changed_since_preliminary = True
        elif entry.status == "rejected":
            row.preliminary_note = "Προκαταρκτικός Κατάλογος: ΜΗ ΔΙΚΑΙΟΥΧΟΣ."
            row.changed_since_preliminary = row.group == BENEFICIARIES
        else:
            row.preliminary_note = f"Προκαταρκτικός Κατάλογος: θέση {entry.proposed_rank}."
            row.changed_since_preliminary = (
                row.group != BENEFICIARIES or entry.proposed_rank != row.position
            )


def build_prioritization_list(target) -> PrioritizationList:
    from plot_applications.beneficiary_lists import community_lists, preliminary_entries

    cycle, community = resolve_announcement_and_community(target)
    applications = list(prioritization_queryset(target))
    listing = PrioritizationList(
        community=community,
        announcement=cycle,
        beneficiaries=_build_group(
            [app for app in applications if application_group(app) == BENEFICIARIES], BENEFICIARIES
        ),
        others=_build_group(
            [app for app in applications if application_group(app) == OTHERS], OTHERS
        ),
    )
    state = community_lists(target)
    if state.preliminary is not None and state.final is None:
        rows = [*listing.beneficiaries, *listing.others]
        mark_preliminary(rows, preliminary_entries(state))
        # Ενότ. 7: ο Τελικός Κατάλογος αλλάζει μόνο στις αιτήσεις με ένσταση και όχι στο Στάδιο 3.
        locked_stage = bool(state.list_edit_locked_reason)
        for row in rows:
            row.locked = locked_stage or not row.has_objection
    return listing


def order_section_ref(application: PlotApplication, group: str) -> str:
    """Η αλλαγή σειράς καταγράφεται με το στάδιο στο οποίο έγινε (Επιτροπή Εξέτασης Αιτήσεων / Ενστάσεων)."""
    prefix = "objections" if application.application_stage in OBJECTION_STAGES else "prioritization"
    return f"{prefix}:{group}"


@transaction.atomic
def save_manual_order(
    target, group: str, requested_ids: list[int], *, enforce_objection_scope: bool = True
) -> list[PlotApplication]:
    """Αποθηκεύει τη σειρά της ομάδας όπως ορίστηκε με drag and drop (θέσεις 1..n)."""
    from plot_applications.beneficiary_lists import BeneficiaryListError, community_lists

    state = community_lists(target)
    if state.list_edit_locked_reason:
        raise BeneficiaryListError(state.list_edit_locked_reason)
    rows = build_prioritization_list(target).group(group)
    row_by_id = {row.application.pk: row for row in rows}
    ordered = [
        row_by_id[app_id].application
        for app_id in dict.fromkeys(requested_ids)
        if app_id in row_by_id
    ]
    ordered += [row.application for row in rows if row.application not in ordered]

    if enforce_objection_scope and state.preliminary is not None and state.final is None:
        current_ids = [row.application.pk for row in rows]
        ordered_ids = [app.pk for app in ordered]
        if ordered_ids != current_ids:
            objector_ids = {
                row.application.pk for row in rows if row.application.has_registered_objection
            }
            non_objector_before = [pk for pk in current_ids if pk not in objector_ids]
            non_objector_after = [pk for pk in ordered_ids if pk not in objector_ids]
            if not objector_ids or non_objector_before != non_objector_after:
                raise BeneficiaryListError(
                    "Στην Επιτροπή Εξέτασης Ενστάσεων επιτρέπεται αλλαγή σειράς μόνο για αιτήσεις με καταχωρισμένη ένσταση (Ενότ. 7)."
                )

    for position, app in enumerate(ordered, start=1):
        row = row_by_id[app.pk]
        if app.priority_rank != position:
            if row.position == position:
                app._audit_skip_fields = {"priority_rank"}
            else:
                prev_label = (
                    f"{row.position} (Σειρά λογισμικού)"
                    if app.priority_rank is None
                    else str(row.position)
                )
                app._priority_rank_audit_values = {
                    app.priority_rank: prev_label,
                    position: str(position),
                }
                app._section_ref = order_section_ref(app, group)
            app.priority_rank = position
            app.save()
    return ordered


@transaction.atomic
def reset_manual_order(target) -> int:
    """Επαναφορά στη σειρά του λογισμικού για όλες τις αιτήσεις του καταλόγου της γνωστοποίησης."""
    from plot_applications.beneficiary_lists import BeneficiaryListError, community_lists

    state = community_lists(target)
    if state.preliminary is not None:
        raise BeneficiaryListError(
            "Μετά την έκδοση του Προκαταρκτικού Καταλόγου η σειρά δεν επανέρχεται στη σειρά του "
            "λογισμικού· αλλάζουν μόνο οι αιτήσεις με ένσταση (Ενότ. 7)."
        )
    listing = build_prioritization_list(target)
    all_rows = [*listing.beneficiaries, *listing.others]
    ranked_rows = [row for row in all_rows if row.application.priority_rank is not None]
    any_moved = any(row.position != row.auto_position for row in ranked_rows)
    count = 0
    for row in ranked_rows:
        app = row.application
        if any_moved and row.position == row.auto_position:
            app._audit_skip_fields = {"priority_rank"}
        else:
            app._priority_rank_audit_values = {
                app.priority_rank: str(row.position),
                None: f"{row.auto_position} (Σειρά λογισμικού)",
            }
            app._section_ref = order_section_ref(app, row.group)
        app.priority_rank = None
        app.save()
        count += 1
    return count


def prioritization_history(target):
    """§Β.1.3 Ιστορικό αλλαγών του πίνακα προτεραιοποίησης και των αιτήσεων της γνωστοποίησης."""
    cycle, community = resolve_announcement_and_community(target)
    if cycle is not None and cycle.pk:
        app_ids = list(
            PlotApplication.objects.filter(announcement=cycle).values_list("pk", flat=True)
        )
    elif community is not None and community.pk:
        app_ids = list(
            PlotApplication.objects.filter(announcement__plots__community=community).values_list(
                "pk", flat=True
            )
        )
    else:
        return ActionHistory.objects.none()
    if not app_ids:
        return ActionHistory.objects.none()
    app_id_strs = [str(pk) for pk in app_ids]
    return ActionHistory.objects.filter(
        Q(entity_type="PlotApplication", entity_id__in=app_id_strs)
        | Q(application_id__in=app_ids)
    ).order_by("-timestamp", "-id")
