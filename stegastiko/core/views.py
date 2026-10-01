from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render

from cases.forms import UtilityServiceTypeFormSet
from cases.models import UtilityServiceType
from core.configuration_forms import SystemConfigurationForm
from core.permissions import user_is_system_admin
from core.reminders import (
    CONSULTATION_DUE_REMINDER_TYPE,
    consultation_due_reminders,
    mark_reminder_read,
)


class AppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = "login"
    http_method_names = ["post", "options"]


@login_required
def home(request):
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
def reminders(request):
    return render(
        request,
        "core/reminders.html",
        {"reminders": consultation_due_reminders(request.user, include_read=True)},
    )


@login_required
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


@login_required
@user_passes_test(user_is_system_admin)
def system_configuration(request):
    if request.method == "POST":
        form = SystemConfigurationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Οι ρυθμίσεις αποθηκεύτηκαν.")
            return redirect("system_configuration")
    else:
        form = SystemConfigurationForm()
    return render(
        request,
        "core/system_configuration.html",
        {"form": form},
    )


@login_required
@user_passes_test(user_is_system_admin)
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
    return render(request, "core/utility_service_types.html", {"formset": formset})
