"""Forms of the Χρήστες and Ρόλοι και δικαιώματα settings screens (§Β.3)."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError

from core.function_catalog import (
    ACCESS_TYPES,
    EDIT,
    FUNCTIONS,
    function_label,
    grant_key,
)
from core.models import Role
from core.permissions import (
    grant_dependency_errors,
    grants_allow,
    role_grants_for,
    set_user_roles,
)

SELF_LOCKOUT_MESSAGE = (
    "Δεν μπορείτε να αφαιρέσετε από τον εαυτό σας την πρόσβαση «{function}: Τροποποίηση»· "
    "ζητήστε το από άλλο διαχειριστή."
)


def _style(form):
    for field in form.fields.values():
        if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
            field.widget.attrs.setdefault("class", "input")


class RoleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, role):
        return role.name if role.is_active else f"{role.name} (ανενεργός)"


class UserForm(forms.ModelForm):
    roles = RoleChoiceField(
        queryset=Role.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Ρόλοι",
        help_text="Η πρόσβαση του χρήστη είναι η ένωση των δικαιωμάτων των ενεργών ρόλων του.",
    )
    password1 = forms.CharField(
        label="Κωδικός πρόσβασης",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Επιβεβαίωση κωδικού",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_active")
        labels = {
            "username": "Όνομα χρήστη",
            "first_name": "Όνομα",
            "last_name": "Επώνυμο",
            "email": "Email",
            "is_active": "Ενεργός λογαριασμός",
        }
        help_texts = {
            "username": "Μοναδικό· δεν αλλάζει μετά τη δημιουργία.",
            "is_active": "Ανενεργός χρήστης δεν μπορεί να συνδεθεί.",
        }

    def __init__(self, *args, acting_user, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        self.is_create = self.instance.pk is None
        if self.is_create:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
        else:
            self.fields["username"].disabled = True
            self.fields["roles"].initial = list(self.instance.app_roles.values_list("pk", flat=True))
            self.fields["password1"].label = "Νέος κωδικός πρόσβασης"
            self.fields["password1"].help_text = "Συμπληρώστε μόνο για αλλαγή κωδικού."
            self.fields["password2"].label = "Επιβεβαίωση νέου κωδικού"
        _style(self)

    @property
    def password_changed(self):
        return bool(self.cleaned_data.get("password1"))

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Οι δύο κωδικοί δεν ταιριάζουν.")
            else:
                try:
                    password_validation.validate_password(password1, self.instance)
                except ValidationError as exc:
                    self.add_error("password1", exc)

        if self.instance.pk and self.instance.pk == self.acting_user.pk and not self.acting_user.is_superuser:
            if not cleaned.get("is_active", True):
                self.add_error("is_active", "Δεν μπορείτε να απενεργοποιήσετε τον δικό σας λογαριασμό.")
            grants = role_grants_for(cleaned.get("roles") or [])
            if not grants_allow(grants, "settings_users", EDIT):
                raise ValidationError(SELF_LOCKOUT_MESSAGE.format(function="Χρήστες"))
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.password_changed:
            user.set_password(self.cleaned_data["password1"])
        user.save()
        set_user_roles(user, self.cleaned_data.get("roles") or [])
        return user


def grant_field_name(code: str, action: str) -> str:
    return f"grant__{code}__{action}"


class RoleForm(forms.ModelForm):
    """Role details plus one checkbox per function / sub-function and access type."""

    class Meta:
        model = Role
        fields = ("name", "description", "is_active")
        labels = {
            "name": "Ονομασία ρόλου",
            "description": "Περιγραφή",
            "is_active": "Ενεργός ρόλος",
        }
        help_texts = {
            "name": "",
            "description": "",
            "is_active": "Ανενεργός ρόλος δεν δίνει πρόσβαση στα μέλη του.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, acting_user, initial_grants=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        grants = set(self.instance.grants or ()) if initial_grants is None else set(initial_grants)
        for function in FUNCTIONS:
            for action in function.actions:
                self.fields[grant_field_name(function.code, action)] = forms.BooleanField(
                    required=False,
                    initial=grant_key(function.code, action) in grants,
                    label=f"{function_label(function)}: {dict(ACCESS_TYPES)[action]}",
                )
        _style(self)

    def detail_fields(self):
        return [self[name] for name in ("name", "description", "is_active")]

    def access_columns(self):
        used = {action for function in FUNCTIONS for action in function.actions}
        return [(action, label) for action, label in ACCESS_TYPES if action in used]

    def matrix_rows(self):
        columns = [action for action, _ in self.access_columns()]
        rows = []
        for function in FUNCTIONS:
            cells = [
                self[grant_field_name(function.code, action)] if action in function.actions else None
                for action in columns
            ]
            rows.append(
                {
                    "function": function,
                    "label": function_label(function),
                    "is_child": bool(function.parent),
                    "group": function.parent or function.code,
                    "cells": cells,
                }
            )
        return rows

    def selected_grants(self) -> list:
        return sorted(
            grant_key(function.code, action)
            for function in FUNCTIONS
            for action in function.actions
            if self.cleaned_data.get(grant_field_name(function.code, action))
        )

    def clean(self):
        cleaned = super().clean()
        grants = set(self.selected_grants())
        for message in grant_dependency_errors(grants):
            self.add_error(None, message)

        acting = self.acting_user
        if self.instance.pk and not acting.is_superuser and self.instance.members.filter(pk=acting.pk).exists():
            other_roles = acting.app_roles.exclude(pk=self.instance.pk)
            remaining = set(role_grants_for(other_roles))
            if cleaned.get("is_active"):
                remaining |= grants
            if not grants_allow(remaining, "settings_roles", EDIT):
                raise ValidationError(SELF_LOCKOUT_MESSAGE.format(function="Ρόλοι και δικαιώματα"))
        return cleaned

    def save(self, commit=True):
        role = super().save(commit=False)
        role.grants = self.selected_grants()
        role.save()
        return role
