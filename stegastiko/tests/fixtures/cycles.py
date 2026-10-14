"""Announcements (SubmissionCycle) for tests: one announcement may cover several communities."""

from cases.models import SubmissionCycle


def make_cycle(*communities, **fields) -> SubmissionCycle:
    cycle = SubmissionCycle.objects.create(**fields)
    cycle.communities.add(*communities)
    return cycle
