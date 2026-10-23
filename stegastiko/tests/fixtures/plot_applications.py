"""Minimal Παράρτημα 3 applications for tests that only need an application to point at."""

from datetime import date

from plot_applications.models import PlotApplication, ResidenceCategory


def make_plot_application(community, applicant, spouse=None, **extra) -> PlotApplication:
    values = dict(
        community=community,
        protocol_number=f"T-{PlotApplication.objects.count() + 1:03d}",
        submitted_on=date(2027, 6, 10),
        applicant=applicant,
        spouse=spouse,
        email="a@example.org",
        residence_category=ResidenceCategory.AUTOCHTHON,
        residence_community=community.name,
        family_status=(
            PlotApplication.FamilyStatus.COUPLE_WITHOUT_CHILDREN
            if spouse
            else PlotApplication.FamilyStatus.SINGLE_PARENT
        ),
    )
    values.update(extra)
    return PlotApplication.objects.create(**values)
