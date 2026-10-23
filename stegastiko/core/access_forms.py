"""Forms of the Χρήστες and Ρόλοι και δικαιώματα settings screens (§Β.3)."""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.function_catalog import (
    ACCESS_TYPES,
    CONFIGURABLE_FUNCTION_CODES,
    EDIT,
    FUNCTIONS,
    FUNCTIONS_BY_CODE,
    PLOT_APPLICATION_ACTION_LABELS,
    PLOT_APPLICATION_SUBFUNCTION_CODES,
    PLOT_APPLICATION_SUBSECTIONS,
    VIEW,
    action_label_for,
    function_label,
    grant_key,
    plot_app_subsection_code,
)
from core.models import Role, set_must_change_password, user_must_change_password
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
    must_change_password = forms.BooleanField(
        label="Υποχρεωτική αλλαγή κωδικού στην επόμενη σύνδεση",
        required=False,
        help_text="Αν ενεργοποιηθεί, ο χρήστης θα πρέπει να ορίσει νέο κωδικό πρόσβασης αμέσως μόλις συνδεθεί.",
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
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
            self.fields["must_change_password"].initial = user_must_change_password(self.instance)
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
        set_must_change_password(user, bool(self.cleaned_data.get("must_change_password")))
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
        self._base_grants = set(grants)

        implicit_subsections = set()
        for action in (VIEW, EDIT):
            if grant_key("plot_applications", action) in grants and not any(
                grant_key(sub_code, action) in grants
                for sub_code in PLOT_APPLICATION_SUBFUNCTION_CODES
            ):
                for sub_code in PLOT_APPLICATION_SUBFUNCTION_CODES:
                    implicit_subsections.add(grant_key(sub_code, action))
        effective_initial_grants = grants | implicit_subsections

        for function in FUNCTIONS:
            for action in function.actions:
                attrs = {"class": "checkbox"}
                if function.code == "plot_applications" and action in (VIEW, EDIT):
                    attrs["data-action-with-subsections"] = action
                self.fields[grant_field_name(function.code, action)] = forms.BooleanField(
                    required=False,
                    initial=grant_key(function.code, action) in effective_initial_grants,
                    label=f"{function_label(function)}: {action_label_for(function.code, action)}",
                    widget=forms.CheckboxInput(attrs=attrs),
                )
        _style(self)

    def detail_fields(self):
        return [self[name] for name in ("name", "description", "is_active")]

    def function_panels(self):
        panels = []
        for code in CONFIGURABLE_FUNCTION_CODES:
            function = FUNCTIONS_BY_CODE[code]
            if code == "plot_applications":
                action_items = []
                for action, action_label in PLOT_APPLICATION_ACTION_LABELS:
                    field = self[grant_field_name(code, action)]
                    subsections = []
                    if action in (VIEW, EDIT):
                        for sub_code, sub_label in PLOT_APPLICATION_SUBSECTIONS:
                            sub_func_code = plot_app_subsection_code(sub_code)
                            sub_field = self[grant_field_name(sub_func_code, action)]
                            subsections.append(
                                {
                                    "code": sub_code,
                                    "label": sub_label,
                                    "field": sub_field,
                                }
                            )
                    is_checked = bool(field.value())
                    all_checked = bool(subsections) and all(
                        bool(item["field"].value()) for item in subsections
                    )
                    action_items.append(
                        {
                            "action": action,
                            "label": action_label,
                            "field": field,
                            "is_checked": is_checked,
                            "subsections": subsections,
                            "all_checked": all_checked,
                        }
                    )
                panels.append(
                    {
                        "code": code,
                        "label": function_label(function),
                        "description": function.description,
                        "actions": action_items,
                    }
                )
        return panels

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
        configured = set(self.data.getlist("configured_functions")) if self.is_bound else set()
        partial_mode = bool(configured)
        selected = set()

        for function in FUNCTIONS:
            if partial_mode and function.code not in configured and (
                function.parent not in configured
            ):
                continue
            for action in function.actions:
                if self.cleaned_data.get(grant_field_name(function.code, action)):
                    selected.add(grant_key(function.code, action))

        for action in (VIEW, EDIT):
            if grant_key("plot_applications", action) not in selected:
                selected = {
                    g
                    for g in selected
                    if not (
                        g.partition(":")[0] in PLOT_APPLICATION_SUBFUNCTION_CODES
                        and g.endswith(f":{action}")
                    )
                }

        if partial_mode:
            for existing in self._base_grants:
                code, _, _ = existing.partition(":")
                func = FUNCTIONS_BY_CODE.get(code)
                if func is None:
                    continue
                if func.code not in configured and func.parent not in configured:
                    selected.add(existing)

        return sorted(selected)

    def clean(self):
        cleaned = super().clean()
        configured = set(self.data.getlist("configured_functions")) if self.is_bound else set()
        grants = set(self.selected_grants())
        if "plot_applications" in configured:
            for action, action_label in ((VIEW, "Εμφάνιση"), (EDIT, "Επεξεργασία")):
                if grant_key("plot_applications", action) in grants and not any(
                    grant_key(sub_code, action) in grants
                    for sub_code in PLOT_APPLICATION_SUBFUNCTION_CODES
                ):
                    self.add_error(
                        None,
                        f"«Αίτηση παραχώρησης οικοπέδου»: επιλέξτε τουλάχιστον μία υποενότητα για την «{action_label}».",
                    )
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
