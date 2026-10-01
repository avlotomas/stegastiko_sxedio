from django.contrib.auth.models import Group, Permission
from django.db.models import Q


ROLE_OFFICER = "Λειτουργός καταχώρισης"
ROLE_SUPERVISOR = "Προϊστάμενος ελέγχου"
ROLE_COMMITTEE = "Μέλος Επιτροπής"
ROLE_DISTRICT_ADMIN = "Έπαρχος"
ROLE_SYSTEM_ADMIN = "Διαχειριστής"
ROLE_READ_ONLY = "Μόνο ανάγνωση"


ROLE_NAMES = [
    ROLE_OFFICER,
    ROLE_SUPERVISOR,
    ROLE_COMMITTEE,
    ROLE_DISTRICT_ADMIN,
    ROLE_SYSTEM_ADMIN,
    ROLE_READ_ONLY,
]


def user_is_system_admin(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=ROLE_SYSTEM_ADMIN).exists()


def ensure_groups():
    groups = {}
    for role_name in ROLE_NAMES:
        group, _ = Group.objects.get_or_create(name=role_name)
        groups[role_name] = group

    # Start from empty permissions for deterministic behavior.
    for group in groups.values():
        group.permissions.clear()

    add_change_view = Permission.objects.filter(
        Q(codename__startswith="add_")
        | Q(codename__startswith="change_")
        | Q(codename__startswith="view_")
    )
    view_only = Permission.objects.filter(codename__startswith="view_")

    groups[ROLE_SYSTEM_ADMIN].permissions.set(add_change_view)
    groups[ROLE_OFFICER].permissions.set(add_change_view)
    groups[ROLE_SUPERVISOR].permissions.set(add_change_view)
    groups[ROLE_COMMITTEE].permissions.set(view_only)
    groups[ROLE_DISTRICT_ADMIN].permissions.set(view_only)
    groups[ROLE_READ_ONLY].permissions.set(view_only)
