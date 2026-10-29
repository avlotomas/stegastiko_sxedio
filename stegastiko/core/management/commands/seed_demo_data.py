"""Replace the working data with realistic demo data for local testing.

Deletes every division case, plot, announcement (Γνωστοποίηση), Παράρτημα 3 application,
allocation and person, then creates division cases at different stages (Ενότητες 1–7),
the plots they produced plus plots entered by hand, announcements, persons and plot
applications that cover the residence categories and family types of Ενότ. 10–11.
Communities, users, roles and settings are left untouched.
"""

from datetime import date, datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from allocation.models import Allocation, Lottery, RankingList
from applications.models import Person
from cases.models import (
    ApprovedDesignPlot,
    Case,
    CompletenessCheck,
    Consultation,
    Field,
    InfrastructureCheck,
    LandPlot,
    MinistryDecisionRound,
    SubmissionCycle,
    SubmissionCyclePublication,
    UtilityService,
    UtilityServiceType,
    ValuationReferral,
    YesNo,
)
from cases.services import create_case
from core.models import Attachment, Communication, Community
from plot_applications.documents import applicable_documents
from plot_applications.models import (
    ApplicationChild,
    ApplicationParty,
    IncomeDeclaration,
    PlotApplication,
    ResidenceCategory,
)
from plot_applications.rules import apply_evaluation, parameter
from plot_applications.services import save_with_new_protocol_number
from plots.models import Plot
from plots.services import complete_case

YES, NO = YesNo.YES, YesNo.NO
Family = PlotApplication.FamilyStatus
SingleParent = PlotApplication.SingleParentStatus
Child = ApplicationChild.Status
Member = IncomeDeclaration.Member
Work = IncomeDeclaration.EmploymentType
DIVISION_PLOT = ApprovedDesignPlot.PlotType.DIVISION_PLOT
Numbering = ApprovedDesignPlot.NumberingStatus


def d(value: str) -> date:
    return date.fromisoformat(value)


def moment(value: str, hour: int = 10):
    return timezone.make_aware(datetime.combine(d(value), datetime.min.time()).replace(hour=hour))


def community(name: str) -> Community:
    try:
        return Community.objects.get(name=name)
    except Community.DoesNotExist as exc:
        raise CommandError(f"Δεν βρέθηκε η Κοινότητα «{name}». Εκτελέστε πρώτα load_communities.") from exc


def service_type(name: str) -> UtilityServiceType:
    service, _ = UtilityServiceType.objects.get_or_create(name=name)
    return service


# ─────────────────────────────────────────────────────────────────────────────
# Διαγραφή
# ─────────────────────────────────────────────────────────────────────────────


def wipe() -> list[tuple[str, int]]:
    removed = []
    steps = (
        ("Κατανομές οικοπέδων", Allocation.objects.all()),
        ("Κληρώσεις", Lottery.objects.all()),
        ("Κατάλογοι κατάταξης", RankingList.objects.all()),
        (
            "Email αιτήσεων / οικοπέδων",
            Communication.objects.filter(
                content_type__app_label__in=("cases", "plots", "plot_applications")
            ),
        ),
        (
            "Αρχεία αιτήσεων / οικοπέδων",
            Attachment.objects.filter(
                content_type__app_label__in=("cases", "plots", "plot_applications")
            ),
        ),
        ("Αιτήσεις παραχώρησης οικοπέδου", PlotApplication.objects.all()),
        ("Γνωστοποιήσεις", SubmissionCycle.objects.all()),
        ("Οικόπεδα", Plot.objects.all()),
        ("Αιτήσεις διαχωρισμού", Case.objects.all()),
        ("Άτομα", Person.objects.all()),
    )
    for label, queryset in steps:
        removed.append((label, queryset.count()))
        queryset.delete()
    return removed


# ─────────────────────────────────────────────────────────────────────────────
# Αιτήσεις διαχωρισμού (Ενότητες 1–7) και τα οικόπεδά τους
# ─────────────────────────────────────────────────────────────────────────────


def new_case(community_name, start, **fields) -> Case:
    case = Case(community=community(community_name), start_date=d(start), **fields)
    return create_case(case)


def completeness(case, check_date, result, deficiencies="", comments=""):
    CompletenessCheck.objects.create(
        case=case, check_date=d(check_date), result=result, deficiencies=deficiencies, comments=comments
    )


def consultation(case, stage, department, topic, sent, due, response=None, text="", other=""):
    Consultation.objects.create(
        case=case,
        stage=stage,
        department=department,
        department_other=other,
        topic=topic,
        sent_date=d(sent),
        due_date=d(due),
        response_date=d(response) if response else None,
        response_text=text,
    )


def design_plots(case, sheet_plan, areas, *, rate=None, first_parcel=None, title_from=None,
                 numbering=Numbering.DESIGN, tkx_prefix="", fields=None, referral=None,
                 sources=(), with_final_area=True):
    """7.3 / 8.2 rows of type «Υπό διαχωρισμό οικόπεδο», numbered 1..n."""
    rows = []
    for index, area in enumerate(areas, start=1):
        area = Decimal(area)
        row = ApprovedDesignPlot(
            case=case,
            plot_type=DIVISION_PLOT,
            design_number=str(index),
            tkx_number=f"{tkx_prefix}{index}" if tkx_prefix else "",
            title_deed_number=str(title_from + index - 1) if title_from else "",
            parcel_number=str(first_parcel + index - 1) if first_parcel else "",
            sheet_plan=sheet_plan if first_parcel else "",
            final_area_sqm=area if with_final_area else None,
            has_separate_title=YES if title_from else "",
            valuation_amount=(area * Decimal(rate)).quantize(Decimal("1")) if rate else None,
            valuation_referral=referral,
            numbering_status=numbering,
            field=fields[(index - 1) * len(fields) // len(areas)] if fields else None,
        )
        row.save()
        if sources:
            row.source_land_plots.set(sources)
        rows.append(row)
    return rows


def other_space(case, plot_type, number, area, comments="", sources=()):
    row = ApprovedDesignPlot.objects.create(
        case=case,
        plot_type=plot_type,
        design_number=number,
        final_area_sqm=Decimal(area),
        comments=comments,
    )
    if sources:
        row.source_land_plots.set(sources)
    return row


def finish(case, completed_on):
    summary = complete_case(case)
    case.completed_at = moment(completed_on, 12)
    case.save(update_fields=["completed_at"])
    return summary


def case_akaki() -> Case:
    """Ολοκληρωμένη νέα αίτηση διαχωρισμού: όλες οι Ενότητες, 10 οικόπεδα."""
    case = new_case(
        "ΑΚΑΚΙ",
        "2023-02-06",
        submitted_at=d("2023-01-27"),
        contact_email="koinotiko.symvoulio.akakiou@example.com",
        priority_limited_private_land=True,
        priority_documentation=(
            "Περιορισμένη διαθεσιμότητα ιδιωτικής γης εντός του ορίου ανάπτυξης. Στον κατάλογο "
            "ενδιαφέροντος της Κοινότητας περιλαμβάνονται 38 νεαρά ζεύγη."
        ),
        comments="Αίτηση του Κοινοτικού Συμβουλίου με απόφαση της συνεδρίας 12/2022.",
        state_land_remains_sufficient=YES,
        state_land_comments="Παραμένουν περί τα 4,5 εκτάρια κρατικής γης βόρεια της Κοινότητας.",
        access_technical_evaluation=(
            "Το τεμάχιο 412 εφάπτεται της οδού Γυμνασίου (πλάτος 8 μ.). Το 415 εξυπηρετείται από "
            "αγροτικό δρόμο που χρειάζεται διαπλάτυνση στα 9 μ."
        ),
        engineer_full_name="Μιχάλης Ζαχαρίου",
        technical_visit_date=d("2023-04-18"),
        survey_assignment_date=d("2023-10-02"),
        surveyor_name="Κώστας Ηλιάδης",
        surveyor_phone="99 456123",
        surveyor_email="k.iliades.surveyor@example.com",
        division_design_status=Case.DesignStatus.COMPLETED,
        division_design_completed_on=d("2024-02-28"),
        division_design_plots_count=10,
        division_design_comments="10 οικόπεδα, χώρος πρασίνου 1.050 τ.μ. και υποσταθμός ΑΗΚ.",
        tpo_application_date=d("2024-03-11"),
        tpo_application_number="ΛΕΥ/00412/2024",
        tpo_response=Case.TpoResponse.CONDITIONAL,
        tpo_response_date=d("2024-07-22"),
        tpo_comments="Όροι: διαπλάτυνση δρόμου πρόσβασης στα 9 μ. και χώρος πρασίνου ≥ 10%.",
        construction_plans_stage="Εγκρίθηκαν τα κατασκευαστικά σχέδια οδοποιίας και ομβρίων (10/2024).",
        land_expropriation_required=NO,
        tender_announcement_date=d("2024-11-15"),
        tender_award_date=d("2025-01-20"),
        contractor_name="Λοϊζίδης Κατασκευαστική Λτδ",
        contractor_phone="22 456789",
        contractor_email="info@loizides-construction.example.com",
        contract_duration_value=10,
        contract_duration_unit=Case.ContractDurationUnit.MONTHS,
        dls_application_date=d("2025-11-10"),
        dls_file_number="Δ.Κ. 412/2025",
        dls_response_date=d("2026-04-14"),
        dls_comments="Εκδόθηκαν ξεχωριστοί τίτλοι ιδιοκτησίας για όλα τα οικόπεδα.",
    )
    completeness(
        case, "2023-02-20", NO,
        "Λείπει ο υπογεγραμμένος κατάλογος ≥ 10 οικογενειών και το τοπογραφικό απόσπασμα.",
    )
    completeness(case, "2023-03-15", YES, comments="Υποβλήθηκαν τα συμπληρωματικά στοιχεία.")

    lp412 = LandPlot.objects.create(
        case=case, parcel_number="412", sheet_plan="29/22", location="«Κόκκινα», βόρεια του Γυμνασίου",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("9850"), zone="Η3",
        inside_development_zone=YES, access=LandPlot.Access.PUBLIC_ROAD,
        morphology=LandPlot.Morphology.FLAT, usable_area_sqm=Decimal("9200"),
        estimated_cost=Decimal("420000"), estimated_plots_count=8,
        technical_suitability=LandPlot.SuitabilityDecision.SUITABLE,
        suitability_decision=LandPlot.SuitabilityDecision.SUITABLE,
        suitability_justification="Επίπεδο, εντός ορίου ανάπτυξης, με πρόσβαση σε δημόσιο δρόμο.",
    )
    lp415 = LandPlot.objects.create(
        case=case, parcel_number="415", sheet_plan="29/22", location="«Κόκκινα»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("3120"), zone="Η3",
        inside_development_zone=YES, access=LandPlot.Access.OTHER,
        access_other="Αγροτικός δρόμος — απαιτείται διαπλάτυνση",
        morphology=LandPlot.Morphology.MILD, usable_area_sqm=Decimal("2900"),
        estimated_cost=Decimal("160000"), estimated_plots_count=2,
        technical_suitability=LandPlot.SuitabilityDecision.CONDITIONAL,
        suitability_decision=LandPlot.SuitabilityDecision.SUITABLE,
        suitability_justification="Κατάλληλο με την προϋπόθεση διαπλάτυνσης του δρόμου πρόσβασης.",
    )
    LandPlot.objects.create(
        case=case, parcel_number="530", sheet_plan="29/30", location="«Πλατύ»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("6400"), zone="Γ3",
        inside_development_zone=NO, access=LandPlot.Access.OTHER, access_other="Χωματόδρομος",
        rejected=YES, comments="Εκτός ορίου ανάπτυξης.",
        suitability_decision=LandPlot.SuitabilityDecision.UNSUITABLE,
        suitability_justification="Γεωργική Ζώνη Γ3, εκτός ορίου ανάπτυξης.",
    )
    for name, proximity in (
        ("ΑΗΚ", "Δίκτυο χαμηλής τάσης στην οδό Γυμνασίου (≈ 30 μ.)"),
        ("Υδατοπρομήθεια", "Κεντρικός αγωγός Ø110 επί της οδού Γυμνασίου"),
        ("Αποχέτευση", "Δεν υπάρχει δίκτυο — σηπτικοί λάκκοι"),
        ("Τηλεπικοινωνίες", "Δίκτυο Cyta στο όριο του τεμαχίου 412"),
    ):
        UtilityService.objects.create(case=case, service_type=service_type(name), proximity=proximity)

    S, D = Consultation.Stage.SUITABILITY, Consultation.Stage.DIVISION
    consultation(case, S, Consultation.Department.TKX, "Ιδιοκτησιακό καθεστώς τεμαχίων 412, 415, 530",
                 "2023-05-02", "2023-06-02", "2023-05-29",
                 "Τα τεμάχια είναι εγγεγραμμένα στην Κυπριακή Δημοκρατία· καμία ένσταση.")
    consultation(case, S, Consultation.Department.TAY, "Πρόσβαση και απορροή ομβρίων",
                 "2023-05-02", "2023-06-02", "2023-06-10",
                 "Απαιτείται αγωγός ομβρίων κατά μήκος του νέου δρόμου.")
    consultation(case, S, Consultation.Department.AHK, "Ηλεκτροδότηση οικοπέδων",
                 "2023-05-02", "2023-06-02", "2023-05-24",
                 "Απαιτείται χώρος υποσταθμού 36 τ.μ.")
    consultation(case, D, Consultation.Department.TAY, "Κατασκευαστικά σχέδια οδοποιίας",
                 "2024-08-05", "2024-09-05", "2024-09-12", "Εγκρίνονται με μικρές τροποποιήσεις.")
    consultation(case, D, Consultation.Department.AHK, "Σχέδια υποσταθμού",
                 "2024-08-05", "2024-09-05", "2024-08-30", "Εγκρίνονται.")

    MinistryDecisionRound.objects.create(
        case=case, letter_sent_date=d("2023-07-10"),
        recommendation=MinistryDecisionRound.Recommendation.POSITIVE,
        ministry_response_date=d("2023-09-04"),
        ministry_decision=MinistryDecisionRound.MinistryDecision.APPROVED,
        comments="Εγκρίθηκε η αξιοποίηση των τεμαχίων 412 και 415.",
    )
    InfrastructureCheck.objects.create(
        case=case, stage="Χωματουργικά και κράσπεδα", check_date=d("2025-05-12"),
        curbs_ready=True, pavements_ready=True, water_ready=True,
        comments="Εκκρεμεί η ασφαλτόστρωση.",
    )
    InfrastructureCheck.objects.create(
        case=case, stage="Ολοκλήρωση ασφαλτόστρωσης", check_date=d("2025-10-30"),
        curbs_ready=True, pavements_ready=True, asphalt_ready=True, pavement_fill_ready=True,
        water_ready=True, telecom_ready=True, electricity_ready=True,
        comments="Εκκρεμεί μόνο η τοποθέτηση του οδικού φωτισμού.",
    )

    north = Field.objects.create(case=case, code="Χ1", description="Τεμάχιο 412 — βόρειο τμήμα")
    south = Field.objects.create(case=case, code="Χ2", description="Τεμάχια 412 (νότιο τμήμα) και 415")
    referral = ValuationReferral.objects.create(
        case=case, letter_date=d("2026-04-20"), reference_number="ΤΚΧ/ΕΚΤ/2026/1187",
        response_date=d("2026-05-28"), comments="Εκτίμηση αγοραίας αξίας 75 €/τ.μ.",
    )
    design_plots(
        case, "29/22", [552, 568, 541, 603, 615, 529, 537, 582, 644, 596],
        rate=75, first_parcel=1021, title_from=40211, numbering=Numbering.TITLE_DEED,
        tkx_prefix="Ο-", fields=[north, south], referral=referral, sources=[lp412, lp415],
    )
    other_space(case, ApprovedDesignPlot.PlotType.GREEN_SPACE, "Π1", 1050, sources=[lp412])
    other_space(case, ApprovedDesignPlot.PlotType.EAC_SUBSTATION, "Υ1", 36, sources=[lp415])
    finish(case, "2026-06-15")
    return case


def case_astromeritis() -> Case:
    """Ολοκληρωμένη νέα αίτηση διαχωρισμού με αρίθμηση ΤΚΧ, 8 οικόπεδα."""
    case = new_case(
        "ΑΣΤΡΟΜΕΡΙΤΗΣ",
        "2022-09-12",
        submitted_at=d("2022-09-01"),
        contact_email="astromeritis.community@example.com",
        priority_turkish_cypriot_properties=True,
        priority_documentation="Σημαντικό μέρος της γης είναι τουρκοκυπριακές περιουσίες.",
        state_land_remains_sufficient=YES,
        engineer_full_name="Ελένη Θεοδούλου",
        technical_visit_date=d("2022-11-23"),
        survey_assignment_date=d("2023-05-15"),
        surveyor_name="Ανδρέας Παπαμιχαήλ",
        surveyor_phone="99 612904",
        surveyor_email="a.papamichael.survey@example.com",
        division_design_status=Case.DesignStatus.COMPLETED,
        division_design_completed_on=d("2023-10-10"),
        division_design_plots_count=8,
        tpo_application_date=d("2023-10-30"),
        tpo_application_number="ΛΕΥ/01877/2023",
        tpo_response=Case.TpoResponse.POSITIVE,
        tpo_response_date=d("2024-02-19"),
        construction_plans_stage="Ολοκληρώθηκαν.",
        land_expropriation_required=NO,
        tender_announcement_date=d("2024-04-08"),
        tender_award_date=d("2024-06-03"),
        contractor_name="Χ. Κυριάκου & Υιοί Λτδ",
        contractor_phone="22 721450",
        contractor_email="tenders@kyriakou-sons.example.com",
        contract_duration_value=8,
        contract_duration_unit=Case.ContractDurationUnit.MONTHS,
        dls_application_date=d("2025-04-02"),
        dls_file_number="Δ.Κ. 198/2025",
        dls_response_date=d("2025-12-18"),
    )
    completeness(case, "2022-09-26", YES)
    lp = LandPlot.objects.create(
        case=case, parcel_number="87", sheet_plan="20/41", location="«Αλώνια»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("6300"), zone="Η2",
        inside_development_zone=YES, access=LandPlot.Access.PUBLIC_ROAD,
        morphology=LandPlot.Morphology.FLAT, usable_area_sqm=Decimal("5900"),
        estimated_cost=Decimal("310000"), estimated_plots_count=8,
        technical_suitability=LandPlot.SuitabilityDecision.SUITABLE,
        suitability_decision=LandPlot.SuitabilityDecision.SUITABLE,
    )
    UtilityService.objects.create(case=case, service_type=service_type("ΑΗΚ"), proximity="Στο όριο του τεμαχίου")
    UtilityService.objects.create(case=case, service_type=service_type("Υδατοπρομήθεια"), proximity="Αγωγός Ø90 επί της οδού Αλωνιών")
    consultation(case, Consultation.Stage.SUITABILITY, Consultation.Department.TKX,
                 "Ιδιοκτησιακό καθεστώς τεμαχίου 87", "2022-12-05", "2023-01-05", "2022-12-20",
                 "Κρατική γη· καμία ένσταση.")
    MinistryDecisionRound.objects.create(
        case=case, letter_sent_date=d("2023-02-01"),
        recommendation=MinistryDecisionRound.Recommendation.POSITIVE,
        ministry_response_date=d("2023-03-27"),
        ministry_decision=MinistryDecisionRound.MinistryDecision.APPROVED,
    )
    InfrastructureCheck.objects.create(
        case=case, stage="Τελικός έλεγχος", check_date=d("2025-02-14"),
        curbs_ready=True, pavements_ready=True, asphalt_ready=True, pavement_fill_ready=True,
        water_ready=True, telecom_ready=True, electricity_ready=True, street_light_ready=True,
    )
    referral = ValuationReferral.objects.create(
        case=case, letter_date=d("2026-01-12"), reference_number="ΤΚΧ/ΕΚΤ/2026/0094",
        response_date=d("2026-03-03"),
    )
    design_plots(
        case, "20/41", [640, 655, 612, 598, 701, 633, 620, 667],
        rate=62, first_parcel=233, numbering=Numbering.TKX, tkx_prefix="ΑΣΤ-",
        referral=referral, sources=[lp],
    )
    other_space(case, ApprovedDesignPlot.PlotType.GREEN_SPACE, "Π1", 720, sources=[lp])
    finish(case, "2026-05-20")
    return case


def case_agioi_trimithias() -> Case:
    """Σε εξέλιξη στην Ενότητα 7: κατασκευαστικές εργασίες, χωρίς τελικά εμβαδά και αξίες."""
    case = new_case(
        "ΑΓΙΟΙ ΤΡΙΜΙΘΙΑΣ",
        "2024-01-15",
        submitted_at=d("2024-01-08"),
        contact_email="agioi.trimithias@example.com",
        priority_nuisance_developments=True,
        priority_documentation="Βιομηχανική ζώνη και λατομεία στα διοικητικά όρια της Κοινότητας.",
        state_land_remains_sufficient=NO,
        state_land_comments="Μετά την αξιοποίηση δεν απομένει άλλη αξιοποιήσιμη κρατική γη.",
        engineer_full_name="Μιχάλης Ζαχαρίου",
        technical_visit_date=d("2024-03-06"),
        survey_assignment_date=d("2024-09-02"),
        surveyor_name="Σάββας Χριστοφόρου",
        surveyor_phone="99 334871",
        division_design_status=Case.DesignStatus.COMPLETED,
        division_design_completed_on=d("2025-01-24"),
        division_design_plots_count=14,
        tpo_application_date=d("2025-02-10"),
        tpo_application_number="ΛΕΥ/00233/2025",
        tpo_response=Case.TpoResponse.POSITIVE,
        tpo_response_date=d("2025-06-30"),
        land_expropriation_required=NO,
        tender_announcement_date=d("2025-10-06"),
        tender_award_date=d("2026-01-12"),
        contractor_name="Ε. Μιχαηλίδης Εργοληπτική Λτδ",
        contractor_phone="22 832610",
        contract_duration_value=12,
        contract_duration_unit=Case.ContractDurationUnit.MONTHS,
    )
    completeness(case, "2024-01-29", YES)
    lp = LandPlot.objects.create(
        case=case, parcel_number="1180", sheet_plan="29/45", location="«Λακκιά»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("11900"), zone="Η2",
        inside_development_zone=YES, access=LandPlot.Access.PUBLIC_ROAD,
        morphology=LandPlot.Morphology.FLAT, usable_area_sqm=Decimal("10800"),
        estimated_cost=Decimal("590000"), estimated_plots_count=14,
        technical_suitability=LandPlot.SuitabilityDecision.SUITABLE,
        suitability_decision=LandPlot.SuitabilityDecision.SUITABLE,
    )
    consultation(case, Consultation.Stage.SUITABILITY, Consultation.Department.TKX,
                 "Ιδιοκτησιακό καθεστώς", "2024-04-01", "2024-05-01", "2024-04-22", "Καμία ένσταση.")
    MinistryDecisionRound.objects.create(
        case=case, letter_sent_date=d("2024-06-03"),
        recommendation=MinistryDecisionRound.Recommendation.POSITIVE,
        ministry_response_date=d("2024-07-15"),
        ministry_decision=MinistryDecisionRound.MinistryDecision.APPROVED,
    )
    InfrastructureCheck.objects.create(
        case=case, stage="Χωματουργικά", check_date=d("2026-06-18"),
        comments="Ολοκληρώθηκε η χάραξη των δρόμων.",
    )
    InfrastructureCheck.objects.create(
        case=case, stage="Κράσπεδα και ρείθρα", check_date=d("2026-09-30"),
        curbs_ready=True, pavements_ready=True, water_ready=True,
        comments="Η ασφαλτόστρωση προγραμματίζεται για τον Νοέμβριο 2026.",
    )
    design_plots(
        case, "29/45", [560, 575, 548, 590, 602, 571, 566, 583, 597, 611, 558, 579, 624, 588],
        sources=[lp], with_final_area=False,
    )
    other_space(case, ApprovedDesignPlot.PlotType.GREEN_SPACE, "Π1", 1200, sources=[lp])
    other_space(case, ApprovedDesignPlot.PlotType.COMMUNITY_FACILITY, "Κ1", 450,
                comments="Χώρος παιδικής χαράς", sources=[lp])
    return case


def case_deneia() -> Case:
    """Σε εξέλιξη στις Ενότητες 5–6: διαβουλεύσεις σε εκκρεμότητα, αναμένεται η απόφαση ΥΠΕΣ."""
    case = new_case(
        "ΔΕΝΕΙΑ",
        "2026-02-09",
        submitted_at=d("2026-02-02"),
        contact_email="deneia.community@example.com",
        priority_turkish_cypriot_properties=True,
        priority_protection_zones=True,
        priority_documentation="Η Κοινότητα εφάπτεται της Νεκρής Ζώνης· μεγάλο μέρος της γης είναι τουρκοκυπριακές περιουσίες.",
        state_land_remains_sufficient=YES,
        engineer_full_name="Ελένη Θεοδούλου",
        technical_visit_date=d("2026-04-21"),
        access_technical_evaluation="Πρόσβαση από την κύρια οδό Δένειας–Ακακίου.",
    )
    completeness(case, "2026-02-23", YES)
    LandPlot.objects.create(
        case=case, parcel_number="305", sheet_plan="21/53", location="«Μουττάλλια»",
        ownership_status=LandPlot.OwnershipStatus.OTHER, ownership_other="Τουρκοκυπριακή περιουσία",
        area_sqm=Decimal("7200"), zone="Η3", inside_development_zone=YES,
        access=LandPlot.Access.PUBLIC_ROAD, morphology=LandPlot.Morphology.FLAT,
        usable_area_sqm=Decimal("6700"), estimated_cost=Decimal("350000"), estimated_plots_count=9,
        technical_suitability=LandPlot.SuitabilityDecision.SUITABLE,
    )
    LandPlot.objects.create(
        case=case, parcel_number="311", sheet_plan="21/53", location="«Μουττάλλια»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("2450"), zone="Η3",
        inside_development_zone=YES, access=LandPlot.Access.PUBLIC_ROAD,
        morphology=LandPlot.Morphology.OTHER, morphology_other="Διέρχεται αγωγός άρδευσης",
        usable_area_sqm=Decimal("2000"), estimated_cost=Decimal("140000"), estimated_plots_count=3,
        technical_suitability=LandPlot.SuitabilityDecision.CONDITIONAL,
    )
    UtilityService.objects.create(case=case, service_type=service_type("ΑΗΚ"), proximity="≈ 50 μ.")
    UtilityService.objects.create(case=case, service_type=service_type("Υδατοπρομήθεια"), proximity="Στο όριο του τεμαχίου 305")
    S = Consultation.Stage.SUITABILITY
    consultation(case, S, Consultation.Department.TKX, "Ιδιοκτησιακό καθεστώς τεμαχίων 305, 311",
                 "2026-05-04", "2026-06-04", "2026-05-30", "Το 305 διαχειρίζεται ο Κηδεμόνας Τ/Κ Περιουσιών.")
    consultation(case, S, Consultation.Department.TAY, "Μετατόπιση αγωγού άρδευσης στο τεμάχιο 311",
                 "2026-05-04", "2026-06-04")
    consultation(case, S, Consultation.Department.OTHER, "Ζώνη ασφαλείας Νεκρής Ζώνης",
                 "2026-05-04", "2026-07-04", other="Υπουργείο Άμυνας")
    MinistryDecisionRound.objects.create(
        case=case, letter_sent_date=d("2026-10-05"),
        recommendation=MinistryDecisionRound.Recommendation.POSITIVE,
        comments="Αναμένεται η απόφαση του ΥΠΕΣ.",
    )
    return case


def case_kakopetria() -> Case:
    """Αρχικό στάδιο: ο έλεγχος πληρότητας (Ενότητα 2) βρήκε ελλείψεις."""
    case = new_case(
        "ΚΑΚΟΠΕΤΡΙΑ",
        "2026-09-14",
        submitted_at=d("2026-09-08"),
        contact_email="kakopetria.community@example.com",
        priority_other="Ορεινή κοινότητα με φθίνοντα πληθυσμό",
        priority_documentation="Η Κοινότητα ζητά οικόπεδα για συγκράτηση νέων οικογενειών.",
    )
    completeness(
        case, "2026-09-28", NO,
        "Ο κατάλογος περιλαμβάνει 7 οικογένειες (απαιτούνται ≥ 10). Λείπει η απόφαση του Κοινοτικού Συμβουλίου.",
    )
    LandPlot.objects.create(
        case=case, parcel_number="58", sheet_plan="36/18", location="«Άγιος Νικόλαος»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("4100"),
        zone="Η1", inside_development_zone=YES, access=LandPlot.Access.PUBLIC_ROAD,
    )
    return case


def case_gourri() -> Case:
    """Απορρίφθηκε από το ΥΠΕΣ μετά από αρνητική τεχνική αξιολόγηση."""
    case = new_case(
        "ΓΟΥΡΡΗ",
        "2025-03-03",
        submitted_at=d("2025-02-24"),
        contact_email="gourri.community@example.com",
        priority_limited_private_land=True,
        state_land_remains_sufficient=YES,
        engineer_full_name="Μιχάλης Ζαχαρίου",
        technical_visit_date=d("2025-05-08"),
        access_technical_evaluation="Πρόσβαση μόνο από στενό χωματόδρομο με κλίση > 15%.",
    )
    completeness(case, "2025-03-17", YES)
    LandPlot.objects.create(
        case=case, parcel_number="141", sheet_plan="37/09", location="«Ράχη»",
        ownership_status=LandPlot.OwnershipStatus.STATE_LAND, area_sqm=Decimal("5300"), zone="Η1",
        inside_development_zone=YES, access=LandPlot.Access.OTHER, access_other="Χωματόδρομος",
        morphology=LandPlot.Morphology.STEEP, usable_area_sqm=Decimal("2100"),
        estimated_cost=Decimal("480000"), estimated_plots_count=3,
        technical_suitability=LandPlot.SuitabilityDecision.UNSUITABLE,
        suitability_decision=LandPlot.SuitabilityDecision.UNSUITABLE,
        suitability_justification="Έντονες υψομετρικές διαφορές· δυσανάλογο κόστος ανά οικόπεδο.",
    )
    MinistryDecisionRound.objects.create(
        case=case, letter_sent_date=d("2025-07-14"),
        recommendation=MinistryDecisionRound.Recommendation.NEGATIVE,
        ministry_response_date=d("2025-09-02"),
        ministry_decision=MinistryDecisionRound.MinistryDecision.REJECTED,
        comments="Το κόστος υποδομών (≈ 160.000 € ανά οικόπεδο) κρίθηκε ασύμφορο.",
    )
    return case


def case_alampra() -> Case:
    """Αδιάθετα οικόπεδα παλαιού διαχωρισμού (2009): μόνο Ενότητα 1 και 7.3."""
    case = new_case(
        "ΑΛΑΜΠΡΑ",
        "2026-06-01",
        case_type=Case.CaseType.UNALLOCATED_PLOTS,
        submitted_at=d("2026-05-25"),
        contact_email="alampra.dd@example.com",
        comments="Τέσσερα αδιάθετα οικόπεδα του στεγαστικού διαχωρισμού του 2009 (οδός Αγίου Ιωάννη).",
    )
    design_plots(
        case, "31/12", [612, 587, 640, 603],
        rate=55, first_parcel=902, title_from=27741, numbering=Numbering.TITLE_DEED,
    )
    finish(case, "2026-07-10")
    return case


def manual_plots(community_name, sheet_plan, specs, rate, comments=""):
    """Οικόπεδα που καταχωρίζονται χειροκίνητα (χωρίς αίτηση διαχωρισμού)."""
    plots = []
    for parcel, title, area, valued in specs:
        area = Decimal(area)
        plot = Plot(
            community=community(community_name),
            parcel_number=parcel,
            sheet_plan=sheet_plan,
            title_deed_number=title,
            final_area_sqm=area,
            has_separate_title=YES,
            valuation_amount=(area * Decimal(rate)).quantize(Decimal("1")) if valued else None,
            numbering_status=Numbering.TITLE_DEED,
            comments=comments if valued else "Εκκρεμεί η εκτίμηση αξίας από το ΤΚΧ.",
        )
        plot.save()
        plots.append(plot)
    return plots


# ─────────────────────────────────────────────────────────────────────────────
# Γνωστοποιήσεις (Ενότητα 9)
# ─────────────────────────────────────────────────────────────────────────────


def announcement(community_names, announced_on, months, published_on=None, comments=""):
    if isinstance(community_names, str):
        community_names = [community_names]
    cycles = []
    for name in community_names:
        comm = community(name)
        cycle = SubmissionCycle(
            announcement_date=d(announced_on), submission_months=months, comments=comments
        )
        cycle.save()
        cycle.plots.set(Plot.objects.available().filter(community=comm))
        if published_on:
            for method in SubmissionCyclePublication.FIXED_METHODS:
                SubmissionCyclePublication.objects.create(
                    submission_cycle=cycle, method=method, published_on=d(announced_on)
                )
            SubmissionCyclePublication.objects.create(
                submission_cycle=cycle,
                method=SubmissionCyclePublication.PublicationMethod.OTHER,
                published_on=d(announced_on),
                notes="Σελίδα της Κοινότητας στο Facebook",
            )
            cycle.published_at = moment(published_on, 9)
            cycle.save()
        cycles.append(cycle)
    return cycles[0] if len(cycles) == 1 else cycles


# ─────────────────────────────────────────────────────────────────────────────
# Άτομα και Αιτήσεις παραχώρησης οικοπέδου (Παράρτημα 3)
# ─────────────────────────────────────────────────────────────────────────────


def person(identity, first, last, born, birth_place, parents_place, birth_country="Κύπρος",
           parents_country="Κύπρος", document_type=""):
    return {
        "identity_number": identity,
        "first_name": first,
        "last_name": last,
        "date_of_birth": d(born),
        "birth_place": birth_place,
        "birth_country": birth_country,
        "parents_birth_place": parents_place,
        "parents_birth_country": parents_country,
        "document_type": document_type,
    }


def party(mobile, sin="", email="", refugee="", arc="", citizenship_other="", landline="",
          employee=False, self_employed=False, unemployed=False, disability=False, employer=""):
    return {
        "social_insurance_number": sin,
        "refugee_identity_number": refugee,
        "alien_registration_number": arc,
        "citizenship": ApplicationParty.Citizenship.OTHER if citizenship_other else ApplicationParty.Citizenship.CYPRIOT,
        "citizenship_other": citizenship_other,
        "mobile_phone": mobile,
        "landline_phone": landline,
        "email": email,
        "is_employee": employee,
        "is_self_employed": self_employed,
        "is_unemployed": unemployed,
        "has_disability": disability,
        "employer_details": employer,
    }


def child(first, last, born, status, sex, identity=""):
    return (first, last, born, status, sex, identity)


def income(member, kind, description, amount, child_index=None):
    return (member, kind, description, Decimal(amount), child_index)


# Persons registered without any application yet («Άτομα» registry only).
REGISTRY_ONLY_PERSONS = (
    person("1102937", "Ιωάννα", "Μιχαηλίδου", "1996-04-18", "Λευκωσία", "Κακοπετριά"),
    person("1088410", "Λευτέρης", "Αντωνίου", "1990-10-02", "Λεμεσός", "Γαλάτα"),
    person("1120558", "Θεοδώρα", "Πετρίδου", "1998-01-27", "Λευκωσία", "Δένεια"),
    person("1065273", "Αχιλλέας", "Κυπριανού", "1987-06-09", "Λάρνακα", "Αμμόχωστος"),
    person("FX4471209", "Ναταλία", "Ιβάνοβα", "1992-12-14", "Οδησσός", "Οδησσός",
           birth_country="Ουκρανία", parents_country="Ουκρανία", document_type="Διαβατήριο"),
)

ADDRESSES = {
    "ΑΚΑΚΙ": ("2722", "Ακάκι"),
    "ΑΣΤΡΟΜΕΡΙΤΗΣ": ("2725", "Αστρομερίτης"),
    "ΑΛΑΜΠΡΑ": ("2565", "Αλάμπρα"),
    "ΕΡΓΑΤΕΣ": ("2643", "Εργάτες"),
    "ΠΕΡΙΣΤΕΡΩΝΑ (ΛΕΥΚΩΣΙΑΣ)": ("2731", "Περιστερώνα"),
    "ΜΕΝΙΚΟ": ("2729", "Μένικο"),
    "ΚΑΜΠΙΑ": ("2647", "Κάμπια"),
    "Στρόβολος": ("2018", "Στρόβολος"),
}

D_ALL = ("D1", "D2", "D3", "D4", "D5")

APPLICATIONS = (
    # ── ΑΚΑΚΙ (γνωστοποίηση 15/07/2026 – 15/09/2026) ──────────────────────────
    {
        "scenario": "Αυτόχθονας · ζεύγος με 2 ανήλικα τέκνα · εντός ορίου εισοδήματος",
        "community": "ΑΚΑΚΙ", "submitted": "2026-07-28", "sworn": "2026-07-24",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Αρχιεπισκόπου Μακαρίου Γ'", "45", ""),
        "applicant": (person("1056734", "Ανδρέας", "Χριστοδούλου", "1991-03-14", "Λευκωσία", "Ακάκι"),
                      party("99 482615", "2318745", "a.christodoulou@example.com", employee=True,
                            employer="Λογιστικό Γραφείο Σ. Πολυκάρπου Λτδ, Λευκωσία")),
        "spouse": (person("1078921", "Μαρία", "Χριστοδούλου", "1993-07-02", "Λεμεσός", "Λεμεσός"),
                   party("97 615280", "2410563", employee=True, employer="Υπουργείο Παιδείας — Δημοτικό Ακακίου")),
        "children": [child("Γιώργος", "Χριστοδούλου", "2019-05-10", Child.MINOR, "M"),
                     child("Ελένη", "Χριστοδούλου", "2022-11-23", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός λογιστή (συμπ. 13ου)", "26400"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός εκπαιδευτικού", "24800")],
    },
    {
        "scenario": "Εκτοπισθείς · πολύτεκνη (φοιτήτρια, εθνοφρουρός, 2 ανήλικα)",
        "community": "ΑΚΑΚΙ", "submitted": "2026-08-20", "sworn": "2026-08-18",
        "category": ResidenceCategory.DISPLACED, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Κερύνειας", "17", ""),
        "applicant": (person("0987345", "Κυριάκος", "Παπαδόπουλος", "1982-09-30", "Λευκωσία", "Κερύνεια"),
                      party("99 731004", "1987234", "k.papadopoulos@example.com", refugee="ΠΤ 0458712",
                            employee=True, employer="Αρχή Ηλεκτρισμού Κύπρου — Τεχνικός")),
        "spouse": (person("1004512", "Σωτηρούλα", "Παπαδοπούλου", "1984-02-11", "Λάρνακα", "Αμμόχωστος"),
                   party("96 228471", "2051897", refugee="ΠΤ 0461290", self_employed=True,
                         employer="Κομμωτήριο «Σωτηρούλα», Ακάκι")),
        "children": [child("Χριστίνα", "Παπαδοπούλου", "2004-10-05", Child.STUDENT, "F", "1150732"),
                     child("Ανδρέας", "Παπαδόπουλος", "2006-01-15", Child.NATIONAL_GUARD, "M", "1163390"),
                     child("Μιχάλης", "Παπαδόπουλος", "2012-04-20", Child.MINOR, "M"),
                     child("Νικόλας", "Παπαδόπουλος", "2015-08-08", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός ΑΗΚ", "31500"),
                    income(Member.SPOUSE, Work.SELF_EMPLOYED, "Κέρδη κομμωτηρίου", "14200"),
                    income(Member.CHILD, Work.OTHER_SOURCE, "Φοιτητική χορηγία", "2400", child_index=0)],
    },
    {
        "scenario": "Απόδημος Εσωτερικού (καταγωγή από πατέρα) · ζεύγος χωρίς τέκνα",
        "community": "ΑΚΑΚΙ", "submitted": "2026-08-05", "sworn": "2026-08-03",
        "category": ResidenceCategory.INTERNAL_EMIGRANT, "family": Family.COUPLE_WITHOUT_CHILDREN,
        "address": ("Αγίου Παύλου", "8", "203"), "residence": "Στρόβολος",
        "origin": "Ο πατέρας, Ιωάννης Ιωάννου, κατάγεται από το Ακάκι.",
        "previous_address": "Αγίου Γεωργίου 12, Ακάκι (1994–2015)",
        "applicant": (person("1069920", "Νεόφυτος", "Ιωάννου", "1989-11-21", "Λευκωσία", "Ακάκι"),
                      party("99 905117", "2287109", "n.ioannou@example.com", employee=True,
                            employer="Τράπεζα Κύπρου — Λειτουργός")),
        "spouse": (person("1091187", "Άννα", "Ιωάννου", "1992-05-30", "Πάφος", "Πάφος"),
                   party("97 330528", "2395120", employee=True, employer="Ιδιωτική Κλινική, Λευκωσία — Νοσηλεύτρια")),
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "24000"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός νοσηλεύτριας", "18500")],
    },
    {
        "scenario": "Επαναπατρισθείς από Ηνωμένο Βασίλειο · σύζυγος Βρετανίδα · 1 τέκνο",
        "community": "ΑΚΑΚΙ", "submitted": "2026-08-18", "sworn": "2026-08-14",
        "category": ResidenceCategory.REPATRIATED, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Ελευθερίας", "23", ""),
        "notes": "Διέμενε στο Λονδίνο από 09/2008 έως 08/2021 για εργασία (13 έτη)· διαμένει μόνιμα στο Ακάκι από 09/2021.",
        "applicant": (person("1031876", "Χρίστος", "Γεωργίου", "1986-12-03", "Λονδίνο", "Ακάκι",
                             birth_country="Ηνωμένο Βασίλειο"),
                      party("99 208733", "2199845", "c.georgiou@example.com", employee=True,
                            employer="Εταιρεία λογισμικού, Λευκωσία — Μηχανικός")),
        "spouse": (person("548812937", "Emily", "Georgiou", "1988-04-22", "Μάντσεστερ", "Μάντσεστερ",
                          birth_country="Ηνωμένο Βασίλειο", parents_country="Ηνωμένο Βασίλειο",
                          document_type="Διαβατήριο"),
                   party("96 551208", "2477310", arc="ARC 1187654", citizenship_other="Βρετανική",
                         employee=True, employer="Ιδιωτικό σχολείο — Καθηγήτρια Αγγλικών (μερική απασχόληση)")),
        "children": [child("Λουκάς", "Γεωργίου", "2020-02-14", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "33000"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός μερικής απασχόλησης", "11500")],
    },
    {
        "scenario": "Κάτοικος Γειτονικής Κοινότητας · μονογονεϊκή (διαζευγμένη) · 2η προτίμηση",
        "community": "ΑΚΑΚΙ", "submitted": "2026-08-12", "sworn": "2026-08-07", "key": "stella",
        "preference": 2,
        "category": ResidenceCategory.NEIGHBOURING, "family": Family.SINGLE_PARENT,
        "single": SingleParent.DIVORCED, "residence": "ΠΕΡΙΣΤΕΡΩΝΑ (ΛΕΥΚΩΣΙΑΣ)",
        "address": ("Ηρώων", "4", ""),
    },
    {
        "scenario": "Αυτόχθονας · ζεύγος χωρίς τέκνα · υπέρβαση ορίου εισοδήματος (Δεν πληροί)",
        "community": "ΑΚΑΚΙ", "submitted": "2026-09-02", "sworn": "2026-08-31",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITHOUT_CHILDREN,
        "address": ("Γρηγόρη Αυξεντίου", "31", ""),
        "applicant": (person("1072215", "Μάριος", "Νικολάου", "1990-01-19", "Λευκωσία", "Ακάκι"),
                      party("99 117742", "2301458", "m.nikolaou@example.com", employee=True,
                            employer="Ελεγκτικός οίκος, Λευκωσία")),
        "spouse": (person("1089734", "Δέσποινα", "Νικολάου", "1992-08-06", "Λευκωσία", "Λευκωσία"),
                   party("97 820311", "2389002", employee=True, employer="Δημόσια υπηρεσία — Λειτουργός")),
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός ελεγκτή", "29500"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός δημόσιας υπαλλήλου", "23800")],
    },
    {
        "scenario": "Αυτόχθονας · ζεύγος με 1 τέκνο · και οι δύο άνω των 45 (Δεν πληροί)",
        "community": "ΑΚΑΚΙ", "submitted": "2026-08-25", "sworn": "2026-08-21",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Αγίας Μαρίνας", "9", ""),
        "applicant": (person("0812456", "Παναγιώτης", "Σάββα", "1978-02-10", "Ακάκι", "Ακάκι"),
                      party("99 640218", "1702334", "p.savva@example.com", self_employed=True,
                            employer="Γεωργοκτηνοτροφική μονάδα, Ακάκι")),
        "spouse": (person("0834190", "Ροδούλα", "Σάββα", "1979-06-30", "Μένικο", "Μένικο"),
                   party("96 412097", "1734561", unemployed=True)),
        "children": [child("Κωνσταντίνος", "Σάββα", "2011-09-17", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.SELF_EMPLOYED, "Κέρδη κτηνοτροφικής μονάδας", "27300")],
    },
    {
        "scenario": "Κάτοικος Γειτονικής Κοινότητας · κανένας Κύπριος πολίτης (Δεν πληροί)",
        "community": "ΑΚΑΚΙ", "submitted": "2026-09-10", "sworn": "2026-09-08",
        "category": ResidenceCategory.NEIGHBOURING, "family": Family.COUPLE_WITH_CHILDREN,
        "residence": "ΜΕΝΙΚΟ", "address": ("Αγίων Κυπριανού και Ιουστίνης", "6", ""),
        "applicant": (person("AK3390176", "Δημήτρης", "Παπαδάκης", "1987-03-25", "Θεσσαλονίκη", "Θεσσαλονίκη",
                             birth_country="Ελλάδα", parents_country="Ελλάδα", document_type="Δελτίο ταυτότητας ΕΕ"),
                      party("99 873320", "2266781", "d.papadakis@example.com", arc="ARC 0995512",
                            citizenship_other="Ελληνική", employee=True, employer="Ιδιωτική εταιρεία logistics")),
        "spouse": (person("BG7741023", "Ιβελίνα", "Παπαδάκη", "1990-10-12", "Πλόβντιβ", "Πλόβντιβ",
                          birth_country="Βουλγαρία", parents_country="Βουλγαρία", document_type="Διαβατήριο"),
                   party("96 304417", "2410998", arc="ARC 1033871", citizenship_other="Βουλγαρική",
                         employee=True, employer="Υπεραγορά, Λευκωσία")),
        "children": [child("Αλέξανδρος", "Παπαδάκης", "2017-06-01", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "21500"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "14300")],
    },
    # ── ΑΣΤΡΟΜΕΡΙΤΗΣ (ίδια γνωστοποίηση) ─────────────────────────────────────
    {
        "scenario": "Κάτοικος Γειτονικής Κοινότητας · μονογονεϊκή (διαζευγμένη) · 1η προτίμηση",
        "community": "ΑΣΤΡΟΜΕΡΙΤΗΣ", "submitted": "2026-08-10", "sworn": "2026-08-07", "key": "stella",
        "preference": 1,
        "category": ResidenceCategory.NEIGHBOURING, "family": Family.SINGLE_PARENT,
        "single": SingleParent.DIVORCED, "residence": "ΠΕΡΙΣΤΕΡΩΝΑ (ΛΕΥΚΩΣΙΑΣ)",
        "address": ("Ηρώων", "4", ""),
    },
    {
        "scenario": "Αυτόχθονας · μονογονεϊκή (χήρα) · ενήλικο τέκνο με αναπηρία",
        "community": "ΑΣΤΡΟΜΕΡΙΤΗΣ", "submitted": "2026-07-30", "sworn": "2026-07-27",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.SINGLE_PARENT,
        "single": SingleParent.WIDOWED, "address": ("Αγίου Ευφημιανού", "14", ""),
        "applicant": (person("1009876", "Γεωργία", "Χαραλάμπους", "1983-05-17", "Αστρομερίτης", "Αστρομερίτης"),
                      party("99 556012", "2077541", "g.charalambous@example.com", employee=True,
                            employer="Κοινοτικό Συμβούλιο Αστρομερίτη — Γραμματειακή λειτουργός")),
        "children": [child("Αντρέας", "Χαραλάμπους", "2002-03-09", Child.ADULT_DISABILITY, "M", "1129987"),
                     child("Μαρίνα", "Χαραλάμπους", "2013-12-01", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "19200"),
                    income(Member.APPLICANT, Work.OTHER_SOURCE, "Σύνταξη χηρείας", "9600")],
    },
    {
        "scenario": "Αυτόχθονας · ζεύγος με 1 τέκνο · έχει εγγεγραμμένη κατοικία (Δεν πληροί)",
        "community": "ΑΣΤΡΟΜΕΡΙΤΗΣ", "submitted": "2026-08-27", "sworn": "2026-08-25",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Παναγίας", "2", ""),
        "dwelling": (True, "Διαμέρισμα στην Έγκωμη (κληρονομιά, 2023), στο όνομα του αιτητή."),
        "applicant": (person("1044518", "Ευάγγελος", "Λοΐζου", "1988-08-28", "Αστρομερίτης", "Αστρομερίτης"),
                      party("99 390476", "2154306", "e.loizou@example.com", employee=True,
                            employer="Συνεργατικό Ταμιευτήριο — Ταμίας")),
        "spouse": (person("1061139", "Χαρούλα", "Λοΐζου", "1990-02-15", "Περιστερώνα", "Περιστερώνα"),
                   party("97 118850", "2236479", employee=True, employer="Φαρμακείο, Περιστερώνα")),
        "children": [child("Παναγιώτα", "Λοΐζου", "2018-04-03", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "20500"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "15900")],
    },
    {
        "scenario": "Εκτοπισθείς · ζεύγος με 2 τέκνα · ελλιπής (χωρίς υπογραφή συζύγου, λείπουν δικαιολογητικά)",
        "community": "ΑΣΤΡΟΜΕΡΙΤΗΣ", "submitted": "2026-09-14", "sworn": "2026-09-11",
        "category": ResidenceCategory.DISPLACED, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Μόρφου", "27", ""), "signed": (True, False), "sworn_by": (True, False),
        "missing": ("B11", *D_ALL),
        "document_notes": {"D1": "Αναμένεται από το DLS Portal", "B11": "Λείπει το πιστοποιητικό του μικρότερου τέκνου"},
        "applicant": (person("1012874", "Σάββας", "Κωνσταντίνου", "1985-10-06", "Αστρομερίτης", "Μόρφου"),
                      party("99 724915", "2098731", "s.konstantinou@example.com", refugee="ΠΤ 0517733",
                            employee=True, employer="Ιδιωτικό συνεργείο αυτοκινήτων")),
        "spouse": (person("1039901", "Αθηνά", "Κωνσταντίνου", "1987-07-19", "Λευκωσία", "Λευκωσία"),
                   party("96 845530", "2142270", employee=True, employer="Υπεραγορά, Αστρομερίτης")),
        "children": [child("Μαρία", "Κωνσταντίνου", "2014-01-22", Child.MINOR, "F"),
                     child("Ιωάννης", "Κωνσταντίνου", "2019-09-30", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "22800"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "13700")],
    },
    {
        "scenario": "Αυτόχθονας · μονογονεϊκή (άγαμη μητέρα) · αυτοτελώς εργαζόμενη",
        "community": "ΑΣΤΡΟΜΕΡΙΤΗΣ", "submitted": "2026-08-31", "sworn": "2026-08-28",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.SINGLE_PARENT,
        "single": SingleParent.UNMARRIED, "address": ("Ανεξαρτησίας", "51", "1"),
        "applicant": (person("1117346", "Ραφαέλα", "Ευθυμίου", "1995-06-12", "Αστρομερίτης", "Αστρομερίτης"),
                      party("97 223681", "2560874", "r.efthymiou@example.com", self_employed=True,
                            employer="Ελεύθερη επαγγελματίας — Γραφίστρια")),
        "children": [child("Δανάη", "Ευθυμίου", "2021-03-08", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.SELF_EMPLOYED, "Κέρδη ελεύθερου επαγγέλματος", "21000")],
    },
    {
        "scenario": "Αυτόχθονας με αναπηρία · σύζυγος Ρωσίδα, άνεργη · 3 ανήλικα τέκνα",
        "community": "ΑΣΤΡΟΜΕΡΙΤΗΣ", "submitted": "2026-09-08", "sworn": "2026-09-04",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Αγίας Παρασκευής", "19", ""),
        "applicant": (person("1027765", "Στέλιος", "Αγαθοκλέους", "1984-11-29", "Αστρομερίτης", "Αστρομερίτης"),
                      party("99 461738", "2113054", "s.agathokleous@example.com", employee=True, disability=True,
                            employer="Κυβερνητικό Τμήμα — Βοηθός Γραφέας")),
        "spouse": (person("754419832", "Όλγα", "Αγαθοκλέους", "1989-03-03", "Κρασνοντάρ", "Κρασνοντάρ",
                          birth_country="Ρωσία", parents_country="Ρωσία", document_type="Διαβατήριο"),
                   party("96 930027", arc="ARC 0877215", citizenship_other="Ρωσική", unemployed=True)),
        "children": [child("Αναστασία", "Αγαθοκλέους", "2012-07-14", Child.MINOR, "F"),
                     child("Μάρκος", "Αγαθοκλέους", "2015-02-02", Child.MINOR, "M"),
                     child("Σοφία", "Αγαθοκλέους", "2019-10-26", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "22000"),
                    income(Member.APPLICANT, Work.OTHER_SOURCE, "Επίδομα αναπηρίας", "4200")],
    },
    # ── ΑΛΑΜΠΡΑ (γνωστοποίηση 21/09/2026 – 21/11/2026, σε εξέλιξη) ────────────
    {
        "scenario": "Αυτόχθονας · ζεύγος με 3 τέκνα · προηγούμενη κρατική στεγαστική ενίσχυση (Δεν πληροί)",
        "community": "ΑΛΑΜΠΡΑ", "submitted": "2026-09-29", "sworn": "2026-09-25",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Αγίου Ιωάννη", "36", ""),
        "aid": (True, "Στεγαστική χορηγία του Σχεδίου Στεγαστικής Ανακούφισης για αγορά διαμερίσματος (2016)."),
        "applicant": (person("1018839", "Χαράλαμπος", "Ματθαίου", "1983-04-05", "Αλάμπρα", "Αλάμπρα"),
                      party("99 287450", "2081997", "ch.matthaiou@example.com", self_employed=True,
                            employer="Ηλεκτρολογικές εργασίες — ιδιοκτήτης")),
        "spouse": (person("1036620", "Πόπη", "Ματθαίου", "1986-12-20", "Λύμπια", "Λύμπια"),
                   party("97 640991", "2140357", unemployed=True)),
        "children": [child("Ανδρέας", "Ματθαίου", "2011-05-05", Child.MINOR, "M"),
                     child("Ελένη", "Ματθαίου", "2014-08-19", Child.MINOR, "F"),
                     child("Μαρία", "Ματθαίου", "2018-01-30", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.SELF_EMPLOYED, "Κέρδη ηλεκτρολογικών εργασιών", "34600")],
    },
    {
        "scenario": "Εκτοπισθείς · σύζυγος Ελληνίδα · αποξένωση οικοπέδου εντός 3 ετών (Δεν πληροί)",
        "community": "ΑΛΑΜΠΡΑ", "submitted": "2026-10-06", "sworn": "2026-10-02",
        "category": ResidenceCategory.DISPLACED, "family": Family.COUPLE_WITHOUT_CHILDREN,
        "address": ("Αμμοχώστου", "3", ""),
        "alienated": (True, "Μεταβίβαση οικοπέδου στην Αλάμπρα (τεμ. 455) στην αδελφή του αιτητή, 05/2024."),
        "applicant": (person("1052207", "Ορέστης", "Φιλίππου", "1990-09-09", "Λάρνακα", "Αμμόχωστος"),
                      party("99 018634", "2290415", "o.filippou@example.com", refugee="ΠΤ 0603318",
                            employee=True, employer="Αστυνομία Κύπρου — Αστυφύλακας")),
        "spouse": (person("AN8820461", "Κατερίνα", "Φιλίππου", "1993-03-11", "Αθήνα", "Πάτρα",
                          birth_country="Ελλάδα", parents_country="Ελλάδα", document_type="Δελτίο ταυτότητας ΕΕ"),
                   party("96 772109", "2502318", arc="ARC 1201764", citizenship_other="Ελληνική",
                         employee=True, employer="Ιδιωτικό φροντιστήριο — Φιλόλογος")),
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "25300"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "12800")],
    },
    {
        "scenario": "Αυτόχθονας · ζεύγος με 2 τέκνα · λείπει πιστοποιητικό ΤΚΧ, χαρακτηρίστηκε ολοκληρωμένη",
        "community": "ΑΛΑΜΠΡΑ", "submitted": "2026-10-13", "sworn": "2026-10-09",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Γιάννου Κρανιδιώτη", "12", ""), "missing": ("D3",),
        "override": "Το πιστοποιητικό ΤΚΧ για τους γονείς εκκρεμεί λόγω καθυστέρησης του DLS Portal — υποβλήθηκε αίτηση 2026/45871.",
        "document_notes": {"D3": "Εκκρεμεί από ΤΚΧ (αίτηση 2026/45871)"},
        "applicant": (person("1080016", "Παύλος", "Χαραλάμπους", "1992-02-26", "Αλάμπρα", "Αλάμπρα"),
                      party("99 351862", "2370088", "p.charalambous@example.com", employee=True,
                            employer="Cyta — Τεχνικός δικτύων")),
        "spouse": (person("1094475", "Στέλλα", "Χαραλάμπους", "1994-09-14", "Λευκωσία", "Λευκωσία"),
                   party("97 492113", "2451796", employee=True, employer="Νοσοκομείο Λευκωσίας — Νοσηλεύτρια")),
        "children": [child("Μιχαέλα", "Χαραλάμπους", "2020-12-12", Child.MINOR, "F"),
                     child("Ηλίας", "Χαραλάμπους", "2024-04-04", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "23700"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "22100")],
    },
    {
        "scenario": "Αυτόχθονας · φοιτητής 26 ετών δεν λογίζεται τέκνο · εισόδημα τέκνου",
        "community": "ΑΛΑΜΠΡΑ", "submitted": "2026-10-02", "sworn": "2026-09-30",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Ηλία Παπακυριακού", "7", ""),
        "applicant": (person("0946671", "Νίκος", "Στυλιανού", "1981-11-20", "Αλάμπρα", "Αλάμπρα"),
                      party("99 664207", "1895512", "n.stylianou@example.com", employee=True,
                            employer="Λατομείο, Μιτσερό — Χειριστής μηχανημάτων")),
        "spouse": (person("0968803", "Ελένη", "Στυλιανού", "1983-06-08", "Νήσου", "Νήσου"),
                   party("96 158874", "1929960", employee=True, employer="Σχολική καντίνα — μερική απασχόληση")),
        "children": [child("Γιώργος", "Στυλιανού", "2000-05-12", Child.STUDENT, "M", "1098812"),
                     child("Άντρια", "Στυλιανού", "2009-03-01", Child.MINOR, "F", "1189034")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "30000"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός μερικής απασχόλησης", "12000"),
                    income(Member.CHILD, Work.EMPLOYEE, "Μερική απασχόληση φοιτητή", "5200", child_index=0)],
    },
    # ── ΕΡΓΑΤΕΣ (οικόπεδα χωρίς διαχωρισμό, ίδια γνωστοποίηση με Αλάμπρα) ───
    {
        "scenario": "Αυτόχθονας · ζεύγος χωρίς τέκνα · δεν απάντησε για οικόπεδο (Εκκρεμεί)",
        "community": "ΕΡΓΑΤΕΣ", "submitted": "2026-10-20", "sworn": "2026-10-16",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITHOUT_CHILDREN,
        "address": ("Αγίου Μάμα", "22", ""), "land": (None, ""), "missing": ("D4", "D5"),
        "applicant": (person("1098230", "Αντώνης", "Πέτρου", "1994-07-07", "Εργάτες", "Εργάτες"),
                      party("99 803146", "2470613", "a.petrou@example.com", employee=True,
                            employer="Ξενοδοχείο, Λευκωσία — Μάγειρας")),
        "spouse": (person("1110094", "Κυριακή", "Πέτρου", "1996-11-02", "Πολιτικό", "Πολιτικό"),
                   party("97 260585", "2533187", employee=True, employer="Παιδοκομικός σταθμός, Εργάτες")),
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "19800"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "14400")],
    },
    {
        "scenario": "Αυτόχθονας · μονογονεϊκή «Άλλο» (σύζυγος στις φυλακές) · 2 τέκνα",
        "community": "ΕΡΓΑΤΕΣ", "submitted": "2026-10-08", "sworn": "2026-10-05",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.SINGLE_PARENT,
        "single": SingleParent.OTHER,
        "single_other": "Ο σύζυγος εκτίει ποινή φυλάκισης στις Κεντρικές Φυλακές μέχρι το 2031.",
        "address": ("Αρχαγγέλου Μιχαήλ", "5", ""), "missing": ("B7", "B8"),
        "applicant": (person("1047782", "Μαρίνα", "Αβραάμ", "1989-04-30", "Εργάτες", "Εργάτες"),
                      party("96 517390", "2260944", "m.avraam@example.com", employee=True,
                            employer="Δήμος Λευκωσίας — Καθαρίστρια")),
        "children": [child("Χρυσάνθη", "Αβραάμ", "2012-10-10", Child.MINOR, "F"),
                     child("Λοΐζος", "Αβραάμ", "2016-06-21", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "15600"),
                    income(Member.APPLICANT, Work.OTHER_SOURCE, "Επίδομα μονογονεϊκής οικογένειας", "2900")],
    },
    {
        "scenario": "Αυτόχθονας · πολύτεκνη με 5 τέκνα (εθνοφρουρός και 4 ανήλικα)",
        "community": "ΕΡΓΑΤΕΣ", "submitted": "2026-10-10", "sworn": "2026-10-07",
        "category": ResidenceCategory.AUTOCHTHON, "family": Family.COUPLE_WITH_CHILDREN,
        "address": ("Πολιτικού", "40", ""),
        "applicant": (person("0957714", "Γιαννάκης", "Ευαγγέλου", "1982-01-08", "Εργάτες", "Εργάτες"),
                      party("99 930558", "1911207", "g.evangelou@example.com", employee=True,
                            employer="Υδατοπρομήθεια Λευκωσίας — Υδραυλικός")),
        "spouse": (person("1001348", "Νάσια", "Ευαγγέλου", "1985-05-25", "Κάμπια", "Κάμπια"),
                   party("97 715422", "2040781", employee=True, employer="Δημόσιο Σχολείο — Σχολική βοηθός")),
        "children": [child("Φίλιππος", "Ευαγγέλου", "2007-02-11", Child.NATIONAL_GUARD, "M", "1171225"),
                     child("Ειρήνη", "Ευαγγέλου", "2010-09-03", Child.MINOR, "F"),
                     child("Θεόδωρος", "Ευαγγέλου", "2013-04-17", Child.MINOR, "M"),
                     child("Άννα", "Ευαγγέλου", "2016-12-29", Child.MINOR, "F"),
                     child("Πέτρος", "Ευαγγέλου", "2020-07-08", Child.MINOR, "M")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "38500"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "22000")],
    },
    {
        "scenario": "Κάτοικος Γειτονικής Κοινότητας (Κάμπια) · ζεύγος χωρίς τέκνα",
        "community": "ΕΡΓΑΤΕΣ", "submitted": "2026-10-23", "sworn": "2026-10-21",
        "category": ResidenceCategory.NEIGHBOURING, "family": Family.COUPLE_WITHOUT_CHILDREN,
        "residence": "ΚΑΜΠΙΑ", "address": ("Αγίου Γεωργίου", "15", ""),
        "applicant": (person("1105529", "Κωνσταντίνος", "Μαύρου", "1997-08-19", "Λευκωσία", "Κάμπια"),
                      party("99 146280", "2588402", "k.mavrou@example.com", employee=True,
                            employer="Εταιρεία τηλεπικοινωνιών — Τεχνικός")),
        "spouse": (person("1113861", "Δήμητρα", "Μαύρου", "1998-02-05", "Λεμεσός", "Λεμεσός"),
                   party("96 404723", "2601119", employee=True, employer="Λογιστικό γραφείο — Βοηθός λογιστή")),
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "21000"),
                    income(Member.SPOUSE, Work.EMPLOYEE, "Μισθός", "19500")],
    },
)

# The same single parent applies in two communities (preference order 1 and 2).
SHARED_APPLICANTS = {
    "stella": {
        "applicant": (person("1058863", "Στέλλα", "Κωνσταντίνου", "1988-09-23", "Περιστερώνα", "Περιστερώνα"),
                      party("99 377921", "2203587", "stella.k@example.com", employee=True,
                            employer="Ιατρείο, Περιστερώνα — Γραμματέας")),
        "children": [child("Ραφαήλ", "Κωνσταντίνου", "2014-02-28", Child.MINOR, "M"),
                     child("Αλεξία", "Κωνσταντίνου", "2017-11-15", Child.MINOR, "F")],
        "incomes": [income(Member.APPLICANT, Work.EMPLOYEE, "Μισθός", "27800"),
                    income(Member.APPLICANT, Work.OTHER_SOURCE, "Διατροφή τέκνων (διάταγμα Οικογενειακού Δικαστηρίου)", "4800")],
    },
}


def get_person(data: dict) -> Person:
    found = Person.objects.filter(identity_number=data["identity_number"]).first()
    if found:
        return found
    created = Person(**data)
    created.save()
    return created


def create_application(spec: dict) -> PlotApplication:
    spec = {**SHARED_APPLICANTS.get(spec.get("key"), {}), **spec}
    target = community(spec["community"])
    category = spec["category"]
    street, number, apartment = spec["address"]
    residence = spec.get("residence") or target.name
    postal_code, town = ADDRESSES.get(residence, ADDRESSES.get(target.name))
    is_couple = spec["family"] in PlotApplication.COUPLE_STATUSES

    applicant_data, applicant_party = spec["applicant"]
    spouse_data, spouse_party = spec.get("spouse") or (None, None)
    applicant = get_person(applicant_data)
    spouse = get_person(spouse_data) if is_couple and spouse_data else None

    dwelling, dwelling_details = spec.get("dwelling", (False, ""))
    land, land_details = spec.get("land", (False, ""))
    alienated, alienated_details = spec.get("alienated", (False, ""))
    aid, aid_details = spec.get("aid", (False, ""))
    applicant_signed, spouse_signed = spec.get("signed", (True, True))
    sworn_applicant, sworn_spouse = spec.get("sworn_by", (True, True))
    persons = [p for p in (applicant, spouse) if p]
    highest_order = PlotApplication.objects.filter(
        Q(applicant__in=persons) | Q(spouse__in=persons)
    ).aggregate(value=Max("preference_order"))["value"] or 0

    application = PlotApplication(
        community=target,
        submitted_on=d(spec["submitted"]),
        applicant=applicant,
        spouse=spouse,
        email=applicant_party["email"],
        correspondence_street=street,
        correspondence_number=number,
        correspondence_apartment=apartment,
        correspondence_community=town,
        correspondence_postal_code=postal_code,
        correspondence_district="Λευκωσία",
        residence_category=category,
        residence_street=street,
        residence_number=number,
        residence_apartment=apartment,
        residence_postal_code=postal_code,
        residence_community=residence,
        resides_in_controlled_areas=spec.get("controlled_areas", True),
        origin_parent_description=spec.get("origin", ""),
        previous_residence_address=spec.get("previous_address", ""),
        residence_notes=spec.get("notes", ""),
        family_status=spec["family"],
        single_parent_status=spec.get("single", ""),
        single_parent_other=spec.get("single_other", ""),
        has_dwelling=dwelling,
        has_dwelling_details=dwelling_details,
        has_residential_land=land,
        has_residential_land_details=land_details,
        has_alienated_property=alienated,
        has_alienated_property_details=alienated_details,
        previous_housing_aid=aid,
        previous_housing_aid_details=aid_details,
        preference_order=spec.get("preference") or highest_order + 1,
        applicant_signed=applicant_signed,
        spouse_signed=spouse_signed and is_couple,
        sworn_declaration_date=d(spec["sworn"]),
        sworn_court="Λευκωσίας",
        sworn_by_applicant=sworn_applicant,
        sworn_by_spouse=sworn_spouse and is_couple,
        document_notes=spec.get("document_notes", {}),
        documents_complete_override=bool(spec.get("override")),
        documents_complete_reason=spec.get("override", ""),
    )
    save_with_new_protocol_number(application)

    ApplicationParty.objects.create(application=application, role=ApplicationParty.Role.APPLICANT, **applicant_party)
    if spouse:
        ApplicationParty.objects.create(application=application, role=ApplicationParty.Role.SPOUSE, **spouse_party)

    children = []
    for first, last, born, status, sex, identity in spec.get("children", []):
        children.append(ApplicationChild.objects.create(
            application=application, first_name=first, last_name=last, date_of_birth=d(born),
            status=status, sex=sex, identity_number=identity,
        ))
    for member, kind, description, amount, child_index in spec.get("incomes", []):
        IncomeDeclaration.objects.create(
            application=application, member=member, employment_type=kind, description=description,
            gross_annual_income=amount,
            child=children[child_index] if child_index is not None else None,
        )

    applicable = applicable_documents(application, parameter("plotApp.largeFamilyChildren"))
    application.attached_documents = sorted(applicable - set(spec.get("missing", ())))
    apply_evaluation(application)
    return application


class Command(BaseCommand):
    help = (
        "Διαγράφει αιτήσεις διαχωρισμού, οικόπεδα, γνωστοποιήσεις, αιτήσεις παραχώρησης και άτομα "
        "και δημιουργεί ρεαλιστικά δεδομένα δοκιμών."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Χωρίς ερώτηση επιβεβαίωσης.")

    def handle(self, *args, **options):
        if not options["yes"]:
            answer = input("Θα διαγραφούν όλα τα επιχειρησιακά δεδομένα. Συνέχεια; [y/N] ")
            if answer.strip().lower() not in ("y", "yes", "ν", "ναι"):
                raise CommandError("Ακυρώθηκε.")

        with transaction.atomic():
            for label, count in wipe():
                self.stdout.write(f"Διαγράφηκαν {count:>4} — {label}")

            cases = [
                case_akaki(), case_astromeritis(), case_agioi_trimithias(), case_deneia(),
                case_kakopetria(), case_gourri(), case_alampra(),
            ]
            manual_plots("ΕΡΓΑΤΕΣ", "30/27", [
                ("611", "33102", 585, True), ("612", "33103", 602, True), ("613", "33104", 574, True),
                ("618", "33109", 630, True), ("619", "33110", 548, True),
            ], rate=80, comments="Κρατικά οικόπεδα παλαιού διαχωρισμού (1998), καταχωρίστηκαν χειροκίνητα.")
            manual_plots("ΚΟΚΚΙΝΟΤΡΙΜΙΘΙΑ", "29/38", [
                ("1442", "51870", 610, True), ("1443", "51871", 596, True), ("1447", "51875", 655, True),
            ], rate=90, comments="Οικόπεδα που επιστράφηκαν μετά από ακύρωση παραχώρησης.")
            manual_plots("ΠΕΡΑ ΧΩΡΙΟ", "39/04", [
                ("377", "19044", 640, True), ("378", "19045", 618, False),
            ], rate=95, comments="Κρατικό οικόπεδο εντός οικιστικής ζώνης.")

            announcement(["ΑΚΑΚΙ", "ΑΣΤΡΟΜΕΡΙΤΗΣ"], "2026-07-15", 2, published_on="2026-07-15",
                         comments="Πρώτη γνωστοποίηση για τα οικόπεδα των διαχωρισμών Ακακίου και Αστρομερίτη.")
            announcement(["ΑΛΑΜΠΡΑ", "ΕΡΓΑΤΕΣ"], "2026-09-21", 2, published_on="2026-09-21")
            announcement(["ΚΟΚΚΙΝΟΤΡΙΜΙΘΙΑ", "ΠΕΡΑ ΧΩΡΙΟ"], "2026-11-02", 2,
                         comments="Προσχέδιο — αναμένεται η εκτίμηση του δεύτερου οικοπέδου του Πέρα Χωριού.")

            for data in REGISTRY_ONLY_PERSONS:
                get_person(data)
            applications = [create_application(spec) for spec in APPLICATIONS]

        self.stdout.write("")
        for case in cases:
            self.stdout.write(
                f"{case.case_number:<16} {case.community.name:<18} {case.get_case_type_display():<24} "
                f"οικόπεδα: {case.plots.count()}"
            )
        self.stdout.write(f"Χειροκίνητα οικόπεδα: {Plot.objects.filter(source_case__isnull=True).count()}")
        self.stdout.write(f"Οικόπεδα συνολικά: {Plot.objects.count()} (διαθέσιμα: {Plot.objects.available().count()})")
        self.stdout.write(f"Γνωστοποιήσεις: {SubmissionCycle.objects.count()}")
        self.stdout.write(f"Άτομα: {Person.objects.count()}")
        self.stdout.write("")
        for application, spec in zip(applications, APPLICATIONS):
            self.stdout.write(
                f"{application.protocol_number:<13} {application.get_completeness_result_display():<9} "
                f"{application.get_eligibility_result_display():<18} {application.get_residence_category_display():<45} "
                f"| {spec['scenario']}"
            )
        self.stdout.write(self.style.SUCCESS("Τα δεδομένα δοκιμών δημιουργήθηκαν."))
