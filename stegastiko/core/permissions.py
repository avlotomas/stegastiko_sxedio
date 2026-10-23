"""Role-based access to application functions (§Β.3).

Access is granted to roles (`Role.grants`) and users receive it only through the roles
they hold. Superusers have every access.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from core.function_catalog import (
    ACCESS_TYPE_LABELS,
    EDIT,
    FUNCTIONS_BY_CODE,
    PLOT_APPLICATION_ACTION_LABEL_MAP,
    PLOT_APPLICATION_SUBFUNCTION_CODES,
    PLOT_APPLICATION_SUBSECTION_CODES,
    VIEW,
    function_label,
    grant_key,
    plot_app_subsection_code,
)
from core.models import Role

GRANTS_CACHE_ATTR = "_role_grants_cache"


def grants_allow(grants, code: str, action: str = VIEW) -> bool:
    """Whether a set of grants opens `action` on `code`, including ancestor checks."""
    function = FUNCTIONS_BY_CODE[code]
    if action not in function.actions:
        raise ValueError(f"{code} has no access type {action}")
    if function.parent == "plot_applications":
        if grant_key("plot_applications", action) not in grants:
            return False
        if grant_key(code, action) in grants:
            return True
        return not any(
            grant_key(sub_func, action) in grants
            for sub_func in PLOT_APPLICATION_SUBFUNCTION_CODES
        )
    if grant_key(code, action) not in grants:
        return False
    parent = function.parent
    while parent:
        if grant_key(parent, VIEW) not in grants:
            return False
        parent = FUNCTIONS_BY_CODE[parent].parent
    return True


def grant_dependency_errors(grants) -> list:
    """Grants that could never take effect: an action without «Προβολή» on the same
    function, or a sub-function without «Προβολή» on its parent."""
    errors = []
    for key in sorted(grants):
        code, _, action = key.partition(":")
        function = FUNCTIONS_BY_CODE.get(code)
        if function is None:
            continue
        if code == "plot_applications":
            continue
        if function.parent == "plot_applications":
            if grant_key("plot_applications", action) not in grants:
                parent = FUNCTIONS_BY_CODE["plot_applications"]
                action_label = PLOT_APPLICATION_ACTION_LABEL_MAP.get(
                    action, ACCESS_TYPE_LABELS.get(action, action)
                )
                message = (
                    f"«{function_label(function)}»: απαιτείται «{action_label}» στη λειτουργία "
                    f"«{function_label(parent)}»."
                )
                if message not in errors:
                    errors.append(message)
            continue
        if action != VIEW and VIEW in function.actions and grant_key(code, VIEW) not in grants:
            errors.append(
                f"«{function_label(function)}»: η πρόσβαση «{ACCESS_TYPE_LABELS[action]}» "
                "απαιτεί και «Προβολή»."
            )
        if function.parent and grant_key(function.parent, VIEW) not in grants:
            parent = FUNCTIONS_BY_CODE[function.parent]
            message = (
                f"«{function_label(function)}»: απαιτείται «Προβολή» στη λειτουργία "
                f"«{function_label(parent)}»."
            )
            if message not in errors:
                errors.append(message)
    return errors


def set_user_roles(user, roles) -> None:
    wanted = {role.pk for role in roles}
    current = set(user.app_roles.values_list("pk", flat=True))
    for role in Role.objects.filter(pk__in=current - wanted):
        role.members.remove(user)
    for role in Role.objects.filter(pk__in=wanted - current):
        role.members.add(user)
    if hasattr(user, GRANTS_CACHE_ATTR):
        delattr(user, GRANTS_CACHE_ATTR)


def role_grants_for(roles) -> frozenset:
    grants = set()
    for role in roles:
        if role.is_active:
            grants.update(role.grants or ())
    return frozenset(grants)


def user_grants(user) -> frozenset:
    cached = getattr(user, GRANTS_CACHE_ATTR, None)
    if cached is None:
        cached = role_grants_for(Role.objects.filter(members=user, is_active=True))
        setattr(user, GRANTS_CACHE_ATTR, cached)
    return cached


def has_access(user, code: str, action: str = VIEW) -> bool:
    if action not in FUNCTIONS_BY_CODE[code].actions:
        raise ValueError(f"{code} has no access type {action}")
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return grants_allow(user_grants(user), code, action)


def has_any_access(user, code: str, actions) -> bool:
    return any(has_access(user, code, action) for action in actions)


def require_access(user, code: str, action: str = VIEW) -> None:
    if not has_access(user, code, action):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")


def access_required(code: str, action: str = VIEW, *, post_action: str | None = None):
    """Login plus `action` on `code`; POST requests need `post_action` when given."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            required = post_action if post_action and request.method == "POST" else action
            require_access(request.user, code, required)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def plot_application_subsection_map(user, action: str = VIEW) -> dict[str, bool]:
    """Map of subsection_code -> bool for `plot_applications` view or edit."""
    return {
        sub_code: has_access(user, plot_app_subsection_code(sub_code), action)
        for sub_code in PLOT_APPLICATION_SUBSECTION_CODES
    }


def editable_plot_application_subsections(user) -> set[str]:
    """Set of subsection codes the user is permitted to edit on a PlotApplication."""
    return {
        sub_code
        for sub_code, allowed in plot_application_subsection_map(user, EDIT).items()
        if allowed
    }


class FunctionAccess:
    """Template helper: `{% if access.case_section_2.delete %}`."""

    def __init__(self, user, code):
        self._user = user
        self._code = code

    def __getitem__(self, action):
        if action == "any":
            function = FUNCTIONS_BY_CODE.get(self._code)
            return bool(function and has_any_access(self._user, self._code, function.actions))
        try:
            return has_access(self._user, self._code, action)
        except ValueError:
            return False


class AccessProxy:
    def __init__(self, user):
        self._user = user

    def __getitem__(self, code):
        if code not in FUNCTIONS_BY_CODE:
            raise KeyError(code)
        return FunctionAccess(self._user, code)
