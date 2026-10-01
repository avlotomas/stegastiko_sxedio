from core.permissions import user_is_system_admin


def ui_flags(request):
    if not request.user.is_authenticated:
        return {}
    return {"user_is_system_admin": user_is_system_admin(request.user)}
