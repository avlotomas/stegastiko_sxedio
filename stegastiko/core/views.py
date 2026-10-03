from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from cases.forms import UtilityServiceTypeFormSet
from cases.models import UtilityServiceType
from core.forms import AppPasswordChangeForm
from core.function_catalog import EDIT
from core.permissions import access_required, has_access
from core.reminders import (
    CONSULTATION_DUE_REMINDER_TYPE,
    consultation_due_reminders,
    mark_reminder_read,
)
from core.settings_navigation import settings_nav

PERMISSION_DENIED_MESSAGE = "Δεν έχετε πρόσβαση σε αυτή τη λειτουργία."


def permission_denied(request, exception=None):
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(
            {"ok": False, "message": PERMISSION_DENIED_MESSAGE, "errors": [PERMISSION_DENIED_MESSAGE]},
            status=403,
        )
    return render(request, "403.html", {"message": PERMISSION_DENIED_MESSAGE}, status=403)


class AppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = "login"
    http_method_names = ["post", "options"]


@login_required
def home(request):
    reminders = []
    if has_access(request.user, "reminders"):
        reminders = consultation_due_reminders(request.user, include_read=False)
    return render(
        request,
        "core/home.html",
        {
            "dashboard_reminders": reminders[:5],
            "dashboard_reminders_total": len(reminders),
        },
    )


@login_required
def account(request):
    if request.method == "POST":
        form = AppPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Ο κωδικός πρόσβασης ενημερώθηκε.")
            return redirect("account")
    else:
        form = AppPasswordChangeForm(request.user)
    return render(request, "core/account.html", {"form": form})


@access_required("reminders")
def reminders(request):
    return render(
        request,
        "core/reminders.html",
        {"reminders": consultation_due_reminders(request.user, include_read=True)},
    )


@access_required("reminders")
def reminder_mark_read(request):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    reminder_key = (request.POST.get("reminder_key") or "").strip()
    reminder_type = (request.POST.get("reminder_type") or "").strip()
    if not reminder_key or reminder_type != CONSULTATION_DUE_REMINDER_TYPE:
        raise Http404("Μη έγκυρη υπενθύμιση.")
    active_reminders = consultation_due_reminders(request.user, include_read=True)
    if not any(item.key == reminder_key for item in active_reminders):
        raise Http404("Η υπενθύμιση δεν είναι διαθέσιμη.")
    mark_reminder_read(request.user, reminder_key, reminder_type)
    messages.success(request, "Η υπενθύμιση σημειώθηκε ως διαβασμένη.")
    next_url = request.POST.get("next") or "home"
    return redirect(next_url)


@access_required("settings_catalogs", post_action=EDIT)
def utility_service_types(request):
    """4.2 Values of the «Υπηρεσία» dropdown: rename, add, order, deactivate."""
    queryset = UtilityServiceType.objects.all()
    if request.method == "POST":
        formset = UtilityServiceTypeFormSet(request.POST, queryset=queryset, prefix="service_types")
        if formset.is_valid():
            with transaction.atomic():
                formset.save()
            messages.success(request, "Ο κατάλογος υπηρεσιών αποθηκεύτηκε.")
            return redirect("utility_service_types")
    else:
        formset = UtilityServiceTypeFormSet(queryset=queryset, prefix="service_types")
    can_edit = has_access(request.user, "settings_catalogs", EDIT)
    if not can_edit:
        for form in formset:
            for field in form.fields.values():
                field.disabled = True
    return render(
        request,
        "core/utility_service_types.html",
        {
            "formset": formset,
            "settings_nav": settings_nav(request.user, "catalogs"),
            "can_edit": can_edit,
        },
    )
