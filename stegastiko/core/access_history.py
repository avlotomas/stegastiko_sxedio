"""Readable action history for the Χρήστες and Ρόλοι screens (§Β.1.3, §Β.4)."""

import json

from django.contrib.auth import get_user_model
from django.db.models import Q

from core.function_catalog import grant_label
from core.models import ActionHistory, Role

ACTION_LABELS = {
    ActionHistory.ActionType.CREATE: "Δημιουργία",
    ActionHistory.ActionType.UPDATE: "Τροποποίηση",
    ActionHistory.ActionType.DELETE: "Διαγραφή",
    ActionHistory.ActionType.CANCEL: "Ακύρωση",
}

FIELD_LABELS = {
    "username": "Όνομα χρήστη",
    "first_name": "Όνομα",
    "last_name": "Επώνυμο",
    "email": "Email",
    "is_active": "Ενεργός",
    "password": "Κωδικός πρόσβασης",
    "name": "Ονομασία ρόλου",
    "description": "Περιγραφή",
    "grants": "Δικαιώματα",
    "members": "Μέλη",
}


def _usernames(ids):
    ids = {int(value) for value in ids if str(value).isdigit()}
    return dict(get_user_model().objects.filter(pk__in=ids).values_list("pk", "username"))


def _grants_change(old_value, new_value):
    old = set(json.loads(old_value or "[]"))
    new = set(json.loads(new_value or "[]"))
    removed = "\n".join(grant_label(key) for key in sorted(old - new))
    added = "\n".join(grant_label(key) for key in sorted(new - old))
    return removed, added


def _row(entry, usernames, field_label=None, old_value=None, new_value=None):
    return {
        "timestamp": entry.timestamp,
        "action": ACTION_LABELS.get(entry.action, entry.action),
        "field": field_label if field_label is not None else FIELD_LABELS.get(entry.field_name, entry.field_name),
        "old_value": entry.old_value if old_value is None else old_value,
        "new_value": entry.new_value if new_value is None else new_value,
        "actor": usernames.get(entry.user_id, "—") if entry.user_id else "—",
    }


def role_history_rows(role):
    entries = list(
        ActionHistory.objects.filter(entity_type="Role", entity_id=str(role.pk)).order_by("-timestamp", "-id")
    )
    member_ids = [e.old_value or e.new_value for e in entries if e.field_name == "members"]
    usernames = _usernames([e.user_id for e in entries if e.user_id] + member_ids)
    rows = []
    for entry in entries:
        if entry.field_name == "grants":
            removed, added = _grants_change(entry.old_value, entry.new_value)
            rows.append(_row(entry, usernames, old_value=removed, new_value=added))
        elif entry.field_name == "members":
            member = lambda value: usernames.get(int(value), value) if value.isdigit() else value
            rows.append(
                _row(entry, usernames, old_value=member(entry.old_value), new_value=member(entry.new_value))
            )
        else:
            rows.append(_row(entry, usernames))
    return rows


def user_history_rows(user):
    pk = str(user.pk)
    entries = list(
        ActionHistory.objects.filter(
            Q(entity_type="User", entity_id=pk)
            | Q(entity_type="Role", field_name="members", old_value=pk)
            | Q(entity_type="Role", field_name="members", new_value=pk)
        ).order_by("-timestamp", "-id")
    )
    usernames = _usernames([e.user_id for e in entries if e.user_id])
    role_ids = {int(e.entity_id) for e in entries if e.entity_type == "Role"}
    role_names = dict(Role.objects.filter(pk__in=role_ids).values_list("pk", "name"))
    rows = []
    for entry in entries:
        if entry.entity_type == "Role":
            role_name = role_names.get(int(entry.entity_id), f"#{entry.entity_id}")
            rows.append(
                _row(
                    entry,
                    usernames,
                    field_label="Ρόλοι",
                    old_value=role_name if entry.old_value else "",
                    new_value=role_name if entry.new_value else "",
                )
            )
        else:
            rows.append(_row(entry, usernames))
    return rows
