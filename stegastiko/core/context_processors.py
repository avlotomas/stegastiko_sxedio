from core.branding import get_app_title
from core.menu_labels import get_menu_labels
from core.permissions import AccessProxy


def ui_flags(request):
    context = {"app_title": get_app_title()}
    if request.user.is_authenticated:
        context["access"] = AccessProxy(request.user)
        context["menu"] = get_menu_labels()
    return context
