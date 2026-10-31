"""Grid modals of the section screens: one `GridEndpoint` per grid and thin view functions.

The view functions keep their historical names and signatures because cases/urls.py and
static/js/app.js address them.
"""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from cases import section_refs as refs
from cases.forms import (
    ApprovedDesignPlotBulkForm,
    ApprovedDesignPlotForm,
    ApprovedDesignPlotInlineForm,
    CompletenessCheckForm,
    ConsultationForm,
    InfrastructureCheckForm,
    LandPlotEvaluationForm,
    LandPlotForm,
    MinistryDecisionRoundForm,
    UtilityServiceForm,
    approved_design_plot_inline_rows,
)
from cases.models import (
    ApprovedDesignPlot,
    Case,
    CompletenessCheck,
    Consultation,
    InfrastructureCheck,
    LandPlot,
    MinistryDecisionRound,
    UtilityService,
)
from cases.services import (
    LAND_PLOT_EMAIL_SUBJECT_DEFAULT,
    LAND_PLOT_EMAIL_SUBJECT_KEY,
    approved_design_plot_section,
    approved_design_plot_section_ref,
    land_plot_email_subject,
)
from cases.views.common import case_for_section, wants_json
from cases.views.grid import GridEndpoint
from core.function_catalog import CREATE, DELETE, EDIT, VIEW, case_section_function
from core.permissions import has_access, require_access
from core.services import get_setting, smtp_is_configured

# Ενότητα 5 and 7.4 share the consultation grid. Ενότητα 7 has no separate create access
# type, so its rows are added with the edit permission (as the 7.3 grid does).
CONSULTATION_GRIDS = {
    Consultation.Stage.SUITABILITY: {
        "section": refs.SECTION_5,
        "create_action": CREATE,
        "delete_action": DELETE,
        "create_url_name": "cases:suitability_consultation_create",
        "edit_url_name": "cases:suitability_consultation_edit",
        "delete_url_name": "cases:suitability_consultation_delete",
    },
    Consultation.Stage.DIVISION: {
        "section": refs.SECTION_7,
        "create_action": EDIT,
        "delete_action": DELETE,
        "create_url_name": "cases:division_consultation_create",
        "edit_url_name": "cases:division_consultation_edit",
        "delete_url_name": "cases:division_consultation_delete",
    },
}


def consultation_grid(user, case, stage):
    config = CONSULTATION_GRIDS[stage]
    function = case_section_function(config["section"])
    return {
        **config,
        "consultations": case.consultations.filter(stage=stage).prefetch_related("attachments"),
        "can_create": has_access(user, function, config["create_action"]),
        "can_edit": has_access(user, function, EDIT),
        "can_delete": has_access(user, function, config["delete_action"]),
    }


def case_utility_services(case):
    return case.utility_services.select_related("service_type")


def completeness_check_grid_context(case):
    return {
        "completeness_checks": case.completeness_checks.prefetch_related("communications"),
        "smtp_ready": smtp_is_configured(),
    }


def land_plot_grid_context(case):
    plots = list(
        case.land_plots.select_related("case__community").prefetch_related(
            "attachments", "approved_design_plots", "communications"
        )
    )
    # 3.1 Each row's «Αποστολή Email» opens the dialog with its own predefined subject.
    subject_template = get_setting(LAND_PLOT_EMAIL_SUBJECT_KEY, LAND_PLOT_EMAIL_SUBJECT_DEFAULT)
    for plot in plots:
        plot.email_subject = land_plot_email_subject(plot, subject_template)
    return {"land_plots": plots, "smtp_ready": smtp_is_configured()}


# --- 2.1 Completeness checks ------------------------------------------------------------


class CompletenessCheckGrid(GridEndpoint):
    section = refs.SECTION_2
    model = CompletenessCheck
    form_class = CompletenessCheckForm
    section_ref = refs.REF_COMPLETENESS_CHECKS
    grid_template = "cases/_completeness_check_grid.html"
    form_template = "cases/_completeness_check_form.html"
    form_context_name = "check_form"

    def grid_context(self, request, case):
        return completeness_check_grid_context(case)

    def saved_message(self, instance, is_new):
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return f"{verb} ο {instance.sequence}ος έλεγχος πληρότητας."

    def deleted_message(self, label):
        return f"Διαγράφηκε ο έλεγχος ({label})."

    def refuse_delete(self, request, case, instance):
        if instance.can_delete:
            return None
        return JsonResponse(
            {
                "ok": False,
                "message": "Ο έλεγχος δεν διαγράφεται γιατί έχει απεσταλμένα email ελλείψεων.",
                "grid_html": self.grid_html(request, case),
            },
            status=409,
        )


# --- 3.1 Land plots ---------------------------------------------------------------------


class LandPlotGrid(GridEndpoint):
    section = refs.SECTION_3
    model = LandPlot
    form_class = LandPlotForm
    section_ref = refs.REF_LAND_PLOTS
    grid_template = "cases/_land_plot_grid.html"
    form_template = "cases/_land_plot_form.html"
    form_context_name = "plot_form"
    delete_attachments = True

    def grid_context(self, request, case):
        return land_plot_grid_context(case)

    def saved_message(self, instance, is_new):
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return f"{verb} το τεμάχιο {instance.parcel_number}."

    def delete_label(self, instance):
        return instance.parcel_number

    def deleted_message(self, label):
        return f"Διαγράφηκε το τεμάχιο {label}."

    def refuse_delete(self, request, case, instance):
        # A parcel named as the origin of a 7.3 plot stays until that link is removed.
        refusal = instance.deletion_refusal
        if refusal:
            return JsonResponse(
                {"ok": False, "message": refusal, "grid_html": self.grid_html(request, case)},
                status=409,
            )
        # The grid may predate a 4.1 evaluation entered meanwhile, so the server checks again.
        if not instance.has_technical_evaluation or request.POST.get("confirm_evaluation") == "1":
            return None
        return JsonResponse(
            {
                "ok": False,
                "requires_confirmation": True,
                "message": instance.deletion_warning,
                "grid_html": self.grid_html(request, case),
            },
            status=409,
        )


# --- 4.1 Technical evaluation per plot (edit only) ------------------------------------------


class PlotEvaluationGrid(GridEndpoint):
    section = refs.SECTION_4
    model = LandPlot
    form_class = LandPlotEvaluationForm
    section_ref = refs.REF_PLOT_EVALUATION
    grid_template = "cases/_plot_evaluation_grid.html"
    form_template = "cases/_plot_evaluation_form.html"
    form_context_name = "evaluation_form"
    # The rows follow the 3.1 plots one-to-one, so plots are never added or removed here.
    can_create = False

    def grid_context(self, request, case):
        return {"land_plots": case.land_plots.all()}

    def saved_message(self, instance, is_new):
        return f"Ενημερώθηκε η τεχνική αξιολόγηση του τεμαχίου {instance.parcel_number}."


# --- 4.2 Utility services -----------------------------------------------------------------


class UtilityServiceGrid(GridEndpoint):
    section = refs.SECTION_4
    model = UtilityService
    form_class = UtilityServiceForm
    section_ref = refs.REF_UTILITY_SERVICES
    grid_template = "cases/_utility_service_grid.html"
    form_template = "cases/_utility_service_form.html"
    form_context_name = "service_form"

    def grid_context(self, request, case):
        return {"utility_services": case_utility_services(case)}

    def saved_message(self, instance, is_new):
        verb = "Προστέθηκε" if is_new else "Ενημερώθηκε"
        return f"{verb} η υπηρεσία {instance.row_label}."

    def deleted_message(self, label):
        return f"Διαγράφηκε η υπηρεσία {label}."


# --- 5 / 7.4 Consultations ------------------------------------------------------------------


class ConsultationGrid(GridEndpoint):
    model = Consultation
    form_class = ConsultationForm
    grid_template = "cases/_consultation_grid.html"
    form_template = "cases/_consultation_form.html"
    delete_attachments = True
    noun_saved = "η διαβούλευση"
    noun_deleted = "η διαβούλευση"

    def __init__(self, stage):
        self.stage = stage
        self.config = CONSULTATION_GRIDS[stage]
        self.section = self.config["section"]
        self.create_action = self.config["create_action"]
        self.delete_action = self.config["delete_action"]
        self.section_ref = Consultation.SECTION_REF_BY_STAGE[stage]

    def queryset(self, case):
        return Consultation.objects.filter(case=case, stage=self.stage)

    def new_instance(self, case):
        return Consultation(case=case, stage=self.stage)

    def grid_context(self, request, case):
        return {"consultation_grid": consultation_grid(request.user, case, self.stage)}

    def form_context(self, request, case, form):
        return {"consultation_form": form, "consultation_urls": self.config}


CONSULTATION_ENDPOINTS = {stage: ConsultationGrid(stage) for stage in CONSULTATION_GRIDS}


# --- 6.7 Ministry decision rounds -----------------------------------------------------------


class MinistryDecisionRoundGrid(GridEndpoint):
    section = refs.SECTION_6
    model = MinistryDecisionRound
    form_class = MinistryDecisionRoundForm
    section_ref = refs.REF_MINISTRY_DECISIONS
    grid_template = "cases/_ministry_decision_round_grid.html"
    form_template = "cases/_ministry_decision_round_form.html"
    form_context_name = "round_form"
    # Ενότητα 6 has no «Δημιουργία» access type: rows are added with «Επεξεργασία».
    create_action = EDIT
    delete_attachments = True

    def grid_context(self, request, case):
        return {
            "ministry_decision_rounds": case.ministry_decision_rounds.prefetch_related(
                "attachments"
            ),
            "readonly": False,
        }


# --- 7.3 Approved design plots (8.2 for unallocated-plots cases) ------------------------------


class ApprovedDesignPlotGrid(GridEndpoint):
    """The rows belong to Ενότητα 7 (new division) or 8.2 (unallocated plots).

    The owning section comes from the case type; the `?section=` the screen sends must
    match it, so a row is only ever changed with the access of the section that owns it.
    """

    model = ApprovedDesignPlot
    form_class = ApprovedDesignPlotForm
    grid_template = "cases/_approved_design_plot_grid.html"
    form_template = "cases/_approved_design_plot_form.html"
    form_context_name = "plot_form"
    # Neither Ενότητα 7 nor 8 has a «Δημιουργία» access type.
    create_action = EDIT

    def get_case(self, request, pk, kind):
        case = get_object_or_404(Case, pk=pk)
        section = approved_design_plot_section(case)
        require_access(request.user, case_section_function(section), self.action_for(kind, section))
        return case

    def row_ref(self, request, case, instance):
        return approved_design_plot_section_ref(approved_design_plot_section(case))

    def grid_context(self, request, case, bound_form=None):
        section = approved_design_plot_section(case)
        function = case_section_function(section)
        can_edit = has_access(request.user, function, EDIT)
        plots = list(
            case.approved_design_plots.select_related("plot").prefetch_related("source_land_plots")
        )
        return {
            "approved_design_plots": plots,
            "approved_design_plot_rows": (
                approved_design_plot_inline_rows(case, bound_form, plots) if can_edit else ()
            ),
            "plot_section": section,
            # The «Τεμάχια προέλευσης» column appears once the case has 3.1 parcels.
            "has_source_land_plots": case.land_plots.exists(),
            "can_edit_approved_design_plots": can_edit,
            "can_delete_approved_design_plots": has_access(
                request.user, function, self.delete_action or DELETE
            ),
            "readonly": not can_edit,
        }

    def grid_html(self, request, case, bound_form=None):
        return render_to_string(
            self.grid_template,
            {"case": case, **self.grid_context(request, case, bound_form)},
            request=request,
        )

    def form_context(self, request, case, form):
        return {"plot_form": form, "plot_section": approved_design_plot_section(case)}

    def refuse_delete(self, request, case, instance):
        # Β: a row that became a completed plot is removed from «Οικόπεδα» first.
        if instance.generated_plot is None:
            return None
        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "Η εγγραφή δεν διαγράφεται γιατί έχει ήδη καταχωριστεί στα Οικόπεδα με την "
                    "ολοκλήρωση της αίτησης. Διαγράψτε πρώτα το οικόπεδο από τον πίνακα «Οικόπεδα»."
                ),
                "grid_html": self.grid_html(request, case),
            },
            status=409,
        )

    def extra_payload(self, request, case):
        return {"reload": False}

    def inline_edit_view(self, request, pk, obj_id):
        case = self.get_case(request, pk, "edit")
        if request.method != "POST" or not wants_json(request):
            raise Http404("Επιτρέπεται μόνο POST.")
        instance = self.get_instance(case, obj_id)
        form = ApprovedDesignPlotInlineForm(
            request.POST,
            instance=instance,
            prefix=f"plot-{instance.pk}",
        )
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "grid_html": self.grid_html(request, case, form)},
                status=400,
            )
        instance._section_ref = self.row_ref(request, case, instance)
        with transaction.atomic():
            instance = form.save()
        return JsonResponse(
            {
                "ok": True,
                "message": self.saved_message(instance, False),
                "grid_html": self.grid_html(request, case),
            }
        )

    def grid_view(self, request, pk):
        case = self.get_case(request, pk, "view")
        if request.method != "GET" or not wants_json(request):
            raise Http404()
        return JsonResponse({"ok": True, "grid_html": self.grid_html(request, case)})

    def perform_delete(self, request, case, instance):
        try:
            super().perform_delete(request, case, instance)
        except ProtectedError:
            return JsonResponse(
                {
                    "ok": False,
                    "message": "Το οικόπεδο έχει ήδη κατανομή και δεν μπορεί να διαγραφεί.",
                },
                status=409,
            )
        return None

    def bulk_form_html(self, request, case, form):
        return render_to_string(
            "cases/_approved_design_plot_bulk_form.html",
            {"case": case, "bulk_form": form, "plot_section": approved_design_plot_section(case)},
            request=request,
        )

    def bulk_create_view(self, request, pk):
        case = self.get_case(request, pk, "create")
        if not wants_json(request):
            raise Http404()
        if request.method == "POST":
            form = ApprovedDesignPlotBulkForm(request.POST, case=case)
            if not form.is_valid():
                return JsonResponse(
                    {"ok": False, "html": self.bulk_form_html(request, case, form)}, status=400
                )
            plots = form.build_plots(case)
            section_ref = self.row_ref(request, case, None)
            with transaction.atomic():
                for plot in plots:
                    plot._section_ref = section_ref
                    plot.save()
            return JsonResponse(
                {
                    "ok": True,
                    "message": f"Προστέθηκαν {len(plots)} εγγραφές ({plots[0].plot_type_display}).",
                    "grid_html": self.grid_html(request, case),
                    **self.extra_payload(request, case),
                }
            )
        if request.method != "GET":
            raise Http404()
        form = ApprovedDesignPlotBulkForm(case=case)
        return JsonResponse({"ok": True, "html": self.bulk_form_html(request, case, form)})


# --- 7.6 Infrastructure (construction works) checks ---------------------------------------------


class InfrastructureCheckGrid(GridEndpoint):
    section = refs.SECTION_7
    model = InfrastructureCheck
    form_class = InfrastructureCheckForm
    section_ref = refs.REF_INFRASTRUCTURE_CHECKS
    grid_template = "cases/_infrastructure_check_grid.html"
    form_template = "cases/_infrastructure_check_form.html"
    form_context_name = "check_form"
    create_action = EDIT
    noun_saved = "ο έλεγχος"
    noun_deleted = "ο έλεγχος"

    def grid_context(self, request, case):
        return {"infrastructure_checks": case.infrastructure_checks.all()}


COMPLETENESS_CHECKS = CompletenessCheckGrid()
LAND_PLOTS = LandPlotGrid()
PLOT_EVALUATIONS = PlotEvaluationGrid()
UTILITY_SERVICES = UtilityServiceGrid()
MINISTRY_DECISION_ROUNDS = MinistryDecisionRoundGrid()
APPROVED_DESIGN_PLOTS = ApprovedDesignPlotGrid()
INFRASTRUCTURE_CHECKS = InfrastructureCheckGrid()


# --- view functions (addressed by cases/urls.py) ------------------------------------------------


@login_required
def completeness_check_form(request, pk, check_id=None):
    """2.1 Add or edit one completeness check from the grid modal."""
    return COMPLETENESS_CHECKS.form_view(request, pk, check_id)


@login_required
def completeness_check_delete(request, pk, check_id):
    """2.1 Delete one completeness check when it has no sent emails."""
    return COMPLETENESS_CHECKS.delete_view(request, pk, check_id)


@login_required
def land_plot_form(request, pk, plot_id=None):
    """3.1 Add or edit one land plot from the grid modal; files stay on the plot."""
    return LAND_PLOTS.form_view(request, pk, plot_id)


@login_required
def land_plot_delete(request, pk, plot_id):
    """3.1 Delete one land plot (and its files) from the grid."""
    return LAND_PLOTS.delete_view(request, pk, plot_id)


@login_required
def land_plot_evaluation_form(request, pk, plot_id):
    """4.1 Edit the technical evaluation of one 3.1 plot from the grid modal."""
    return PLOT_EVALUATIONS.form_view(request, pk, plot_id)


@login_required
def utility_service_form(request, pk, service_id=None):
    """4.2 Add or edit one utility service row from the grid modal."""
    return UTILITY_SERVICES.form_view(request, pk, service_id)


@login_required
def utility_service_delete(request, pk, service_id):
    """4.2 Delete one utility service row from the grid."""
    return UTILITY_SERVICES.delete_view(request, pk, service_id)


@login_required
def consultation_form(request, pk, stage, consultation_id=None):
    """5 / 7.4 Add or edit one consultation from the grid modal."""
    return CONSULTATION_ENDPOINTS[stage].form_view(request, pk, consultation_id)


@login_required
def consultation_delete(request, pk, stage, consultation_id):
    """5 / 7.4 Delete one consultation (and its files) from the grid."""
    return CONSULTATION_ENDPOINTS[stage].delete_view(request, pk, consultation_id)


@login_required
def ministry_decision_round_form(request, pk, round_id=None):
    """6.7 Add or edit one ministry decision row from the grid modal."""
    return MINISTRY_DECISION_ROUNDS.form_view(request, pk, round_id)


@login_required
def ministry_decision_round_delete(request, pk, round_id):
    """6.7 Delete one ministry decision row (and its files) from the grid."""
    return MINISTRY_DECISION_ROUNDS.delete_view(request, pk, round_id)


@login_required
def approved_design_plot_form(request, pk, plot_id=None):
    """7.3 Add or edit one approved design plot row from the grid modal."""
    return APPROVED_DESIGN_PLOTS.form_view(request, pk, plot_id)


@login_required
def approved_design_plot_grid(request, pk):
    """Load the persistent approved-design-plots grid when its workspace opens."""
    return APPROVED_DESIGN_PLOTS.grid_view(request, pk)


@login_required
def approved_design_plot_inline_edit(request, pk, plot_id):
    """Save one row edited directly in the persistent approved-design-plots grid."""
    return APPROVED_DESIGN_PLOTS.inline_edit_view(request, pk, plot_id)


@login_required
def approved_design_plot_bulk_create(request, pk):
    """7.3 «Μαζική προσθήκη» of many rows of one type."""
    return APPROVED_DESIGN_PLOTS.bulk_create_view(request, pk)


@login_required
def approved_design_plot_delete(request, pk, plot_id):
    """7.3 / 8.2 Delete one approved design plot row from the grid."""
    return APPROVED_DESIGN_PLOTS.delete_view(request, pk, plot_id)


@login_required
def infrastructure_check_form(request, pk, check_id=None):
    """7.6 Add or edit one construction works check from the grid modal."""
    return INFRASTRUCTURE_CHECKS.form_view(request, pk, check_id)


@login_required
def infrastructure_check_delete(request, pk, check_id):
    """7.6 Delete one construction works check from the grid."""
    return INFRASTRUCTURE_CHECKS.delete_view(request, pk, check_id)
