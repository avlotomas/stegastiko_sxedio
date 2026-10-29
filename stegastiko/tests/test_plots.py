"""«Οικόπεδα» (completed plots), «Ολοκλήρωση αίτησης» and the stand-alone announcements."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from applications.models import Person
from cases.models import ApprovedDesignPlot, Case, InfrastructureCheck, SubmissionCycle, YesNo
from cases.services import completion_readiness
from core.models import Community
from plots.models import Plot
from plots.services import complete_case, publish_announcement
from tests.fixtures.cycles import make_cycle
from tests.fixtures.plot_applications import make_plot_application

JSON = {"HTTP_ACCEPT": "application/json"}


@pytest.fixture
def community(db):
    return Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        municipality_type="Κοινότητα",
        name="ΑΒΓ",
        contact_email="ks.abg@example.org",
        community_folder_code="001",
    )


@pytest.fixture
def other_community(db):
    return Community.objects.create(
        district="ΛΕΥΚΩΣΙΑΣ",
        name="ΔΕΖ",
        contact_email="ks.dez@example.org",
        community_folder_code="002",
    )


@pytest.fixture
def staff_client(client, make_user):
    client.force_login(make_user("supervisor", "Προϊστάμενος ελέγχου"))
    return client


def _design_plot(case, number="1", plot_type=ApprovedDesignPlot.PlotType.DIVISION_PLOT, **extra):
    values = {
        "design_number": number,
        "final_area_sqm": Decimal("600"),
        "has_separate_title": YesNo.YES,
        "valuation_amount": Decimal("70000"),
    }
    values.update(extra)
    return ApprovedDesignPlot.objects.create(case=case, plot_type=plot_type, **values)


def _ready_case(community, number="CASE-ABG-01", plots=("1", "2")):
    case = Case.objects.create(
        community=community,
        case_number=number,
        start_date=date(2026, 1, 1),
        contact_email=community.contact_email,
        dls_response_date=date(2027, 6, 1),
    )
    InfrastructureCheck.objects.create(
        case=case,
        check_date=date(2027, 5, 15),
        curbs_ready=True,
        pavements_ready=True,
        asphalt_ready=True,
    )
    for number in plots:
        _design_plot(case, number)
    return case


def _allocate(plot, community):
    from allocation.models import Allocation

    person = Person.objects.create(
        identity_number="ID-1",
        first_name="Α",
        last_name="Β",
        date_of_birth=date(1990, 1, 1),
        birth_place="Λευκωσία",
        birth_country="Κύπρος",
        parents_birth_place="Λευκωσία",
        parents_birth_country="Κύπρος",
    )
    application = make_plot_application(community, person)
    return Allocation.objects.create(application=application, parcel=plot)


def _manual_plot(community, number="M-1", **extra):
    values = {"valuation_amount": Decimal("50000"), "final_area_sqm": Decimal("500")}
    values.update(extra)
    return Plot.objects.create(community=community, design_number=number, **values)


# --- Ολοκλήρωση αίτησης ------------------------------------------------------------------------


@pytest.mark.django_db
def test_completion_creates_a_plot_per_division_plot_only(community):
    case = _ready_case(community)
    _design_plot(case, "Π1", plot_type=ApprovedDesignPlot.PlotType.GREEN_SPACE)
    _design_plot(case, "Υ1", plot_type=ApprovedDesignPlot.PlotType.EAC_SUBSTATION)

    summary = complete_case(case)

    assert summary["created"] == 2
    plots = list(Plot.objects.order_by("design_number"))
    assert [plot.design_number for plot in plots] == ["1", "2"]
    for plot in plots:
        assert plot.community == community
        assert plot.source_case == case
        assert plot.source_design_plot.case == case
        assert plot.final_area_sqm == Decimal("600")
        assert plot.disposal_price == Decimal("17500.00")
    case.refresh_from_db()
    assert case.is_completed


@pytest.mark.django_db
def test_completing_again_never_duplicates_and_updates_changed_plots(community):
    case = _ready_case(community)
    complete_case(case)

    changed = case.approved_design_plots.get(design_number="1")
    changed.final_area_sqm = Decimal("650")
    changed.save()
    _design_plot(case, "3")

    summary = complete_case(case)

    assert summary == {"created": 1, "updated": 1, "unchanged": 1, "allocated": 0}
    assert Plot.objects.count() == 3
    assert Plot.objects.get(source_design_plot=changed).final_area_sqm == Decimal("650")

    complete_case(case)
    assert Plot.objects.count() == 3


@pytest.mark.django_db
def test_completing_again_leaves_an_allocated_plot_unchanged(community):
    case = _ready_case(community, plots=("1",))
    complete_case(case)
    plot = Plot.objects.get()
    _allocate(plot, community)

    design_plot = plot.source_design_plot
    design_plot.final_area_sqm = Decimal("999")
    design_plot.save()
    summary = complete_case(case)

    assert summary["allocated"] == 1
    plot.refresh_from_db()
    assert plot.final_area_sqm == Decimal("600")


@pytest.mark.django_db
def test_a_design_plot_can_never_produce_two_plots(community):
    case = _ready_case(community, plots=("1",))
    complete_case(case)
    design_plot = case.approved_design_plots.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        Plot.objects.create(community=community, source_case=case, source_design_plot=design_plot)


@pytest.mark.django_db
def test_completion_is_allowed_when_the_case_is_not_ready(community):
    case = _ready_case(community, plots=())
    _design_plot(case, "1", valuation_amount=None)
    assert not completion_readiness(case)["ready"]
    summary = complete_case(case)
    assert summary["created"] == 1
    case.refresh_from_db()
    assert case.is_completed


@pytest.mark.django_db
def test_completion_view(community, staff_client):
    case = _ready_case(community)
    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert reverse("cases:complete", args=[case.pk]) in detail
    assert "Συνολική ετοιμότητα" in detail

    response = staff_client.post(reverse("cases:complete", args=[case.pk]), follow=True)
    assert response.status_code == 200
    assert "δημιουργήθηκαν 2 νέα οικόπεδα" in response.content.decode()
    assert Plot.objects.filter(source_case=case).count() == 2
    assert "Επανάληψη ολοκλήρωσης" in response.content.decode()

    staff_client.post(reverse("cases:complete", args=[case.pk]))
    assert Plot.objects.filter(source_case=case).count() == 2


@pytest.mark.django_db
def test_completion_needs_its_own_access(community, client, make_user):
    case = _ready_case(community)
    client.force_login(make_user("officer", "Λειτουργός καταχώρισης"))
    assert client.post(reverse("cases:complete", args=[case.pk])).status_code == 403
    assert not Plot.objects.exists()


@pytest.mark.django_db
def test_completion_view_when_not_ready(community, staff_client):
    case = _ready_case(community, plots=())
    _design_plot(case, "1", valuation_amount=None)
    detail = staff_client.get(reverse("cases:detail", args=[case.pk])).content.decode()
    assert "Η ολοκλήρωση επιτρέπεται" in detail
    response = staff_client.post(reverse("cases:complete", args=[case.pk]), follow=True)
    assert "Η αίτηση ολοκληρώθηκε" in response.content.decode()
    assert Plot.objects.filter(source_case=case).count() == 1


# --- 7.3 rows that became plots ----------------------------------------------------------------


@pytest.mark.django_db
def test_design_plot_that_became_a_plot_cannot_be_deleted_or_retyped(community, staff_client):
    case = _ready_case(community, plots=("1",))
    complete_case(case)
    design_plot = case.approved_design_plots.get()

    response = staff_client.post(
        reverse("cases:approved_design_plot_delete", args=[case.pk, design_plot.pk]), **JSON
    )
    assert response.status_code == 409
    assert "Οικόπεδα" in response.json()["message"]
    assert ApprovedDesignPlot.objects.filter(pk=design_plot.pk).exists()

    response = staff_client.post(
        reverse("cases:approved_design_plot_edit", args=[case.pk, design_plot.pk]),
        {"plot_type": "green_space", "plot_type_other": "", "design_number": "1"},
        **JSON,
    )
    assert response.status_code == 400
    design_plot.refresh_from_db()
    assert design_plot.plot_type == ApprovedDesignPlot.PlotType.DIVISION_PLOT


@pytest.mark.django_db
def test_deleting_the_plot_frees_the_design_plot(community, staff_client):
    case = _ready_case(community, plots=("1",))
    complete_case(case)
    plot = Plot.objects.get()
    design_plot = plot.source_design_plot

    response = staff_client.post(reverse("plots:delete", args=[plot.pk]))
    assert response.status_code == 302
    assert not Plot.objects.exists()

    response = staff_client.post(
        reverse("cases:approved_design_plot_delete", args=[case.pk, design_plot.pk]), **JSON
    )
    assert response.status_code == 200
    assert not ApprovedDesignPlot.objects.filter(pk=design_plot.pk).exists()


@pytest.mark.django_db
def test_allocated_plot_cannot_be_deleted(community, staff_client):
    plot = _manual_plot(community)
    _allocate(plot, community)
    response = staff_client.post(reverse("plots:delete", args=[plot.pk]), follow=True)
    assert "έχει κατανομή" in response.content.decode()
    assert Plot.objects.filter(pk=plot.pk).exists()


# --- «Οικόπεδα» screens ------------------------------------------------------------------------


@pytest.mark.django_db
def test_manual_plot_entry(community, staff_client):
    response = staff_client.post(
        reverse("plots:create"),
        {
            "community": community.pk,
            "numbering_status": Plot.NumberingStatus.TITLE_DEED,
            "title_deed_number": "T-55",
            "final_area_sqm": "720",
            "valuation_amount": "80000",
        },
    )
    assert response.status_code == 302
    plot = Plot.objects.get()
    assert plot.is_manual
    assert plot.community == community
    assert plot.disposal_price == Decimal("20000.00")

    html = staff_client.get(reverse("plots:list")).content.decode()
    assert "Οικόπεδο T-55" in html
    assert "Χειροκίνητη καταχώριση" in html


@pytest.mark.django_db
def test_plot_needs_a_community(staff_client):
    response = staff_client.post(
        reverse("plots:create"), {"numbering_status": Plot.NumberingStatus.DESIGN}
    )
    assert response.status_code == 200
    assert not Plot.objects.exists()


@pytest.mark.django_db
def test_plot_list_filters_by_source_case(community, staff_client):
    case = _ready_case(community, plots=("1",))
    complete_case(case)
    _manual_plot(community, number="M-9")

    html = staff_client.get(
        reverse("plots:list") + f"?source_case={case.pk}"
    ).content.decode()
    assert case.case_number in html
    assert "Οικόπεδο M-9" not in html

    html = staff_client.get(reverse("plots:list") + "?origin=manual").content.decode()
    assert "Οικόπεδο M-9" in html
    assert "Οικόπεδο 1<" not in html


@pytest.mark.django_db
def test_read_only_role_sees_plots_without_editing(community, client, make_user):
    plot = _manual_plot(community)
    client.force_login(make_user("reader", "Μόνο ανάγνωση"))
    html = client.get(reverse("plots:detail", args=[plot.pk])).content.decode()
    assert "disabled" in html
    assert ">Αποθήκευση</button>" not in html
    assert client.post(reverse("plots:detail", args=[plot.pk]), {}).status_code == 403
    assert client.get(reverse("plots:create")).status_code == 403


@pytest.mark.django_db
def test_main_menu_links_to_plots_and_announcements(staff_client):
    html = staff_client.get(reverse("home")).content.decode()
    assert reverse("plots:list") in html
    assert reverse("announcements:list") in html


# --- Γνωστοποιήσεις --------------------------------------------------------------------------


def _step2(client, *plots):
    """The wizard's second screen, after choosing `plots` on the first."""
    response = client.get(
        reverse("announcements:create"),
        {"plots": [plot.pk for plot in plots], "next": "1"},
    )
    assert response.status_code == 200
    return response


def _announcement_post(plots, **extra):
    data = {
        "plots": [plot.pk for plot in plots],
        "announcement_date": "2027-06-01",
        "submission_months": "1",
    }
    data.update(extra)
    return data


@pytest.mark.django_db
def test_announcement_wizard_step_one_lists_plots_to_choose(community, other_community, staff_client):
    plot = _manual_plot(community)
    html = staff_client.get(reverse("announcements:create")).content.decode()
    assert response_step(html) == 1
    assert f'name="plots" value="{plot.pk}"' in html
    assert "1 διαθέσιμα οικόπεδα" in html
    # Community without available plots (`other_community`) is not shown at all
    assert f'data-community-group="{community.pk}"' in html
    assert f'data-community-group="{other_community.pk}"' not in html
    assert other_community.name not in html


@pytest.mark.django_db
def test_plot_in_active_announcement_is_not_available_until_closed(community, other_community, staff_client):
    plot1 = _manual_plot(community, number="A-1")
    plot2 = _manual_plot(community, number="A-2")
    cycle = make_cycle(community, plots=[plot1], announcement_date=date(2027, 6, 1))

    # Across all active stages (1 through 7), plot1 is in an active announcement and not available
    for stage in SubmissionCycle.ACTIVE_STAGES:
        cycle.stage = stage
        cycle.save(update_fields=["stage"])
        assert cycle.is_active is True
        assert list(Plot.objects.available()) == [plot2]

    # Step 1 of creating a new announcement shows only plot2 (not plot1)
    html = staff_client.get(reverse("announcements:create")).content.decode()
    assert f'name="plots" value="{plot2.pk}"' in html
    assert f'name="plots" value="{plot1.pk}"' not in html

    # Adding plot1 to another active announcement is rejected
    with pytest.raises(ValidationError), transaction.atomic():
        make_cycle(community, plots=[plot1], announcement_date=date(2027, 7, 1))

    # If plot2 is also placed in an active announcement, `community` has 0 available plots and is hidden
    cycle.plots.add(plot2)
    assert not Plot.objects.available().exists()
    html_empty = staff_client.get(reverse("announcements:create")).content.decode()
    assert f'data-community-group="{community.pk}"' not in html_empty
    assert "Δεν υπάρχουν διαθέσιμα οικόπεδα." in html_empty


def response_step(html):
    return 2 if "Βήμα 2" in html else 1


@pytest.mark.django_db
def test_announcement_step_one_needs_a_plot(staff_client):
    response = staff_client.get(reverse("announcements:create"), {"next": "1"})
    assert response.status_code == 200
    assert response_step(response.content.decode()) == 1
    assert "Επιλέξτε τουλάχιστον ένα διαθέσιμο οικόπεδο." in response.content.decode()


@pytest.mark.django_db
def test_announcement_offers_available_plots_of_its_community(community, other_community, staff_client):
    case = _ready_case(community)
    complete_case(case)
    manual = _manual_plot(community)
    unvalued = _manual_plot(community, number="M-2", valuation_amount=None)
    other_plot = _manual_plot(other_community, number="X-1")

    offered = list(Plot.objects.filter(source_case=case)) + [manual]
    html = _step2(staff_client, *offered).content.decode()
    assert response_step(html) == 2
    for plot in Plot.objects.filter(source_case=case):
        assert f'name="plots" value="{plot.pk}"' in html
    assert f'name="plots" value="{manual.pk}"' in html
    assert f'name="plots" value="{other_plot.pk}"' not in html
    assert f'name="plots" value="{unvalued.pk}"' not in html
    assert html.count(" checked") >= 3

    response = staff_client.post(
        reverse("announcements:create"), _announcement_post(offered)
    )
    assert response.status_code == 302
    cycle = SubmissionCycle.objects.get()
    assert cycle.community == community
    assert set(cycle.plots.all()) == set(offered)
    assert cycle.submission_months == 1
    assert cycle.submission_end_date == date(2027, 7, 1)


@pytest.mark.django_db
def test_announcement_step_two_does_not_offer_allocated_plots(community, other_community, staff_client):
    held = _manual_plot(community, number="H-1")
    free = _manual_plot(community, number="H-2")
    _allocate(held, community)
    html = _step2(staff_client, free).content.decode()
    assert f'name="plots" value="{free.pk}"' in html
    assert f'name="plots" value="{held.pk}"' not in html


@pytest.mark.django_db
def test_announcement_refuses_plots_from_multiple_communities(community, other_community, staff_client):
    first = _manual_plot(community, number="A-1")
    foreign = _manual_plot(other_community, number="B-1")
    response = staff_client.get(
        reverse("announcements:create"), {"plots": [first.pk, foreign.pk], "next": "1"}
    )
    assert response_step(response.content.decode()) == 1
    assert "ίδια Κοινότητα" in response.content.decode()

    post = staff_client.post(
        reverse("announcements:create"), _announcement_post([first, foreign])
    )
    assert post.status_code == 200
    assert not SubmissionCycle.objects.exists()


@pytest.mark.django_db
def test_announcement_list_filters_by_community_of_its_plots(community, other_community, staff_client):
    p1 = _manual_plot(community, number="C-1")
    p2 = _manual_plot(other_community, number="C-2")
    make_cycle(community, plots=[p1], announcement_date=date(2027, 6, 1))
    second = make_cycle(other_community, plots=[p2], announcement_date=date(2027, 6, 1))
    html = staff_client.get(reverse("announcements:list"), {"community_id": other_community.pk}).content.decode()
    assert reverse("announcements:detail", args=[second.pk]) in html
    assert "ΔΕΖ" in html


@pytest.mark.django_db
def test_allocated_plot_is_not_offered_again(community):
    plot = _manual_plot(community)
    assert list(Plot.objects.available()) == [plot]
    _allocate(plot, community)
    assert not Plot.objects.available().exists()


@pytest.mark.django_db
def test_publish_needs_at_least_one_plot(community):
    cycle = make_cycle(
        community,
        announcement_date=date(2027, 6, 1),
    )
    with pytest.raises(ValidationError):
        publish_announcement(cycle)

    cycle.plots.add(_manual_plot(community))
    publish_announcement(cycle)  # the publication dates are optional
    cycle.refresh_from_db()
    assert cycle.is_published


@pytest.mark.django_db
def test_plot_in_published_announcement_cannot_be_deleted(community, staff_client):
    plot = _manual_plot(community)
    cycle = make_cycle(
        community,
        announcement_date=date(2027, 6, 1),
        published_at="2027-06-01T10:00:00Z",
    )
    cycle.plots.add(plot)
    staff_client.post(reverse("plots:delete", args=[plot.pk]))
    assert Plot.objects.filter(pk=plot.pk).exists()


@pytest.mark.django_db
def test_plot_list_shows_and_filters_by_announcement_availability(community, staff_client):
    available_plot = _manual_plot(community, number="AV-1")
    in_cycle_plot = _manual_plot(community, number="CY-1")
    allocated_plot = _manual_plot(community, number="AL-1")
    unvalued_plot = _manual_plot(community, number="UV-1", valuation_amount=None)

    active_cycle = make_cycle(
        community,
        plots=[in_cycle_plot],
        announcement_date=date(2027, 6, 1),
    )
    _allocate(allocated_plot, community)

    assert available_plot.is_available_for_announcement is True
    assert available_plot.announcement_unavailability_reason == ""
    assert in_cycle_plot.is_available_for_announcement is False
    assert in_cycle_plot.active_announcement == active_cycle
    assert in_cycle_plot.announcement_unavailability_reason == "Σε ενεργή γνωστοποίηση"
    assert allocated_plot.is_available_for_announcement is False
    assert allocated_plot.announcement_unavailability_reason == "Έχει κατανομή"
    assert unvalued_plot.is_available_for_announcement is False
    assert unvalued_plot.announcement_unavailability_reason == "Εκκρεμεί αξία/τιμή διάθεσης"

    # Full list shows availability column and reasons
    html = staff_client.get(reverse("plots:list")).content.decode()
    assert "Διαθέσιμο για γνωστοποίηση" in html
    assert f'data-plot-availability="{available_plot.pk}"' in html
    assert "Σε ενεργή γνωστοποίηση (01/06/2027)" in html
    assert "Έχει κατανομή" in html
    assert "Εκκρεμεί αξία/τιμή διάθεσης" in html

    # Filter by available only
    html_avail = staff_client.get(
        reverse("plots:list"), {"availability": "available"}
    ).content.decode()
    assert f'data-plot-row="{available_plot.pk}"' in html_avail
    assert f'data-plot-row="{in_cycle_plot.pk}"' not in html_avail
    assert f'data-plot-row="{allocated_plot.pk}"' not in html_avail
    assert f'data-plot-row="{unvalued_plot.pk}"' not in html_avail

    # Filter by unavailable only
    html_unavail = staff_client.get(
        reverse("plots:list"), {"availability": "unavailable"}
    ).content.decode()
    assert f'data-plot-row="{available_plot.pk}"' not in html_unavail
    assert f'data-plot-row="{in_cycle_plot.pk}"' in html_unavail
    assert f'data-plot-row="{allocated_plot.pk}"' in html_unavail
    assert f'data-plot-row="{unvalued_plot.pk}"' in html_unavail

    # Once `active_cycle` is completed (`CLOSED`), `in_cycle_plot` becomes available again
    active_cycle.stage = SubmissionCycle.Stage.CLOSED
    active_cycle.save(update_fields=["stage"])
    html_avail_after = staff_client.get(
        reverse("plots:list"), {"availability": "available"}
    ).content.decode()
    assert f'data-plot-row="{available_plot.pk}"' in html_avail_after
    assert f'data-plot-row="{in_cycle_plot.pk}"' in html_avail_after

