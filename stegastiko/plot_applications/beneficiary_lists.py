"""Προκαταρκτικός και Τελικός Κατάλογος Δικαιούχων ανά Γνωστοποίηση / Κοινότητα (Ενότ. 6, 7, 8).

1. Η Επιτροπή Εξέτασης Αιτήσεων κατατάσσει τις πλήρεις αιτήσεις στην οθόνη «Προτεραιοποίηση
   αιτήσεων» και μπορεί να αλλάξει το αποτέλεσμα (δικαιούχος / μη δικαιούχος). Στο τέλος εκδίδεται
   ο **Προκαταρκτικός Κατάλογος Δικαιούχων** (`RankingList` τύπου `preliminary`).
2. Ακολουθεί η περίοδος ενστάσεων (Ενότ. 7, παράμετρος `plotApp.objectionDays`), κατά την οποία
   η Επιτροπή Εξέτασης Ενστάσεων μπορεί να κάνει αλλαγές στις αιτήσεις που υπέβαλαν ένσταση.
3. Μετά τη λήξη της εκδίδεται ο **Τελικός Κατάλογος Δικαιούχων** (`RankingList` τύπου `final`):
   οι πρώτοι δικαιούχοι, όσα και τα οικόπεδα, προχωρούν σε κλήρωση οικοπέδων, οι υπόλοιποι είναι
   «Επιλαχόντες» (Ενότ. 8) και οι μη δικαιούχοι απορρίπτονται από την Επιτροπή.

Και οι δύο κατάλογοι αποθηκεύονται ως στιγμιότυπο (`RankingEntry`) κατά την έκδοσή τους. Μόλις
αποσταλούν οι επιστολές / τα email του Προκαταρκτικού Καταλόγου (Ενότ. 6(β)), ο κατάλογος δεν
ανακαλείται και δεν αλλάζει· οι αλλαγές της περιόδου ενστάσεων γίνονται στον (υπό κατάρτιση)
Τελικό Κατάλογο και φαίνονται ανά πάσα στιγμή έναντι του Προκαταρκτικού (`list_changes`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from allocation.models import RankingEntry, RankingList
from cases.models import SubmissionCycle
from plot_applications.models import (
    ApplicationStage,
    Objection,
    PendingRequirement,
    PlotApplication,
)
from plot_applications.prioritization import (
    BENEFICIARIES,
    OTHERS,
    PrioritizationList,
    PrioritizationRow,
    beneficiary_criteria,
    build_prioritization_list,
    mark_preliminary,
    non_beneficiary_reasons,
    resolve_announcement_and_community,
    row_snapshot,
)
from plot_applications.rules import parameter
from plots.models import Plot

PHASE_COMMITTEE = "committee"
PHASE_OBJECTIONS = "objections"
PHASE_FINAL = "final"

PHASE_LABELS = {
    PHASE_COMMITTEE: "Εξέταση από την Επιτροπή Εξέτασης Αιτήσεων (Ενότ. 6)",
    PHASE_OBJECTIONS: "Προκαταρκτικός Κατάλογος Δικαιούχων — Περίοδος ενστάσεων (Ενότ. 7)",
    PHASE_FINAL: "Τελικός Κατάλογος Δικαιούχων (Ενότ. 7, 8)",
}

LIST_VIEW_PRELIMINARY = "preliminary"
LIST_VIEW_FINAL = "final"
LIST_VIEW_CHANGES = "changes"
LIST_VIEWS = (LIST_VIEW_PRELIMINARY, LIST_VIEW_FINAL, LIST_VIEW_CHANGES)

BLOCKING_STAGES = (ApplicationStage.COLLECTION, ApplicationStage.EXAMINATION)


class BeneficiaryListError(Exception):
    """Η ενέργεια στον κατάλογο δεν επιτρέπεται· το μήνυμα εμφανίζεται στον χρήστη."""


@dataclass
class CommunityLists:
    community: object
    cycle: SubmissionCycle | None
    preliminary: RankingList | None
    final: RankingList | None

    @property
    def phase(self) -> str:
        if self.final is not None:
            return PHASE_FINAL
        if self.preliminary is not None:
            return PHASE_OBJECTIONS
        return PHASE_COMMITTEE

    @property
    def phase_label(self) -> str:
        return PHASE_LABELS[self.phase]

    @property
    def objection_deadline(self) -> date | None:
        if not self.preliminary:
            return None
        deadlines = [self.preliminary.objection_deadline] if self.preliminary.objection_deadline else []
        entry_deadlines = [
            e.objection_deadline
            for e in self.preliminary.entries.all()
            if e.objection_deadline is not None
        ]
        all_dates = deadlines + entry_deadlines
        return max(all_dates) if all_dates else None

    def objections_open(self, today: date | None = None) -> bool:
        deadline = self.objection_deadline
        return deadline is not None and (today or timezone.localdate()) <= deadline

    @property
    def objections_closed(self) -> bool:
        """Η περίοδος ενστάσεων έκλεισε (λήξη ή μετάβαση στο Στάδιο 4 με αποδοχή προειδοποίησης)."""
        return bool(self.cycle is not None and self.cycle.objections_closed_on)

    @property
    def list_edit_locked_reason(self) -> str:
        """Γιατί ο κατάλογος δεν αλλάζει τώρα (κενό αν αλλάζει)· στο Στάδιο 4 εξετάζονται μόνο οι ενστάσεις."""
        if (
            self.preliminary is not None
            and self.final is None
            and self.cycle is not None
            and self.cycle.stage == SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        ):
            return (
                "Στο Στάδιο 4 (Ενστάσεις) εξετάζονται οι ενστάσεις· ο Τελικός "
                "Κατάλογος αλλάζει στο Στάδιο 5 «Τελικός Κατάλογος Δικαιούχων» της Γνωστοποίησης."
            )
        return ""

    @property
    def preliminary_locked_reason(self) -> str:
        """Γιατί ο Προκαταρκτικός Κατάλογος δεν ανακαλείται πλέον (κενό αν ανακαλείται)."""
        if self.preliminary is None:
            return ""
        if self.final is not None:
            return "Ανακαλέστε πρώτα τον Τελικό Κατάλογο Δικαιούχων."
        if self.preliminary.notifications_sent_at is not None:
            return (
                "Ο Προκαταρκτικός Κατάλογος έχει γνωστοποιηθεί στους αιτητές (Ενότ. 6(β)) και δεν "
                "ανακαλείται· οι αλλαγές γίνονται στον Τελικό Κατάλογο πριν από την έκδοσή του."
            )
        if Objection.objects.filter(preliminary_entry__ranking_list=self.preliminary).exists():
            return (
                "Έχουν υποβληθεί ενστάσεις επί του Προκαταρκτικού Καταλόγου (Ενότ. 7)· ο κατάλογος "
                "δεν ανακαλείται."
            )
        return ""

    @property
    def can_revoke_preliminary(self) -> bool:
        return self.preliminary is not None and not self.preliminary_locked_reason

    @property
    def plots_count(self) -> int:
        if self.final is not None and self.final.plots_count is not None:
            return self.final.plots_count
        return available_plots_count(self.community, self.cycle)


def submission_cycle_for(community) -> SubmissionCycle | None:
    """Η πιο πρόσφατη δημοσιευμένη γνωστοποίηση (Ενότ. 4) που καλύπτει την Κοινότητα."""
    cycle, _ = resolve_announcement_and_community(community)
    if cycle is not None and cycle.is_published:
        return cycle
    return (
        SubmissionCycle.for_community(community).exclude(stage=SubmissionCycle.Stage.CLOSED).first()
        or SubmissionCycle.for_community(community).first()
    )


def available_plots_count(community, cycle: SubmissionCycle | None) -> int:
    """Τα οικόπεδα που προσφέρει η γνωστοποίηση· αλλιώς τα διαθέσιμα οικόπεδα της Κοινότητας."""
    if cycle is not None and cycle.pk:
        offered = cycle.plots.count()
        if offered:
            return offered
    if community is not None and getattr(community, "pk", None):
        return Plot.objects.available().filter(community=community).count()
    return 0


def community_lists(target) -> CommunityLists:
    cycle, community = resolve_announcement_and_community(target)
    if cycle is not None and not cycle.is_published and isinstance(target, SubmissionCycle) is False:
        # When called with a Community, require a published cycle as before.
        cycle = SubmissionCycle.for_community(community).first() or (
            cycle if cycle.is_published else None
        )
    preliminary = final = None
    if cycle is not None and cycle.pk:
        lists = RankingList.objects.filter(submission_cycle=cycle).prefetch_related("entries")
        preliminary = lists.filter(list_type=RankingList.ListType.PRELIMINARY).first()
        final = lists.filter(list_type=RankingList.ListType.FINAL).first()
    return CommunityLists(community=community, cycle=cycle, preliminary=preliminary, final=final)


announcement_lists = community_lists


def blocking_applications(target):
    """Ανοικτές αιτήσεις χωρίς κρίση επιλεξιμότητας ή ελλιπείς, που εμποδίζουν την έκδοση καταλόγου."""
    cycle, community = resolve_announcement_and_community(target)
    qs = PlotApplication.objects.filter(application_stage__in=BLOCKING_STAGES)
    if cycle is not None and cycle.pk:
        qs = qs.filter(announcement=cycle)
    elif community is not None and getattr(community, "pk", None):
        qs = qs.filter(announcement__plots__community=community).distinct()
    else:
        return PlotApplication.objects.none()
    return qs.order_by("protocol_number")


def _check_no_blockers(target) -> None:
    blockers = list(blocking_applications(target).values_list("protocol_number", flat=True))
    if blockers:
        raise BeneficiaryListError(
            "Δεν μπορεί να εκδοθεί κατάλογος όσο υπάρχουν αιτήσεις με «Εκκρεμεί έλεγχος» ή ελλιπείς "
            "αιτήσεις (κρίνονται ή απορρίπτονται πρώτα): " + ", ".join(blockers) + "."
        )


def _check_no_open_objections_or_pending_items(
    cycle: SubmissionCycle, action: str = "να εκδοθεί ο Τελικός Κατάλογος"
) -> None:
    pending_reqs = list(
        PendingRequirement.objects.filter(
            application__announcement=cycle, is_fulfilled=False
        )
        .select_related("application")
        .values_list("application__protocol_number", flat=True)
        .distinct()
    )
    if pending_reqs:
        raise BeneficiaryListError(
            f"Δεν μπορεί {action} όσο εκκρεμεί προσκόμιση επιπλέον στοιχείων "
            "στις αιτήσεις: " + ", ".join(pending_reqs) + "."
        )
    undecided = list(
        Objection.objects.filter(
            application__announcement=cycle, status=Objection.Status.PENDING
        )
        .select_related("application")
        .values_list("application__protocol_number", flat=True)
        .distinct()
    )
    if undecided:
        raise BeneficiaryListError(
            f"Δεν μπορεί {action} όσο υπάρχουν ενστάσεις χωρίς απόφαση: "
            + ", ".join(undecided)
            + "."
        )


def _create_list(state: CommunityLists, list_type: str, user, **extra) -> RankingList:
    return RankingList.objects.create(
        submission_cycle=state.cycle,
        list_type=list_type,
        finalized_at=timezone.now(),
        finalized_by_id=getattr(user, "pk", None),
        **extra,
    )


@transaction.atomic
def issue_preliminary_list(target, user, today: date | None = None) -> RankingList:
    state = community_lists(target)
    if state.cycle is None or not state.cycle.is_published:
        raise BeneficiaryListError(
            "Δεν υπάρχει δημοσιευμένη γνωστοποίηση υποβολής αιτήσεων (Ενότ. 4) για την Κοινότητα."
        )
    if state.preliminary is not None:
        raise BeneficiaryListError("Ο Προκαταρκτικός Κατάλογος Δικαιούχων έχει ήδη εκδοθεί.")
    _check_no_blockers(state.cycle)
    listing = build_prioritization_list(state.cycle)
    if not (listing.beneficiaries or listing.others):
        raise BeneficiaryListError("Δεν υπάρχουν αιτήσεις στον κατάλογο της Κοινότητας.")
    issued_on = today or timezone.localdate()
    notified_dt = timezone.make_aware(datetime.combine(issued_on, time(9, 0)))
    deadline = issued_on + timedelta(days=parameter("plotApp.objectionDays"))
    ranking_list = _create_list(
        state,
        RankingList.ListType.PRELIMINARY,
        user,
        objection_deadline=deadline,
    )
    for row in listing.beneficiaries:
        RankingEntry.objects.create(
            ranking_list=ranking_list,
            application=row.application,
            proposed_rank=row.position,
            status=RankingEntry.Status.ELIGIBLE,
            snapshot=row_snapshot(row),
            notified_at=notified_dt,
            objection_deadline=deadline,
        )
    for row in listing.others:
        RankingEntry.objects.create(
            ranking_list=ranking_list,
            application=row.application,
            status=RankingEntry.Status.REJECTED,
            snapshot=row_snapshot(row),
            notified_at=notified_dt,
            objection_deadline=deadline,
        )
    cycle = state.cycle
    changed = []
    if cycle.stage in (SubmissionCycle.Stage.DETAILS, SubmissionCycle.Stage.SUBMISSION):
        cycle.stage = SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
        changed.append("stage")
    if cycle.applications_committee_date is None:
        cycle.applications_committee_date = issued_on
        changed.append("applications_committee_date")
    if changed:
        cycle.save(update_fields=changed)
    return ranking_list


@transaction.atomic
def issue_final_list(target, user, today: date | None = None) -> RankingList:
    state = community_lists(target)
    if state.preliminary is None:
        raise BeneficiaryListError("Πρέπει πρώτα να εκδοθεί ο Προκαταρκτικός Κατάλογος Δικαιούχων.")
    if state.final is not None:
        raise BeneficiaryListError("Ο Τελικός Κατάλογος Δικαιούχων έχει ήδη εκδοθεί.")
    if state.objections_open(today) and not state.objections_closed:
        raise BeneficiaryListError(
            "Η περίοδος ενστάσεων (Ενότ. 7) λήγει στις "
            f"{state.objection_deadline:%d/%m/%Y}· ο Τελικός Κατάλογος εκδίδεται μετά τη λήξη της."
        )
    _check_no_blockers(state.cycle)
    _check_no_open_objections_or_pending_items(state.cycle)
    listing = build_prioritization_list(state.cycle)
    plots = state.plots_count
    issued_on = today or timezone.localdate()
    notified_dt = timezone.make_aware(datetime.combine(issued_on, time(9, 0)))
    ranking_list = _create_list(state, RankingList.ListType.FINAL, user, plots_count=plots)
    for row in listing.beneficiaries:
        RankingEntry.objects.create(
            ranking_list=ranking_list,
            application=row.application,
            proposed_rank=row.position,
            finalized_rank=row.position,
            status=(
                RankingEntry.Status.ELIGIBLE
                if row.position <= plots
                else RankingEntry.Status.ALTERNATE
            ),
            snapshot=row_snapshot(row),
            notified_at=notified_dt,
        )
    for row in listing.others:
        RankingEntry.objects.create(
            ranking_list=ranking_list,
            application=row.application,
            status=RankingEntry.Status.REJECTED,
            snapshot=row_snapshot(row),
            notified_at=notified_dt,
        )
    cycle = state.cycle
    changed = []
    if cycle.objections_committee_date is None:
        cycle.objections_committee_date = issued_on
        changed.append("objections_committee_date")
    if cycle.stage in (SubmissionCycle.Stage.OBJECTIONS_COMMITTEE, SubmissionCycle.Stage.FINAL_LIST):
        cycle.stage = SubmissionCycle.Stage.LOTTERY
        changed.append("stage")
    if changed:
        cycle.save(update_fields=changed)
    for entry in ranking_list.entries.select_related("application").all():
        if entry.application_id:
            from plot_applications.rules import apply_evaluation

            apply_evaluation(entry.application)
    return ranking_list


def _delete_list(ranking_list: RankingList) -> None:
    # RankingEntry.delete() re-evaluates the application, so its stage goes back one step.
    for entry in list(ranking_list.entries.all()):
        entry.delete()
    ranking_list.delete()


@transaction.atomic
def revoke_final_list(target) -> None:
    state = community_lists(target)
    if state.final is None:
        raise BeneficiaryListError("Δεν έχει εκδοθεί Τελικός Κατάλογος Δικαιούχων.")
    if any(
        alloc.status == "active"
        for entry in state.final.entries.select_related("application")
        for alloc in entry.application.allocations.all()
    ):
        raise BeneficiaryListError(
            "Ο Τελικός Κατάλογος δεν ανακαλείται, γιατί έχουν ήδη κατανεμηθεί οικόπεδα (Ενότ. 9)."
        )
    cycle = state.cycle
    if cycle is not None and cycle.stage in (
        SubmissionCycle.Stage.LOTTERY,
        SubmissionCycle.Stage.AGREEMENTS,
    ):
        cycle.stage = (
            SubmissionCycle.Stage.FINAL_LIST
            if cycle.objections_closed_on
            else SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        )
        cycle.save(update_fields=["stage"])
    _delete_list(state.final)


@transaction.atomic
def revoke_preliminary_list(target) -> None:
    state = community_lists(target)
    if state.preliminary is None:
        raise BeneficiaryListError("Δεν έχει εκδοθεί Προκαταρκτικός Κατάλογος Δικαιούχων.")
    if state.preliminary_locked_reason:
        raise BeneficiaryListError(state.preliminary_locked_reason)
    cycle = state.cycle
    if cycle is not None:
        if cycle.stage in (SubmissionCycle.Stage.OBJECTIONS_COMMITTEE, SubmissionCycle.Stage.FINAL_LIST):
            cycle.stage = SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
        cycle.objections_closed_on = None
        cycle.objections_closed_early = False
        cycle.save(update_fields=["stage", "objections_closed_on", "objections_closed_early"])
    _delete_list(state.preliminary)


def application_list_decisions(application: PlotApplication) -> list[dict]:
    """Η θέση/απόφαση της αίτησης σε κάθε κατάλογο, για την προβολή της αίτησης."""
    if not application.pk:
        return []
    decisions = []
    entries = application.ranking_entries.select_related("ranking_list").order_by("ranking_list_id")
    for entry in entries:
        ranking_list = entry.ranking_list
        is_final = ranking_list.list_type == RankingList.ListType.FINAL
        rank = entry.finalized_rank or entry.proposed_rank
        if entry.status == RankingEntry.Status.REJECTED:
            text = "ΜΗ ΔΙΚΑΙΟΥΧΟΣ — απόρριψη από την Επιτροπή" + (
                "" if is_final else " (δικαίωμα ένστασης, Ενότ. 7)"
            )
            badge = "fail"
        elif not is_final:
            text, badge = f"ΔΙΚΑΙΟΥΧΟΣ — θέση {rank}", "pass"
        elif entry.status == RankingEntry.Status.ELIGIBLE:
            text, badge = f"ΔΙΚΑΙΟΥΧΟΣ — θέση {rank} — Πήρε οικόπεδο (Ενότ. 8)", "pass"
        else:
            text = f"ΔΙΚΑΙΟΥΧΟΣ — θέση {rank} — Επιλαχών: τα οικόπεδα δεν επαρκούν (Ενότ. 8)"
            badge = "pending"
        issued = timezone.localtime(ranking_list.finalized_at) if ranking_list.finalized_at else None
        deadline = None if is_final else (entry.objection_deadline or ranking_list.objection_deadline)
        decisions.append(
            {
                "title": f"{ranking_list.get_list_type_display()} Κατάλογος Δικαιούχων",
                "issued_at": issued,
                "text": text,
                "badge": badge,
                "objection_deadline": deadline,
                "entry": entry,
            }
        )
    return decisions


def preliminary_entries(state: CommunityLists) -> dict[int, RankingEntry]:
    if state.preliminary is None:
        return {}
    return {entry.application_id: entry for entry in state.preliminary.entries.all()}


LIST_STATUS_LABELS = {
    RankingEntry.Status.ELIGIBLE: "Πήρε οικόπεδο",
    RankingEntry.Status.ALTERNATE: "Επιλαχών",
    RankingEntry.Status.REJECTED: "Απόρριψη από Επιτροπή",
}
PRELIMINARY_STATUS_LABELS = {
    RankingEntry.Status.ELIGIBLE: "ΔΙΚΑΙΟΥΧΟΣ",
    RankingEntry.Status.REJECTED: "ΜΗ ΔΙΚΑΙΟΥΧΟΣ",
}


def _entry_status_label(entry: RankingEntry, is_final: bool) -> str:
    labels = LIST_STATUS_LABELS if is_final else PRELIMINARY_STATUS_LABELS
    return labels.get(entry.status, entry.get_status_display())


def snapshot_listing(ranking_list: RankingList) -> PrioritizationList:
    """Ο κατάλογος όπως εκδόθηκε: δικαιούχοι κατά τη θέση τους και έπειτα οι μη δικαιούχοι.

    Τα κριτήρια / οι λόγοι εμφανίζονται όπως ίσχυαν κατά την έκδοση (`RankingEntry.snapshot`), ώστε
    οι μεταγενέστερες αλλαγές (π.χ. μετά από ένσταση) να μην αλλοιώνουν τον εκδοθέντα κατάλογο.
    """
    entries = list(
        ranking_list.entries.select_related(
            "application", "application__announcement", "application__applicant", "application__spouse"
        ).prefetch_related("application__announcement__plots__community", "application__objections")
    )
    is_final = ranking_list.list_type == RankingList.ListType.FINAL
    ranked = sorted(
        (entry for entry in entries if entry.status != RankingEntry.Status.REJECTED),
        key=lambda entry: (entry.finalized_rank or entry.proposed_rank or 0, entry.pk),
    )
    rejected = sorted(
        (entry for entry in entries if entry.status == RankingEntry.Status.REJECTED),
        key=lambda entry: (entry.application.protocol_number, entry.pk),
    )
    beneficiaries = []
    for entry in ranked:
        rank = entry.finalized_rank or entry.proposed_rank or 0
        snapshot = entry.snapshot or {}
        beneficiaries.append(
            PrioritizationRow(
                application=entry.application,
                group=BENEFICIARIES,
                position=rank,
                auto_position=rank,
                criteria=snapshot.get("criteria") or beneficiary_criteria(entry.application),
                list_status=_entry_status_label(entry, is_final),
                list_status_badge=(
                    "pass" if entry.status == RankingEntry.Status.ELIGIBLE else "pending"
                ),
                has_objection=bool(entry.application.objections.all()),
                snapshot=snapshot,
            )
        )
    others = [
        PrioritizationRow(
            application=entry.application,
            group=OTHERS,
            position=index,
            auto_position=index,
            reasons=(entry.snapshot or {}).get("reasons") or non_beneficiary_reasons(entry.application),
            list_status=_entry_status_label(entry, is_final),
            list_status_badge="fail",
            has_objection=bool(entry.application.objections.all()),
            snapshot=entry.snapshot or {},
        )
        for index, entry in enumerate(rejected, start=1)
    ]
    return PrioritizationList(
        community=ranking_list.community,
        announcement=ranking_list.submission_cycle,
        beneficiaries=beneficiaries,
        others=others,
    )


def final_listing(state: CommunityLists) -> PrioritizationList | None:
    """Ο Τελικός Κατάλογος: όπως εκδόθηκε ή, πριν από την έκδοση, όπως διαμορφώνεται στην περίοδο ενστάσεων."""
    if state.final is not None:
        listing = snapshot_listing(state.final)
        mark_preliminary([*listing.beneficiaries, *listing.others], preliminary_entries(state))
        return listing
    if state.cycle is None:
        return None
    return build_prioritization_list(state.cycle)


ANNOUNCEMENT_STAGE_LABELS: dict[str, str] = {
    SubmissionCycle.Stage.DETAILS: "1. Στοιχεία γνωστοποίησης",
    SubmissionCycle.Stage.SUBMISSION: "2. Υποβολή αιτήσεων",
    SubmissionCycle.Stage.APPLICATIONS_COMMITTEE: "3. Επιτροπή Εξέτασης Αιτήσεων",
    SubmissionCycle.Stage.OBJECTIONS_COMMITTEE: "4. Ενστάσεις",
    SubmissionCycle.Stage.FINAL_LIST: "5. Τελικός Κατάλογος Δικαιούχων",
    SubmissionCycle.Stage.LOTTERY: "6. Στάδιο κλήρωσης",
    SubmissionCycle.Stage.AGREEMENTS: "7. Υπογραφή συμφωνίας και πληρωμή",
}


def communication_stage_info(
    communication,
    *,
    section_ref: str | None = None,
    preliminary: RankingList | None = None,
    final: RankingList | None = None,
) -> tuple[str, str, str]:
    """Επιστρέφει `(stage_code, stage_label, email_kind_label)` για ένα `Communication` αίτησης."""
    from core.models import ActionHistory

    if section_ref is None:
        section_ref = ""
        if getattr(communication, "pk", None):
            section_ref = (
                ActionHistory.objects.filter(
                    entity_type="Communication",
                    entity_id=str(communication.pk),
                )
                .exclude(section_ref="")
                .values_list("section_ref", flat=True)
                .first()
                or ""
            )

    subject = (getattr(communication, "subject", "") or "").strip()
    body = (getattr(communication, "body", "") or "").strip()
    created_at = getattr(communication, "created_at", None)

    is_final_window = (
        final is not None
        and final.finalized_at is not None
        and final.notifications_sent_at is not None
        and created_at is not None
        and final.finalized_at <= created_at <= final.notifications_sent_at
        and section_ref in ("stage:objections_committee", "stage:final_list", "announcement_workflow", "")
    )
    is_prelim_window = (
        preliminary is not None
        and preliminary.finalized_at is not None
        and preliminary.notifications_sent_at is not None
        and created_at is not None
        and preliminary.finalized_at <= created_at <= preliminary.notifications_sent_at
    )

    if (
        section_ref in ("stage:final_list", "announcement_stage:final_list")
        or is_final_window
        or subject.startswith("Τελικός Κατάλογος")
    ):
        stage_code = SubmissionCycle.Stage.FINAL_LIST
        if "Επιλαχών" in subject or "ΕΠΙΛΑΧΩΝ" in body:
            kind = "Τελικός Κατάλογος — Επιλαχών"
        else:
            kind = "Τελικός Κατάλογος — Δικαιούχος Οικοπέδου"
    elif (
        section_ref in ("stage:prioritization", "stage:applications_committee")
        or is_prelim_window
        or subject.startswith("Προκαταρκτικός Κατάλογος")
    ):
        stage_code = SubmissionCycle.Stage.APPLICATIONS_COMMITTEE
        if "Απόρριψη" in subject or "ΜΗ ΔΙΚΑΙΟΥΧΟΣ" in body:
            kind = "Προκαταρκτικός Κατάλογος — Μη Δικαιούχος"
        else:
            kind = "Προκαταρκτικός Κατάλογος — Δικαιούχος"
    elif section_ref == "stage:lottery" or subject.startswith("Πρόσκληση σε Κλήρωση"):
        stage_code = SubmissionCycle.Stage.LOTTERY
        kind = "Πρόσκληση σε Κλήρωση Οικοπέδων"
    elif (
        section_ref in ("stage:agreement", "stage:agreements")
        or subject.startswith("Πρόσκληση για Υπογραφή Συμφωνίας")
        or subject.startswith("Ανάθεση Οικοπέδου σε Επιλαχόντα")
    ):
        stage_code = SubmissionCycle.Stage.AGREEMENTS
        if "Επιλαχόντα" in subject or "επιλαχών" in body.lower():
            kind = "Ανάθεση Οικοπέδου σε Επιλαχόντα"
        else:
            kind = "Πρόσκληση Υπογραφής Συμφωνίας & Πληρωμής"
    elif (
        section_ref in ("stage:objections_committee", "stage:objections")
        or subject.startswith("Απόφαση επί Ένστασης")
    ):
        stage_code = SubmissionCycle.Stage.OBJECTIONS_COMMITTEE
        kind = "Απόφαση επί Ένστασης"
    elif section_ref.startswith("announcement_stage:"):
        code = section_ref.split(":", 1)[1]
        stage_code = (
            code if code in ANNOUNCEMENT_STAGE_LABELS else SubmissionCycle.Stage.SUBMISSION
        )
        kind = (
            "Επικοινωνία Αίτησης / Δικαιολογητικά"
            if stage_code == SubmissionCycle.Stage.SUBMISSION
            else "Επικοινωνία Αίτησης"
        )
    else:
        stage_code = SubmissionCycle.Stage.SUBMISSION
        kind = "Επικοινωνία Αίτησης / Δικαιολογητικά"

    return stage_code, ANNOUNCEMENT_STAGE_LABELS.get(stage_code, stage_code), kind


def populate_communications_metadata(
    communications,
    *,
    preliminary: RankingList | None = None,
    final: RankingList | None = None,
) -> list:
    """Φορτώνει μαζικά τον αποστολέα (`sender_label`) και το στάδιο (`stage_label`) για λίστα `Communication`."""
    comm_list = list(communications)
    if not comm_list:
        return comm_list
    from django.contrib.auth import get_user_model

    from core.models import ActionHistory

    comm_id_strs = [str(c.pk) for c in comm_list if c.pk]
    section_ref_by_id: dict[str, str] = {}
    fallback_user_by_id: dict[str, int] = {}
    if comm_id_strs:
        for entity_id, sec_ref, uid in ActionHistory.objects.filter(
            entity_type="Communication", entity_id__in=comm_id_strs
        ).values_list("entity_id", "section_ref", "user_id"):
            if sec_ref and entity_id not in section_ref_by_id:
                section_ref_by_id[entity_id] = sec_ref
            if uid and entity_id not in fallback_user_by_id:
                fallback_user_by_id[entity_id] = uid

    user_ids = {
        c.created_by_id or fallback_user_by_id.get(str(c.pk))
        for c in comm_list
    }
    user_ids.discard(None)
    user_labels: dict[int, str] = {}
    if user_ids:
        User = get_user_model()
        for u in User.objects.filter(pk__in=user_ids):
            full_name = u.get_full_name().strip()
            user_labels[u.pk] = f"{full_name} ({u.username})" if full_name else u.username

    for comm in comm_list:
        uid = comm.created_by_id or fallback_user_by_id.get(str(comm.pk))
        if uid:
            comm._sender_label = user_labels.get(uid, f"Χρήστης #{uid}")
        else:
            comm._sender_label = "Σύστημα"
        stage_code, stage_label, kind = communication_stage_info(
            comm,
            section_ref=section_ref_by_id.get(str(comm.pk), ""),
            preliminary=preliminary,
            final=final,
        )
        comm._stage_code = stage_code
        comm._stage_label = stage_label
        comm._email_kind_label = kind
    return comm_list


@dataclass
class AnnouncementEmail:
    """Ένα email που στάλθηκε σε αιτητή στο πλαίσιο συγκεκριμένου σταδίου της γνωστοποίησης."""

    communication: object
    application: PlotApplication
    applicant_name: str
    recipient: str
    sender_label: str
    subject: str
    body: str
    status: str
    status_label: str
    status_badge: str
    sent_at: datetime | None
    stage_code: str
    stage_label: str
    email_kind_label: str


def announcement_communications(
    cycle: SubmissionCycle, state: CommunityLists | None = None
) -> tuple[list[AnnouncementEmail], dict[str, list[AnnouncementEmail]]]:
    """Όλα τα email που έχουν σταλεί για τις αιτήσεις της γνωστοποίησης, συνολικά και ανά στάδιο."""
    from django.contrib.contenttypes.models import ContentType

    from cases.models import CommunicationStatus
    from core.models import Communication

    by_stage: dict[str, list[AnnouncementEmail]] = {
        code: [] for code in ANNOUNCEMENT_STAGE_LABELS
    }
    if cycle is None or not cycle.pk:
        return [], by_stage

    if state is None:
        state = community_lists(cycle)

    apps_by_id = {
        app.pk: app
        for app in cycle.applications.select_related("applicant", "spouse").all()
    }
    if not apps_by_id:
        return [], by_stage

    raw_comms = list(
        Communication.objects.filter(
            content_type=ContentType.objects.get_for_model(PlotApplication),
            object_id__in=list(apps_by_id.keys()),
        ).order_by("created_at", "id")
    )
    populate_communications_metadata(
        raw_comms, preliminary=state.preliminary, final=state.final
    )

    all_emails: list[AnnouncementEmail] = []
    for comm in raw_comms:
        app = apps_by_id.get(comm.object_id)
        if app is None:
            continue
        applicant = app.applicant if app.applicant_id else None
        applicant_name = (
            f"{applicant.first_name} {applicant.last_name}".strip() if applicant else "—"
        )
        status_label = CommunicationStatus.label(comm.status)
        if comm.status == CommunicationStatus.SENT:
            status_badge = "pass"
        elif comm.status == CommunicationStatus.FAILED:
            status_badge = "fail"
        else:
            status_badge = "pending"
        item = AnnouncementEmail(
            communication=comm,
            application=app,
            applicant_name=applicant_name,
            recipient=comm.recipient,
            sender_label=comm.sender_label,
            subject=comm.subject,
            body=comm.body,
            status=comm.status,
            status_label=status_label,
            status_badge=status_badge,
            sent_at=comm.sent_at or comm.created_at,
            stage_code=comm._stage_code,
            stage_label=comm._stage_label,
            email_kind_label=comm._email_kind_label,
        )
        all_emails.append(item)
        by_stage.setdefault(item.stage_code, []).append(item)

    return all_emails, by_stage


@dataclass
class ListNotification:
    """Η γνωστοποίηση μιας εγγραφής του καταλόγου στον αιτητή (Ενότ. 6(β))."""

    entry: RankingEntry
    communication: object | None
    status_label: str
    status_badge: str
    sender_label: str = "—"


def list_notifications(ranking_list: RankingList | None) -> list[ListNotification]:
    """Τα email που στάλθηκαν κατά τη γνωστοποίηση του καταλόγου, ένα ανά εγγραφή (ή «μόνο ταχυδρομικώς»)."""
    if ranking_list is None:
        return []
    from django.contrib.contenttypes.models import ContentType

    from cases.models import CommunicationStatus
    from core.models import Communication

    entries = sorted(
        ranking_list.entries.select_related("application", "application__applicant"),
        key=lambda entry: (
            entry.status == RankingEntry.Status.REJECTED,
            entry.finalized_rank or entry.proposed_rank or 0,
            entry.application.protocol_number,
        ),
    )
    by_application = {}
    if ranking_list.notifications_sent_at is not None:
        communications = list(
            Communication.objects.filter(
                content_type=ContentType.objects.get_for_model(PlotApplication),
                object_id__in=[entry.application_id for entry in entries],
                created_at__gte=ranking_list.finalized_at,
                created_at__lte=ranking_list.notifications_sent_at,
            ).order_by("created_at", "id")
        )
        populate_communications_metadata(
            communications,
            preliminary=(
                ranking_list
                if ranking_list.list_type == RankingList.ListType.PRELIMINARY
                else None
            ),
            final=(
                ranking_list
                if ranking_list.list_type == RankingList.ListType.FINAL
                else None
            ),
        )
        for communication in communications:
            by_application[communication.object_id] = communication
    rows = []
    for entry in entries:
        communication = by_application.get(entry.application_id)
        if communication is not None:
            label = CommunicationStatus.label(communication.status)
            badge = "pass" if communication.status == CommunicationStatus.SENT else "fail"
            sender = communication.sender_label
        elif ranking_list.notifications_sent_at is None:
            label, badge, sender = "Δεν στάλθηκε email", "pending", "—"
        else:
            label, badge, sender = "Μόνο ταχυδρομικώς (χωρίς email)", "pending", "—"
        rows.append(ListNotification(entry, communication, label, badge, sender))
    return rows


@dataclass
class ListChange:
    """Μια αίτηση της οποίας το αποτέλεσμα ή η θέση διαφέρει μεταξύ Προκαταρκτικού και Τελικού (Ενότ. 7)."""

    application: PlotApplication
    kind: str
    preliminary_text: str
    preliminary_badge: str
    final_text: str
    final_badge: str
    reasons: list[str]
    is_direct: bool
    sort_key: tuple


def _placement(group: str | None, rank: int | None) -> tuple[str, str]:
    if group is None:
        return "Δεν περιλαμβάνεται", "pending"
    if group == BENEFICIARIES:
        return f"ΔΙΚΑΙΟΥΧΟΣ — θέση {rank}", "pass"
    return "ΜΗ ΔΙΚΑΙΟΥΧΟΣ", "fail"


def _change_reasons(application: PlotApplication, kind: str) -> tuple[list[str], bool]:
    reasons = []
    is_direct = False
    for objection in application.objections.all():
        text = f"Ένσταση — {objection.get_objection_type_display()}: {objection.get_status_display()}"
        if objection.decision_notes:
            text += f" — {objection.decision_notes}"
        reasons.append(text)
        is_direct = is_direct or objection.status != Objection.Status.DISMISSED
    if (
        kind == "Αλλαγή αποτελέσματος"
        and application.eligibility_override
        and application.eligibility_override_reason
    ):
        reasons.append(
            f"Χειροκίνητη αλλαγή σε {application.get_eligibility_override_display()}: "
            f"{application.eligibility_override_reason}"
        )
        is_direct = True
    if not is_direct and kind == "Αλλαγή θέσης":
        reasons.append("Μετακίνηση λόγω αλλαγών σε άλλες αιτήσεις (ενστάσεις).")
    return reasons, is_direct


def list_changes(state: CommunityLists) -> list[ListChange]:
    """Οι διαφορές του Τελικού Καταλόγου (εκδοθέντος ή υπό κατάρτιση) έναντι του Προκαταρκτικού."""
    if state.preliminary is None:
        return []
    listing = final_listing(state)
    if listing is None:
        return []
    before = {
        entry.application_id: (
            OTHERS if entry.status == RankingEntry.Status.REJECTED else BENEFICIARIES,
            entry.proposed_rank,
        )
        for entry in state.preliminary.entries.all()
    }
    after = {}
    applications = {}
    for row in listing.beneficiaries:
        after[row.application.pk] = (BENEFICIARIES, row.position)
        applications[row.application.pk] = row.application
    for row in listing.others:
        after[row.application.pk] = (OTHERS, None)
        applications[row.application.pk] = row.application
    missing = set(before) - set(after)
    if missing:
        for app in PlotApplication.objects.filter(pk__in=missing).prefetch_related("objections"):
            applications[app.pk] = app

    changes = []
    for app_id, application in applications.items():
        old = before.get(app_id, (None, None))
        new = after.get(app_id, (None, None))
        if old == new:
            continue
        if old[0] is None:
            kind = "Νέα αίτηση στον κατάλογο"
        elif new[0] is None:
            kind = "Εκτός Τελικού Καταλόγου"
        elif old[0] != new[0]:
            kind = "Αλλαγή αποτελέσματος"
        else:
            kind = "Αλλαγή θέσης"
        reasons, is_direct = _change_reasons(application, kind)
        preliminary_text, preliminary_badge = _placement(*old)
        final_text, final_badge = _placement(*new)
        if kind == "Αλλαγή θέσης":
            moved = old[1] - new[1]
            final_text += f" ({'▲' if moved > 0 else '▼'} {abs(moved)})"
        group_order = {BENEFICIARIES: 0, OTHERS: 1, None: 2}[new[0]]
        changes.append(
            ListChange(
                application=application,
                kind=kind,
                preliminary_text=preliminary_text,
                preliminary_badge=preliminary_badge,
                final_text=final_text,
                final_badge=final_badge,
                reasons=reasons,
                is_direct=is_direct,
                sort_key=(group_order, new[1] or 0, application.protocol_number),
            )
        )
    return sorted(changes, key=lambda change: change.sort_key)
