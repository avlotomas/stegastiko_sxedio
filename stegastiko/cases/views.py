from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.contrib.contenttypes.models import ContentType
from django.utils import formats, timezone
from django.utils.http import content_disposition_header

from cases.forms import (
    AnnouncementTextForm,
    CaseCreateForm,
    CompletenessCheckForm,
    DeficiencyEmailForm,
    DivisionConsultationFormSet,
    FieldFormSet,
    InfrastructureCheckFormSet,
    LandPlotDecisionFormSet,
    LandPlotEvaluationForm,
    LandPlotForm,
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
    SuitabilityConsultationForm,
    UtilityServiceForm,
    ValuationReferralFormSet,
)
from cases.models import (
    Case,
    CompletenessCheck,
    Consultation,
    LandPlot,
    SubmissionCycle,
    UtilityService,
)
from cases.section4_blank_pdf import render_section4_blank_pdf, section4_blank_pdf_filename
from cases.section6_report_pdf import render_section6_report_pdf, section6_report_pdf_filename
from cases.services import (
    announcement_readiness,
    build_announcement_text,
    case_communications,
    deficiency_email_subject,
    generate_case_number,
    publish_announcement,
    section8_completion,
    send_deficiency_email,
    suitability_summary,
)
from cases.section_labels import case_section_heading, get_case_section_label
from cases.subsection_labels import CASE_SUBSECTION_LABEL_KEYS, case_subsection_heading
from cases.services import case_history as case_history_entries
from core.models import Attachment, Communication, Community
from core.services import smtp_is_configured

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
        "formsets": (),
    },
    "3": {
        "title": "Ενότητα 3 — Στοιχεία τεμαχίων",
        "action": "Στοιχεία τεμαχίων",
        "summary": "3.1 πίνακας τεμαχίων, 3.2 έλεγχος επάρκειας κρατικής γης, 3.3 σχόλια.",
        "form": Section3Form,
        # 3.1 plots are edited one at a time from the grid modal (land_plot_form).
        "formsets": (),
    },
    "4": {
        "title": "Ενότητα 4 — Τεχνική αξιολόγηση καταλληλότητας",
        "action": "Τεχνική αξιολόγηση",
        "summary": "4.1 αξιολόγηση ανά τεμάχιο, 4.2 υπηρεσίες, 4.3 πρόσβαση, 4.4 αρχεία, 4.5 σχόλια, 4.6 επίσκεψη.",
        "form": Section4Form,
        # 4.1 rows follow the 3.1 plots (land_plot_evaluation_form); 4.2 rows have their own
        # grid modal (utility_service_form).
        "formsets": (),
    },
    "5": {
        "title": "Ενότητα 5 — Διαβουλεύσεις με Τμήματα / Υπηρεσίες",
        "action": "Διαβουλεύσεις καταλληλότητας",
        "summary": "Μία γραμμή ανά διαβούλευση· η κατάσταση είναι αυτόματη.",
        "form": None,
        # 5.x rows are edited one at a time from the grid modal (suitability_consultation_form).
        "formsets": (),
    },
    "6": {
        "title": "Ενότητα 6 — Αξιολόγηση καταλληλότητας",
        "action": "Απόφαση καταλληλότητας",
        "summary": "6.1–6.5 συνοπτικοί πίνακες, 6.6 απόφαση και αιτιολόγηση ανά τεμάχιο.",
        "form": Section6Form,
        "formsets": (
            ("plot_decisions", LandPlotDecisionFormSet, "6.6"),
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
            ("consultations", DivisionConsultationFormSet, "8.4"),
            ("infrastructure_checks", InfrastructureCheckFormSet, "8.6"),
        ),
    },
    "8-plots": {
        "title": "Ενότητα 8 — Οικόπεδα, εμβαδά και αξία (8.7–8.8)",
        "action": "Οικόπεδα, αξία και τιμή (8.7–8.8)",
        "summary": "Χωρομετρική εργασία, χωράφια, οικόπεδα και τιμή διάθεσης 25%.",
        "form": Section8PlotsForm,
        "formsets": (
            ("fields", FieldFormSet, "8.7-parcels"),
            ("valuation_referrals", ValuationReferralFormSet, "8.8.1"),
            ("parcels", ParcelFormSet, "8.7-8.8-mapping"),
        ),
    },
}

SECTION_ORDER = list(SECTIONS)

CONSULTATION_STAGE_BY_SECTION = {
    "5": Consultation.Stage.SUITABILITY,
    "8": Consultation.Stage.DIVISION,
}


def _resolve_formset_legend(legend: str) -> str:
    if legend in CASE_SUBSECTION_LABEL_KEYS:
        return case_subsection_heading(legend)
    return legend


def _build_formsets(section_key, case, data=None, files=None):
    """Instantiate the inline formsets of a section, scoped to the case."""
    formsets = []
    for prefix, formset_class, legend in SECTIONS[section_key]["formsets"]:
        legend = _resolve_formset_legend(legend)
        kwargs = {"instance": case, "prefix": prefix}
        if prefix == "consultations":
            kwargs["queryset"] = Consultation.objects.filter(
                case=case, stage=CONSULTATION_STAGE_BY_SECTION[section_key]
            )
        formsets.append((legend, formset_class(data, files, **kwargs)))
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
            "action": case_section_heading(key),
            "summary": SECTIONS[key]["summary"],
            "title": case_section_heading(key),
            "is_active": active_key == key,
        }
        for key in section_screens_for(case)
    ]
    if "9" in case.applicable_sections:
        items.append(
            {
                "key": "9",
                "action": case_section_heading("9"),
                "summary": SECTION_9_NAV["summary"],
                "title": case_section_heading("9"),
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
            "land_plots": case.land_plots.prefetch_related("attachments"),
            "utility_services": _case_utility_services(case),
            "technical_attachments": case.attachments.filter(section_ref="4.4"),
            "suitability_consultations": _case_suitability_consultations(case),
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
        form = form_class(request.POST, request.FILES, instance=case) if form_class else None
        formsets = _build_formsets(section, case, request.POST, request.FILES)
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

    context = {
        "case": case,
        "section": section,
        "section_title": get_case_section_label(section),
        "form": form,
        "formsets": formsets,
        "summary": suitability_summary(case) if section == "6" else None,
        "completion": section8_completion(case) if section == "8-plots" else None,
        "case_nav": case_nav_items(case, active_key=section),
    }
    if section == "3":
        context["land_plots"] = case.land_plots.prefetch_related("attachments")
    if section == "4":
        context["land_plots"] = case.land_plots.all()
        context["utility_services"] = _case_utility_services(case)
    if section == "5":
        context["suitability_consultations"] = _case_suitability_consultations(case)
    if section == "2":
        context.update(
            {
                "completeness_checks": case.completeness_checks.all(),
                "communications": case_communications(case),
                "deficiency_email_form": DeficiencyEmailForm(
                    initial={
                        "subject": deficiency_email_subject(case),
                        "body": "",
                    }
                ),
                "smtp_ready": smtp_is_configured(),
            }
        )
    return render(request, "cases/section_form.html", context)


@login_required
def section_4_blank_pdf(request, pk):
    """Blank Ενότητα 4 form for printing / field completion (PDF)."""
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    if "4" not in case.applicable_sections:
        raise Http404("Η ενότητα δεν ισχύει για αυτόν τον τύπο διαδικασίας.")
    pdf_bytes = render_section4_blank_pdf(case)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True,
        filename=section4_blank_pdf_filename(case),
    )
    return response


@login_required
def section_6_report_pdf(request, pk):
    """Ενότητα 6 report «Πίνακες αξιολόγησης καταλληλότητας κρατικής γης» (PDF)."""
    case = _case_for_section(pk, "6")
    pdf_bytes = render_section6_report_pdf(case)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True,
        filename=section6_report_pdf_filename(case),
    )
    return response


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


@login_required
def completeness_check_form(request, pk, check_id=None):
    """2.1 Add or edit one completeness check from the grid modal."""
    case = _case_for_section(pk, "2")
    if not _wants_json(request):
        raise Http404()
    if check_id is None:
        check = CompletenessCheck(case=case)
    else:
        check = get_object_or_404(CompletenessCheck, pk=check_id, case=case)

    if request.method == "POST":
        form = CompletenessCheckForm(request.POST, instance=check)
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "html": _completeness_check_form_html(request, case, form)}, status=400
            )
        is_new = check.pk is None
        check._section_ref = "2.1"
        with transaction.atomic():
            check = form.save()
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return JsonResponse(
            {
                "ok": True,
                "message": f"{verb} ο {check.sequence}ος έλεγχος πληρότητας.",
                "grid_html": _completeness_check_grid_html(request, case),
            }
        )
    if request.method != "GET":
        raise Http404()
    form = CompletenessCheckForm(instance=check)
    return JsonResponse({"ok": True, "html": _completeness_check_form_html(request, case, form)})


@login_required
def completeness_check_delete(request, pk, check_id):
    """2.1 Delete one completeness check when it has no sent emails."""
    case = _case_for_section(pk, "2")
    if request.method != "POST" or not _wants_json(request):
        raise Http404("Επιτρέπεται μόνο POST.")
    check = get_object_or_404(CompletenessCheck, pk=check_id, case=case)
    if not check.can_delete:
        return JsonResponse(
            {
                "ok": False,
                "message": "Ο έλεγχος δεν διαγράφεται γιατί έχει απεσταλμένα email ελλείψεων.",
                "grid_html": _completeness_check_grid_html(request, case),
            },
            status=409,
        )
    label = check.row_label
    check._section_ref = "2.1"
    check.delete()
    return JsonResponse(
        {"ok": True, "message": f"Διαγράφηκε ο έλεγχος ({label}).", "grid_html": _completeness_check_grid_html(request, case)}
    )


@login_required
def case_deficiency_email_send(request, pk, check_id):
    """2.2 Send the deficiencies email for one completeness check."""
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    if "2" not in case.applicable_sections:
        raise Http404("Η ενότητα δεν ισχύει για αυτόν τον τύπο διαδικασίας.")
    check = get_object_or_404(CompletenessCheck, pk=check_id, case=case)

    form = DeficiencyEmailForm(request.POST)
    errors = []
    communication = None
    if form.is_valid():
        try:
            communication = send_deficiency_email(
                check, form.cleaned_data["subject"], form.cleaned_data["body"]
            )
        except ValidationError as exc:
            errors = exc.messages
    else:
        errors = [error for field_errors in form.errors.values() for error in field_errors]

    if communication:
        message = f"Το email ελλείψεων στάλθηκε στο {communication.recipient}."
    if _wants_json(request):
        if not communication:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        log_html = render_to_string(
            "cases/_deficiency_email_log.html",
            {"case": case, "communications": case_communications(case)},
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                "message": message,
                "log_html": log_html,
                "grid_html": _completeness_check_grid_html(request, case),
            }
        )

    if communication:
        messages.success(request, message)
    else:
        for error in errors:
            messages.error(request, error)
    return redirect("cases:section_edit", pk=case.pk, section="2")


def _completeness_check_form_html(request, case, form):
    return render_to_string(
        "cases/_completeness_check_form.html",
        {"case": case, "check_form": form},
        request=request,
    )


def _completeness_check_grid_html(request, case):
    return render_to_string(
        "cases/_completeness_check_grid.html",
        {
            "case": case,
            "completeness_checks": case.completeness_checks.all(),
            "smtp_ready": smtp_is_configured(),
        },
        request=request,
    )


def _communication_detail_payload(communication: Communication) -> dict:
    sent_at = ""
    if communication.sent_at:
        sent_at = formats.date_format(
            timezone.localtime(communication.sent_at), "SHORT_DATETIME_FORMAT"
        )
    status_display = "Απεστάλη" if communication.status == "sent" else "Προσχέδιο"
    return {
        "recipient": communication.recipient,
        "subject": communication.subject,
        "body": communication.body,
        "check_label": getattr(communication.content_object, "row_label", ""),
        "status": communication.status,
        "status_display": status_display,
        "sent_at": sent_at,
    }


@login_required
def case_communication_detail(request, pk, communication_id):
    """Return one sent email for the 2.2 history view modal."""
    case = get_object_or_404(Case, pk=pk)
    case_type = ContentType.objects.get_for_model(Case)
    check_type = ContentType.objects.get_for_model(CompletenessCheck)
    communication = get_object_or_404(
        Communication.objects.filter(
            Q(content_type=case_type, object_id=case.pk)
            | Q(content_type=check_type, object_id__in=case.completeness_checks.values("pk"))
        ),
        pk=communication_id,
    )
    if request.method != "GET":
        raise Http404("Επιτρέπεται μόνο GET.")
    if not _wants_json(request):
        raise Http404()
    return JsonResponse({"ok": True, **_communication_detail_payload(communication)})


def _case_for_section(pk, section):
    case = get_object_or_404(Case.objects.select_related("community"), pk=pk)
    if section not in case.applicable_sections:
        raise Http404("Η ενότητα δεν ισχύει για αυτόν τον τύπο διαδικασίας.")
    return case


def _land_plot_grid_html(request, case):
    return render_to_string(
        "cases/_land_plot_grid.html",
        {"case": case, "land_plots": case.land_plots.prefetch_related("attachments")},
        request=request,
    )


def _land_plot_form_html(request, case, form):
    return render_to_string(
        "cases/_land_plot_form.html", {"case": case, "plot_form": form}, request=request
    )


@login_required
def land_plot_form(request, pk, plot_id=None):
    """3.1 Add or edit one land plot from the grid modal; files stay on the plot."""
    case = _case_for_section(pk, "3")
    if not _wants_json(request):
        raise Http404()
    if plot_id is None:
        plot = LandPlot(case=case)
    else:
        plot = get_object_or_404(LandPlot, pk=plot_id, case=case)

    if request.method == "POST":
        form = LandPlotForm(request.POST, request.FILES, instance=plot)
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "html": _land_plot_form_html(request, case, form)}, status=400
            )
        is_new = plot.pk is None
        plot._section_ref = "3.1"
        with transaction.atomic():
            plot = form.save()
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return JsonResponse(
            {
                "ok": True,
                "message": f"{verb} το τεμάχιο {plot.parcel_number}.",
                "grid_html": _land_plot_grid_html(request, case),
            }
        )
    if request.method != "GET":
        raise Http404()
    form = LandPlotForm(instance=plot)
    return JsonResponse({"ok": True, "html": _land_plot_form_html(request, case, form)})


@login_required
def land_plot_delete(request, pk, plot_id):
    """3.1 Delete one land plot (and its files) from the grid."""
    case = _case_for_section(pk, "3")
    if request.method != "POST" or not _wants_json(request):
        raise Http404("Επιτρέπεται μόνο POST.")
    plot = get_object_or_404(LandPlot, pk=plot_id, case=case)
    # The grid may predate a 4.1 evaluation entered meanwhile, so the server checks again.
    if plot.has_technical_evaluation and request.POST.get("confirm_evaluation") != "1":
        return JsonResponse(
            {
                "ok": False,
                "requires_confirmation": True,
                "message": plot.deletion_warning,
                "grid_html": _land_plot_grid_html(request, case),
            },
            status=409,
        )
    parcel_number = plot.parcel_number
    plot._section_ref = "3.1"
    with transaction.atomic():
        for attachment in plot.attachments.all():
            attachment._section_ref = "3.1"
            attachment.delete()
        plot.delete()
    return JsonResponse(
        {
            "ok": True,
            "message": f"Διαγράφηκε το τεμάχιο {parcel_number}.",
            "grid_html": _land_plot_grid_html(request, case),
        }
    )


def _plot_evaluation_grid_html(request, case):
    return render_to_string(
        "cases/_plot_evaluation_grid.html",
        {"case": case, "land_plots": case.land_plots.all()},
        request=request,
    )


def _plot_evaluation_form_html(request, case, form):
    return render_to_string(
        "cases/_plot_evaluation_form.html", {"case": case, "evaluation_form": form}, request=request
    )


@login_required
def land_plot_evaluation_form(request, pk, plot_id):
    """4.1 Edit the technical evaluation of one 3.1 plot from the grid modal.

    The rows follow the 3.1 plots one-to-one, so plots are never added or removed here.
    """
    case = _case_for_section(pk, "4")
    if not _wants_json(request):
        raise Http404()
    plot = get_object_or_404(LandPlot, pk=plot_id, case=case)

    if request.method == "POST":
        form = LandPlotEvaluationForm(request.POST, instance=plot)
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "html": _plot_evaluation_form_html(request, case, form)}, status=400
            )
        plot._section_ref = "4.1"
        with transaction.atomic():
            plot = form.save()
        return JsonResponse(
            {
                "ok": True,
                "message": f"Ενημερώθηκε η τεχνική αξιολόγηση του τεμαχίου {plot.parcel_number}.",
                "grid_html": _plot_evaluation_grid_html(request, case),
            }
        )
    if request.method != "GET":
        raise Http404()
    form = LandPlotEvaluationForm(instance=plot)
    return JsonResponse({"ok": True, "html": _plot_evaluation_form_html(request, case, form)})


def _case_suitability_consultations(case):
    return case.consultations.filter(stage=Consultation.Stage.SUITABILITY).prefetch_related(
        "attachments"
    )


def _case_utility_services(case):
    return case.utility_services.select_related("service_type")


def _utility_service_grid_html(request, case):
    return render_to_string(
        "cases/_utility_service_grid.html",
        {"case": case, "utility_services": _case_utility_services(case)},
        request=request,
    )


def _utility_service_form_html(request, case, form):
    return render_to_string(
        "cases/_utility_service_form.html", {"case": case, "service_form": form}, request=request
    )


@login_required
def utility_service_form(request, pk, service_id=None):
    """4.2 Add or edit one utility service row from the grid modal."""
    case = _case_for_section(pk, "4")
    if not _wants_json(request):
        raise Http404()
    if service_id is None:
        service = UtilityService(case=case)
    else:
        service = get_object_or_404(UtilityService, pk=service_id, case=case)

    if request.method == "POST":
        form = UtilityServiceForm(request.POST, instance=service)
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "html": _utility_service_form_html(request, case, form)}, status=400
            )
        is_new = service.pk is None
        service._section_ref = "4.2"
        with transaction.atomic():
            service = form.save()
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return JsonResponse(
            {
                "ok": True,
                "message": f"{verb} η υπηρεσία {service.row_label}.",
                "grid_html": _utility_service_grid_html(request, case),
            }
        )
    if request.method != "GET":
        raise Http404()
    form = UtilityServiceForm(instance=service)
    return JsonResponse({"ok": True, "html": _utility_service_form_html(request, case, form)})


@login_required
def utility_service_delete(request, pk, service_id):
    """4.2 Delete one utility service row from the grid."""
    case = _case_for_section(pk, "4")
    if request.method != "POST" or not _wants_json(request):
        raise Http404("Επιτρέπεται μόνο POST.")
    service = get_object_or_404(UtilityService, pk=service_id, case=case)
    label = service.row_label
    service._section_ref = "4.2"
    service.delete()
    return JsonResponse(
        {
            "ok": True,
            "message": f"Διαγράφηκε η υπηρεσία {label}.",
            "grid_html": _utility_service_grid_html(request, case),
        }
    )


def _suitability_consultation_grid_html(request, case):
    return render_to_string(
        "cases/_suitability_consultation_grid.html",
        {"case": case, "suitability_consultations": _case_suitability_consultations(case)},
        request=request,
    )


def _suitability_consultation_form_html(request, case, form):
    return render_to_string(
        "cases/_suitability_consultation_form.html",
        {"case": case, "consultation_form": form},
        request=request,
    )


@login_required
def suitability_consultation_form(request, pk, consultation_id=None):
    """5 Add or edit one suitability consultation from the grid modal."""
    case = _case_for_section(pk, "5")
    if not _wants_json(request):
        raise Http404()
    if consultation_id is None:
        consultation = Consultation(case=case, stage=Consultation.Stage.SUITABILITY)
    else:
        consultation = get_object_or_404(
            Consultation,
            pk=consultation_id,
            case=case,
            stage=Consultation.Stage.SUITABILITY,
        )

    if request.method == "POST":
        form = SuitabilityConsultationForm(request.POST, request.FILES, instance=consultation)
        if not form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "html": _suitability_consultation_form_html(request, case, form),
                },
                status=400,
            )
        is_new = consultation.pk is None
        consultation._section_ref = "5"
        consultation.stage = Consultation.Stage.SUITABILITY
        with transaction.atomic():
            consultation = form.save()
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return JsonResponse(
            {
                "ok": True,
                "message": f"{verb} η διαβούλευση ({consultation.row_label}).",
                "grid_html": _suitability_consultation_grid_html(request, case),
            }
        )
    if request.method != "GET":
        raise Http404()
    form = SuitabilityConsultationForm(instance=consultation)
    return JsonResponse(
        {"ok": True, "html": _suitability_consultation_form_html(request, case, form)}
    )


@login_required
def suitability_consultation_delete(request, pk, consultation_id):
    """5 Delete one suitability consultation (and its files) from the grid."""
    case = _case_for_section(pk, "5")
    if request.method != "POST" or not _wants_json(request):
        raise Http404("Επιτρέπεται μόνο POST.")
    consultation = get_object_or_404(
        Consultation,
        pk=consultation_id,
        case=case,
        stage=Consultation.Stage.SUITABILITY,
    )
    label = consultation.row_label
    consultation._section_ref = "5"
    with transaction.atomic():
        for attachment in consultation.attachments.filter(section_ref="5"):
            attachment._section_ref = "5"
            attachment.delete()
        consultation.delete()
    return JsonResponse(
        {
            "ok": True,
            "message": f"Διαγράφηκε η διαβούλευση {label}.",
            "grid_html": _suitability_consultation_grid_html(request, case),
        }
    )


@login_required
def case_attachment_download(request, pk, attachment_id):
    """Download a file of the case: 3.1 files of its land plots or 4.4 files of the case."""
    case = get_object_or_404(Case, pk=pk)
    plot_files = Q(
        content_type=ContentType.objects.get_for_model(LandPlot),
        object_id__in=case.land_plots.values("pk"),
    )
    case_files = Q(content_type=ContentType.objects.get_for_model(Case), object_id=case.pk)
    consultation_files = Q(
        content_type=ContentType.objects.get_for_model(Consultation),
        object_id__in=case.consultations.values("pk"),
    )
    attachment = get_object_or_404(
        Attachment.objects.filter(plot_files | case_files | consultation_files),
        pk=attachment_id,
    )
    response = HttpResponse(
        bytes(attachment.data), content_type=attachment.content_type_name
    )
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=attachment.filename
    )
    return response


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
            "submission_cycles": case.submission_cycles.all(),
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
