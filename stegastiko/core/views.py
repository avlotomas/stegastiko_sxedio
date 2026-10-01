from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from core.configuration_forms import SystemConfigurationForm
from core.permissions import user_is_system_admin


class AppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = "login"
    http_method_names = ["post", "options"]


@login_required
def home(request):
    return render(request, "core/home.html")


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
