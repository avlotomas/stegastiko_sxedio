"""Settings screens «Χρήστες» and «Ρόλοι και δικαιώματα» (§Β.3)."""

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from core.access_forms import RoleForm, UserForm
from core.access_history import role_history_rows, user_history_rows
from core.audit import record_user_changes, user_audit_snapshot
from core.function_catalog import CREATE, DELETE, EDIT, FUNCTIONS_BY_CODE
from core.models import Role
from core.permissions import access_required, has_access
from core.settings_navigation import settings_nav


def _active_grants_count(role):
    return sum(1 for key in role.grants or () if key.partition(":")[0] in FUNCTIONS_BY_CODE)


@access_required("settings_users")
def user_list(request):
    users = (
        get_user_model()
        .objects.order_by("username")
        .prefetch_related(Prefetch("app_roles", queryset=Role.objects.order_by("name")))
    )
    return render(
        request,
        "core/settings/users.html",
        {
            "users": users,
            "settings_nav": settings_nav(request.user, "users"),
            "can_create": has_access(request.user, "settings_users", CREATE),
            "can_edit": has_access(request.user, "settings_users", EDIT),
        },
    )


def _user_form_page(request, form, target):
    return render(
        request,
        "core/settings/user_form.html",
        {
            "form": form,
            "target": target,
            "settings_nav": settings_nav(request.user, "users"),
            "history_rows": user_history_rows(target) if target else [],
        },
    )


@access_required("settings_users", CREATE)
def user_create(request):
    if request.method == "POST":
        form = UserForm(request.POST, acting_user=request.user)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                record_user_changes(user)
            messages.success(request, f"Δημιουργήθηκε ο χρήστης {user.username}.")
            return redirect("settings_user_edit", pk=user.pk)
    else:
        form = UserForm(acting_user=request.user, initial={"is_active": True})
    return _user_form_page(request, form, None)


@access_required("settings_users", EDIT)
def user_edit(request, pk):
    target = get_object_or_404(get_user_model(), pk=pk)
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, "Ο λογαριασμός υπερχρήστη αλλάζει μόνο από υπερχρήστη.")
        return redirect("settings_users")
    if request.method == "POST":
        previous = user_audit_snapshot(target)
        form = UserForm(request.POST, instance=target, acting_user=request.user)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                record_user_changes(user, previous, password_changed=form.password_changed)
            if user.pk == request.user.pk and form.password_changed:
                update_session_auth_hash(request, user)
            messages.success(request, f"Ο χρήστης {user.username} ενημερώθηκε.")
            return redirect("settings_user_edit", pk=user.pk)
    else:
        form = UserForm(instance=target, acting_user=request.user)
    return _user_form_page(request, form, target)


@access_required("settings_roles")
def role_list(request):
    roles = Role.objects.annotate(members_count=Count("members")).order_by("name")
    for role in roles:
        role.grants_count = _active_grants_count(role)
    return render(
        request,
        "core/settings/roles.html",
        {
            "roles": roles,
            "settings_nav": settings_nav(request.user, "roles"),
            "can_create": has_access(request.user, "settings_roles", CREATE),
        },
    )


def _role_form_page(request, form, role, *, can_edit):
    if not can_edit:
        for field in form.fields.values():
            field.disabled = True
    return render(
        request,
        "core/settings/role_form.html",
        {
            "form": form,
            "role": role,
            "can_edit": can_edit,
            "can_delete": role is not None and has_access(request.user, "settings_roles", DELETE),
            "members": role.members.order_by("username") if role else [],
            "settings_nav": settings_nav(request.user, "roles"),
            "history_rows": role_history_rows(role) if role else [],
        },
    )


@access_required("settings_roles", CREATE)
def role_create(request):
    if request.method == "POST":
        form = RoleForm(request.POST, acting_user=request.user)
        if form.is_valid():
            role = form.save()
            messages.success(request, f"Δημιουργήθηκε ο ρόλος «{role.name}».")
            return redirect("settings_role_edit", pk=role.pk)
    else:
        source = None
        copy_id = request.GET.get("copy", "")
        if copy_id.isdigit():
            source = get_object_or_404(Role, pk=copy_id)
        form = RoleForm(
            acting_user=request.user,
            initial={
                "is_active": True,
                "name": f"{source.name} (αντίγραφο)" if source else "",
                "description": source.description if source else "",
            },
            initial_grants=source.grants if source else (),
        )
    return _role_form_page(request, form, None, can_edit=True)


@access_required("settings_roles", post_action=EDIT)
def role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    can_edit = has_access(request.user, "settings_roles", EDIT)
    if request.method == "POST":
        form = RoleForm(request.POST, instance=role, acting_user=request.user)
        if form.is_valid():
            role = form.save()
            messages.success(request, f"Ο ρόλος «{role.name}» αποθηκεύτηκε.")
            return redirect("settings_role_edit", pk=role.pk)
    else:
        form = RoleForm(instance=role, acting_user=request.user)
    return _role_form_page(request, form, role, can_edit=can_edit)


@access_required("settings_roles", DELETE)
def role_delete(request, pk):
    if request.method != "POST":
        raise Http404("Επιτρέπεται μόνο POST.")
    role = get_object_or_404(Role, pk=pk)
    if role.members.exists():
        messages.error(
            request,
            f"Ο ρόλος «{role.name}» έχει χρήστες και δεν διαγράφεται· "
            "αφαιρέστε τους χρήστες ή απενεργοποιήστε τον ρόλο.",
        )
        return redirect("settings_role_edit", pk=role.pk)
    name = role.name
    role.delete()
    messages.success(request, f"Διαγράφηκε ο ρόλος «{name}».")
    return redirect("settings_roles")
