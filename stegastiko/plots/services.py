"""Completing a division case into plots, and the announcements (Ενότητα 9) that offer them."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from cases.models import ApprovedDesignPlot, Case, SubmissionCycle
from plots.models import Plot


@transaction.atomic
def complete_case(case: Case, user=None) -> dict:
    """«Ολοκλήρωση αίτησης»: every «Υπό διαχωρισμό οικόπεδο» row of 7.3 becomes a Plot.

    Completing again after further changes never duplicates a plot: a row that already
    produced one updates it instead (Plot.source_design_plot is unique), unless that plot
    has been allocated, in which case it is left as it is.

    The readiness check (completion_readiness) is advisory only: the case can be completed
    even when it does not pass.
    """
    case = Case.objects.select_for_update().select_related("community").get(pk=case.pk)
    summary = {"created": 0, "updated": 0, "unchanged": 0, "allocated": 0}
    design_plots = case.approved_design_plots.filter(
        plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT
    ).select_related("plot")
    for design_plot in design_plots:
        plot = design_plot.generated_plot
        if plot is None:
            plot = Plot(community=case.community, source_case=case, source_design_plot=design_plot)
            plot.copy_from(design_plot)
            plot.save()
            summary["created"] += 1
        elif plot.is_allocated:
            summary["allocated"] += 1
        else:
            changed = plot.copy_from(design_plot)
            if changed:
                plot.save(update_fields=changed)
                summary["updated"] += 1
            else:
                summary["unchanged"] += 1
    case.completed_at = timezone.now()
    case.completed_by = user if user is not None and user.is_authenticated else None
    case.save(update_fields=["completed_at", "completed_by"])
    return summary


def completion_message(summary: dict) -> str:
    parts = [f"δημιουργήθηκαν {summary['created']} νέα οικόπεδα"]
    if summary["updated"]:
        parts.append(f"ενημερώθηκαν {summary['updated']}")
    if summary["unchanged"]:
        parts.append(f"{summary['unchanged']} χωρίς αλλαγές")
    if summary["allocated"]:
        parts.append(f"{summary['allocated']} με κατανομή δεν άλλαξαν")
    return "Η αίτηση ολοκληρώθηκε: " + ", ".join(parts) + "."


def create_announcement(form) -> SubmissionCycle:
    """9.1 Create the announcement of a valid SubmissionCycleForm, with its 9.3 draft."""
    with transaction.atomic():
        cycle = form.save(commit=False)
        cycle.community = form.community
        cycle.save()
        form.save_m2m()
        cycle.announcement_text = build_announcement_text(cycle)
        cycle.save()
    return cycle


def build_announcement_text(cycle: SubmissionCycle) -> str:
    """9.3 Automatic draft from the offered plots and the submission period.

    The exact approved wording is still pending (Ε-68), so this is a working draft
    that the operator previews and edits before finalising.
    """
    community = cycle.community
    case_numbers = sorted(
        {
            plot.source_case.case_number
            for plot in cycle.plots.select_related("source_case")
            if plot.source_case_id
        }
    )
    return (
        "ΑΝΑΚΟΙΝΩΣΗ\n"
        "Στεγαστικό Σχέδιο Διάθεσης Οικοπέδων\n\n"
        f"Επαρχία: {community.district}\n"
        f"Κοινότητα / Δ.Δ.: {community.name}\n"
        f"Αρ. Φακέλου/ων υπόθεσης: {', '.join(case_numbers) or '—'}\n"
        f"Αριθμός διαθέσιμων οικοπέδων: {cycle.available_plots_count}\n\n"
        f"Ημερομηνία γνωστοποίησης: {cycle.announcement_date}\n"
        f"Έναρξη υποβολής αιτήσεων: {cycle.submission_start_date}\n"
        f"Λήξη υποβολής αιτήσεων: {cycle.submission_end_date}\n\n"
        "Καλούνται οι ενδιαφερόμενες οικογένειες να υποβάλουν αίτηση (Παράρτημα 3) "
        "εντός της ανωτέρω προθεσμίας, μαζί με τα απαιτούμενα δικαιολογητικά.\n"
    )


def publish_announcement(cycle: SubmissionCycle) -> SubmissionCycle:
    """9.3 Finalise and issue the announcement; it must offer at least one plot."""
    if cycle.is_published:
        raise ValidationError("Η ανακοίνωση έχει ήδη οριστικοποιηθεί.")
    if not cycle.announcement_text.strip():
        raise ValidationError("Δεν υπάρχει κείμενο ανακοίνωσης (9.3).")
    if not cycle.plots.exists():
        raise ValidationError("Η γνωστοποίηση δεν προσφέρει κανένα οικόπεδο (9.1).")
    cycle.published_at = timezone.now()
    cycle.save()
    return cycle
