from django.conf import settings

from core.branding import get_app_subtitle, get_app_title
from core.menu_labels import get_menu_labels
from core.permissions import AccessProxy
from core.ui_texts import (
    UI_EDIT_MODE_SESSION_KEY,
    can_edit_ui_texts,
    get_ui_text_defaults,
    get_ui_text_overrides,
)


def display_version(version):
    """Release tags (1.1.0 or v1.1.0) show as v1.1.0; anything else (dev, a commit) as is."""
    number = version.removeprefix("v")
    if number[:1].isdigit():
        return f"v{number}"
    return version


def ui_flags(request):
    context = {
        "app_title": get_app_title(),
        "app_subtitle": get_app_subtitle(),
        "ui_text_overrides": get_ui_text_overrides(),
        "ui_text_defaults": get_ui_text_defaults(),
        "can_edit_ui_texts": False,
        "ui_edit_mode": False,
        "is_embed": bool(getattr(request, "is_embed", False)),
        "app_version": display_version(settings.APP_VERSION),
    }
    if request.user.is_authenticated:
        context["access"] = AccessProxy(request.user)
        context["menu"] = get_menu_labels()
        can_edit = can_edit_ui_texts(request.user)
        context["can_edit_ui_texts"] = can_edit
        context["ui_edit_mode"] = bool(
            can_edit
            and hasattr(request, "session")
            and request.session.get(UI_EDIT_MODE_SESSION_KEY)
        )
    return context
