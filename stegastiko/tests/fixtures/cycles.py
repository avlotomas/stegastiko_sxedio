"""Announcements (SubmissionCycle) for tests: each announcement offers plots of one community."""

from cases.models import SubmissionCycle


def make_cycle(*communities, plots=None, **fields) -> SubmissionCycle:
    cycle = SubmissionCycle.objects.create(**fields)
    if communities:
        cycle._fallback_community = communities[0]
    if plots:
        cycle.plots.add(*plots)
    return cycle
