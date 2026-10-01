from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cases.forms import (
    AnnouncementTextForm,
    CaseCreateForm,
    CompletenessCheckFormSet,
    DivisionConsultationFormSet,
    FieldFormSet,
    InfrastructureCheckFormSet,
    LandPlotDecisionFormSet,
    LandPlotEvaluationFormSet,
    LandPlotFormSet,
    ParcelFormSet,
    Section1Form,
    Section2Form,
    Section3Form,
    Section4Form,
    Section6Form,
    Section7Form,
    Section8Form,
    Section8PlotsForm,
    SubmissionCycleForm,
    SubmissionCyclePublicationFormSet,
    SuitabilityConsultationFormSet,
    UtilityServiceFormSet,
    ValuationReferralFormSet,
)
from cases.models import Case, CompletenessCheck, Consultation, SubmissionCycle
from cases.services import (
    announcement_readiness,
    build_announcement_text,
    case_communications,
    create_deficiency_email,
    generate_case_number,
    mark_communication_sent,
    publish_announcement,
    section8_completion,
    suitability_summary,
)
from cases.section_labels import get_case_section_label
from cases.services import case_history as case_history_entries
from core.models import Communication, Community

# Each entry drives one action screen of the Κ.Σ./Δ.Δ. application: the label shown on
# the case folder, a short description, the main Case form and its inline formsets.
SECTIONS = {
    "1": {
        "title": "Ενότητα 1 — Δεδομένα αίτησης Κ.Σ. / Δ.Δ.",
        "action": "Βασικά στοιχεία και προτεραιότητα",
        "summary": "1.1 στοιχεία υπόθεσης, 1.2 χαρακτηριστικά προτεραιότητας, 1.3 σχόλια.",
        "form": Section1Form,
        "formsets": (),
    },
    "2": {
        "title": "Ενότητα 2 — Έλεγχος πληρότητας αίτησης Κ.Σ.",
        "action": "Έλεγχος πληρότητας",
        "summary": "Επαναλαμβανόμενος πίνακας ελέγχων με ελλείψεις και email.",
        "form": Section2Form,
        "formsets": (("completeness_checks", CompletenessCheckFormSet, "2 Πίνακας ελέγχων"),),
    },
    "3": {
        "title": "Ενότητα 3 — Στοιχεία τεμαχίων",
        "action": "Στοιχεία τεμαχίων",
        "summary": "Πίνακας τεμαχίων και έλεγχος κρατικής γης.",
        "form": Section3Form,
        "formsets": (("land_plots", LandPlotFormSet, "3 Πίνακας τεμαχίων"),),
    },
    "4": {
        "title": "Ενότητα 4 — Τεχνική αξιολόγηση καταλληλότητας",
        "action": "Τεχνική αξιολόγηση",
        "summary": "4.1 αξιολόγηση ανά τεμάχιο, 4.2 υπηρεσίες κοινής ωφέλειας, 4.3 πρόσβαση.",
        "form": Section4Form,
        "formsets": (
            ("plot_evaluations", LandPlotEvaluationFormSet, "4.1 Τεχνική αξιολόγηση ανά τεμάχιο"),
            ("utility_services", UtilityServiceFormSet, "4.2 Υπηρεσίες κοινής ωφέλειας"),
        ),
    },
    "5": {
        "title": "Ενότητα 5 — Διαβουλεύσεις με Τμήματα / Υπηρεσίες",
        "action": "Διαβουλεύσεις καταλληλότητας",
        "summary": "Μία γραμμή ανά διαβούλευση· η κατάσταση είναι αυτόματη.",
        "form": None,
        "formsets": (("consultations", SuitabilityConsultationFormSet, "5 Διαβουλεύσεις"),),
    },
    "6": {
        "title": "Ενότητα 6 — Αξιολόγηση καταλληλότητας",
        "action": "Απόφαση καταλληλότητας",
        "summary": "6.1–6.5 συνοπτικοί πίνακες, 6.6 απόφαση και αιτιολόγηση ανά τεμάχιο.",
        "form": Section6Form,
        "formsets": (
            ("plot_decisions", LandPlotDecisionFormSet, "6.6 Απόφαση καταλληλότητας ανά τεμάχιο"),
        ),
    },
    "7": {
        "title": "Ενότητα 7 — Σύσταση προς τον Υπουργό",
        "action": "Σύσταση προς Υπουργό",
        "summary": "Σύσταση Επαρχιακής Διοίκησης και απόφαση ΥΠΕΣ.",
        "form": Section7Form,
        "formsets": (),
    },
    "8": {
        "title": "Ενότητα 8 — Σχεδιασμός και υλοποίηση διαχωρισμού (8.1–8.6)",
        "action": "Διαχωρισμός (8.1–8.6)",
        "summary": "Ανάθεση μελέτης, ΤΠΟ, διαγωνισμός, διαβουλεύσεις και έλεγχοι υποδομών.",
        "form": Section8Form,
        "formsets": (
            ("consultations", DivisionConsultationFormSet, "8.4 Διαβουλεύσεις κατά τον διαχωρισμό"),
            ("infrastructure_checks", InfrastructureCheckFormSet, "8.6 Έλεγχος υποδομών"),
        ),
    },
    "8-plots": {
        "title": "Ενότητα 8 — Οικόπεδα, εμβαδά και αξία (8.7–8.8)",
        "action": "Οικόπεδα, αξία και τιμή (8.7–8.8)",
        "summary": "Χωρομετρική εργασία, χωράφια, οικόπεδα και τιμή διάθεσης 25%.",
        "form": Section8PlotsForm,
        "formsets": (
            ("fields", FieldFormSet, "8.7 Χωράφια"),
            ("valuation_referrals", ValuationReferralFormSet, "8.8.1 Παραπομπές προς ΤΚΧ"),
            ("parcels", ParcelFormSet, "8.7 / 8.8 Πίνακας αντιστοίχισης οικοπέδων"),
        ),
    },
}

SECTION_ORDER = list(SECTIONS)

CONSULTATION_STAGE_BY_SECTION = {
    "5": Consultation.Stage.SUITABILITY,
    "8": Consultation.Stage.DIVISION,
}


def _build_formsets(section_key, case, data=None):
    """Instantiate the inline formsets of a section, scoped to the case."""
    formsets = []
    for prefix, formset_class, legend in SECTIONS[section_key]["formsets"]:
        kwargs = {"instance": case, "prefix": prefix}
        if prefix == "consultations":
            kwargs["queryset"] = Consultation.objects.filter(
                case=case, stage=CONSULTATION_STAGE_BY_SECTION[section_key]
            )
        formsets.append((legend, formset_class(data, **kwargs)))
    return formsets


def section_screens_for(case):
    """Sections of this case that are edited through the generic section screen.

    Ενότητα 9 is applicable too, but it is handled by the dedicated announcement
    screens because it lives on SubmissionCycle rather than on the Case.
    """
    applicable = case.applicable_sections
    return [key for key in SECTION_ORDER if key in applicable]


SECTION_9_NAV = {
    "key": "9",
    "action": "Γνωστοποίηση έναρξης αιτήσεων",
    "summary": "Ενότητα 9: περίοδος υποβολής, δημοσίευση και έκδοση ανακοίνωσης.",
    "title": "Ενότητα 9 — Γνωστοποίηση έναρξης αιτήσεων",
}


def case_nav_items(case, active_key=None):
    """Sidebar navigation for case work screens (sections 1–8 and 9)."""
    items = [
        {
            "key": key,
            "action": get_case_section_label(key),
            "summary": SECTIONS[key]["summary"],
            "title": get_case_section_label(key),
            "is_active": active_key == key,
        }
        for key in section_screens_for(case)
    ]
    if "9" in case.applicable_sections:
        items.append(
            {
                "key": "9",
                "action": get_case_section_label("9"),
                "summary": SECTION_9_NAV["summary"],
                "title": get_case_section_label("9"),
                "is_active": active_key == "9",
            }
        )
    return items


@login_required
def case_list(request):
    cases = Case.objects.select_related("community").all()
    communities = Community.objects.filter(is_active=True).order_by("name")
    community_id = request.GET.get("community_id") or ""
    case_type = request.GET.get("case_type") or ""
    q = (request.GET.get("q") or "").strip()
    if community_id:
        cases = cases.filter(community_id=community_id)
    if case_type:
        cases = cases.filter(case_type=case_type)
    if q:
        cases = cases.filter(case_number__icontains=q)
    return render(
        request,
        "cases/list.html",
        {
            "cases": cases,
            "communities": communities,
            "community_id": community_id,
            "case_type": case_type,
            "case_types": Case.CaseType.choices,
            "q": q,
        },
    )


@login_required
def case_create(request):
    if request.method == "POST":
        form = CaseCreateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    case = form.save(commit=False)
                    case.start_date = timezone.localdate()
                    case.case_number = generate_case_number(case.community, case.start_date)
                    case.save()
            except ValidationError as exc:
                form.add_error(None, exc.messages[0] if exc.messages else str(exc))
            else:
                messages.success(request, f"Δημιουργήθηκε η υπόθεση {case.case_number}.")
                return redirect("cases:detail", pk=case.pk)
    else:
        form = CaseCreateForm()
    communities = Community.objects.filter(is_active=True)
    community_emails = {str(community.pk): community.contact_email for community in communities}
    community_districts = {str(community.pk): community.district for community in communities}
    return render(
        request,
        "cases/create.html",
        {
            "form": form,
            "community_emails": community_emails,
            "community_districts": community_districts,
        },
    )


@login_required
def case_detail(request, pk):
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    return render(
        request,
        "cases/detail.html",
        {
            "case": case,
            "case_nav": case_nav_items(case),
            "suitability_summary": suitability_summary(case) if case.is_new_division else None,
            "completeness_checks": case.completeness_checks.all(),
            "land_plots": case.land_plots.all(),
            "suitability_consultations": case.consultations.filter(
                stage=Consultation.Stage.SUITABILITY
            ),
            "division_consultations": case.consultations.filter(
                stage=Consultation.Stage.DIVISION
            ),
            "infrastructure_checks": case.infrastructure_checks.all(),
            "parcels": case.parcels.select_related("field", "valuation_referral"),
            "completion": section8_completion(case),
            "readiness": announcement_readiness(case),
            "communications": case_communications(case),
            "submission_cycles": case.submission_cycles.all(),
        },
    )


@login_required
def case_history(request, pk):
    case = get_object_or_404(Case, pk=pk)
    return render(
        request,
        "cases/history.html",
        {
            "case": case,
            "history_entries": case_history_entries(case),
            "case_nav": case_nav_items(case),
        },
    )


@login_required
def case_section_edit(request, pk, section):
    if section not in SECTIONS:
        raise Http404("Άγνωστη ενότητα.")
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    if section not in case.applicable_sections:
        raise Http404("Η ενότητα δεν ισχύει για αυτόν τον τύπο διαδικασίας.")
    section_config = SECTIONS[section]
    form_class = section_config["form"]

    if request.method == "POST":
        form = form_class(request.POST, instance=case) if form_class else None
        formsets = _build_formsets(section, case, request.POST)
        form_valid = form.is_valid() if form else True
        formsets_valid = all(formset.is_valid() for _, formset in formsets)
        if form_valid and formsets_valid:
            with transaction.atomic():
                if form:
                    form.save()
                for _, formset in formsets:
                    formset.save()
            messages.success(request, "Οι αλλαγές αποθηκεύτηκαν.")
            return redirect("cases:detail", pk=case.pk)
    else:
        form = form_class(instance=case) if form_class else None
        formsets = _build_formsets(section, case)

    return render(
        request,
        "cases/section_form.html",
        {
            "case": case,
            "section": section,
            "section_title": get_case_section_label(section),
            "form": form,
            "formsets": formsets,
            "summary": suitability_summary(case) if section == "6" else None,
            "completion": section8_completion(case) if section == "8-plots" else None,
            "completeness_checks": case.completeness_checks.all() if section == "2" else None,
            "communications": case_communications(case) if section == "2" else None,
            "case_nav": case_nav_items(case, active_key=section),
        },
    )


@login_required
def case_deficiency_email_create(request, pk, check_id):
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    check = get_object_or_404(CompletenessCheck, pk=check_id, case=case)
    try:
        create_deficiency_email(check)
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else str(exc))
    else:
        messages.success(
            request, f"Δημιουργήθηκε προσχέδιο email ελλείψεων ({check.sequence}ος έλεγχος)."
        )
    return redirect("cases:section_edit", pk=case.pk, section="2")


@login_required
def case_deficiency_email_send(request, pk, communication_id):
    case = get_object_or_404(Case, pk=pk)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    communication = get_object_or_404(Communication, pk=communication_id, object_id=case.pk)
    try:
        mark_communication_sent(communication)
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else str(exc))
    else:
        messages.success(request, "Καταγράφηκε η αποστολή του email ελλείψεων.")
    return redirect("cases:detail", pk=case.pk)


@login_required
def announcement_create(request, pk):
    """9.1 Create the announcement of a case, gated by the 9.4 readiness check."""
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    readiness = announcement_readiness(case)
    if request.method == "POST":
        form = SubmissionCycleForm(request.POST, community=case.community)
        if form.is_valid():
            with transaction.atomic():
                cycle = form.save(commit=False)
                cycle.community = case.community
                cycle.save()
                form.save_m2m()
                cycle.cases.add(case)
                cycle.announcement_text = build_announcement_text(cycle)
                cycle.save()
            messages.success(request, "Δημιουργήθηκε η γνωστοποίηση (9.1) με προσχέδιο (9.3).")
            return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)
    else:
        form = SubmissionCycleForm(community=case.community, initial={"cases": [case]})
    return render(
        request,
        "cases/announcement_form.html",
        {
            "case": case,
            "form": form,
            "readiness": readiness,
            "case_nav": case_nav_items(case, active_key="9"),
            "section_title": get_case_section_label("9"),
        },
    )


@login_required
def announcement_detail(request, pk, cycle_id):
    """9.2–9.4 Publication methods, announcement text and readiness."""
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    cycle = get_object_or_404(SubmissionCycle, pk=cycle_id, cases=case)

    if request.method == "POST":
        text_form = AnnouncementTextForm(request.POST, instance=cycle)
        publications = SubmissionCyclePublicationFormSet(
            request.POST, instance=cycle, prefix="publications"
        )
        if text_form.is_valid() and publications.is_valid():
            with transaction.atomic():
                text_form.save()
                publications.save()
            messages.success(request, "Οι αλλαγές της γνωστοποίησης αποθηκεύτηκαν.")
            return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)
    else:
        text_form = AnnouncementTextForm(instance=cycle)
        publications = SubmissionCyclePublicationFormSet(instance=cycle, prefix="publications")

    return render(
        request,
        "cases/announcement_detail.html",
        {
            "case": case,
            "cycle": cycle,
            "text_form": text_form,
            "publications": publications,
            "readiness_by_case": [
                (linked, announcement_readiness(linked)) for linked in cycle.cases.all()
            ],
            "case_nav": case_nav_items(case, active_key="9"),
            "section_title": get_case_section_label("9"),
        },
    )


@login_required
def announcement_regenerate(request, pk, cycle_id):
    """9.3 Rebuild the draft from current case data."""
    case = get_object_or_404(Case, pk=pk)
    cycle = get_object_or_404(SubmissionCycle, pk=cycle_id, cases=case)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if cycle.is_published:
        messages.error(request, "Η ανακοίνωση έχει οριστικοποιηθεί και δεν αλλάζει.")
    else:
        cycle.announcement_text = build_announcement_text(cycle)
        cycle.save()
        messages.success(request, "Το προσχέδιο ανακοίνωσης δημιουργήθηκε ξανά (9.3).")
    return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)


@login_required
def announcement_publish(request, pk, cycle_id):
    """9.3 Finalise and issue the announcement."""
    case = get_object_or_404(Case, pk=pk)
    cycle = get_object_or_404(SubmissionCycle, pk=cycle_id, cases=case)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    try:
        publish_announcement(cycle)
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if exc.messages else str(exc))
    else:
        messages.success(request, "Η ανακοίνωση οριστικοποιήθηκε και εκδόθηκε (9.3).")
    return redirect("cases:announcement_detail", pk=case.pk, cycle_id=cycle.pk)
