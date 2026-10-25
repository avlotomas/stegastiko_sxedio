"""Timeline builder for `ActionHistory` entries (§Β.1.3).

Groups consecutive audit rows by the same user within 5 seconds into a single
timeline event, maps entity and field names to Greek labels, formats raw serialized
values readably, and hides automatically recalculated fields declared in
`Model._history_hidden_fields`.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from core.models import ActionHistory
from plot_applications.documents import DOCUMENT_LABELS

GROUP_WINDOW_SECONDS = 5.0

ACTION_LABELS = {
    ActionHistory.ActionType.CREATE: "Δημιουργία",
    ActionHistory.ActionType.UPDATE: "Τροποποίηση",
    ActionHistory.ActionType.DELETE: "Διαγραφή",
    ActionHistory.ActionType.CANCEL: "Ακύρωση",
}

ENTITY_LABELS = {
    "PlotApplication": "Αίτηση",
    "ApplicationParty": "Στοιχεία προσώπου αίτησης",
    "ApplicationChild": "7. Τέκνο",
    "IncomeDeclaration": "8. Εισόδημα",
    "Person": "Άτομο",
    "Case": "Υπόθεση",
    "CompletenessCheck": "2.1 Έλεγχος πληρότητας",
    "LandPlot": "3.1 Τεμάχιο",
    "UtilityService": "4.2 Υπηρεσία κοινής ωφέλειας",
    "UtilityServiceType": "4.2 Τύπος υπηρεσίας κοινής ωφέλειας",
    "Consultation": "5 / 7.4 Διαβούλευση",
    "MinistryDecisionRound": "6.7 Σύσταση / Απόφαση ΥΠΕΣ",
    "ApprovedDesignPlot": "7.3 Οικόπεδο σχεδιασμού",
    "InfrastructureCheck": "7.6 Έλεγχος κατασκευαστικών εργασιών",
    "Field": "8.2 Χωράφι",
    "ValuationReferral": "8.2 Παραπομπή ΤΚΧ",
    "SubmissionCycle": "9.1 Γνωστοποίηση",
    "SubmissionCyclePublication": "9.2 Δημοσιοποίηση γνωστοποίησης",
    "Plot": "Οικόπεδο",
    "RankingList": "Κατάλογος κατάταξης",
    "RankingEntry": "Κατάταξη αίτησης",
    "Lottery": "Κλήρωση",
    "Allocation": "Κατανομή οικοπέδου",
    "Payment": "Πληρωμή",
    "Agreement": "Σύμβαση",
    "TitleTransfer": "Μεταβίβαση τίτλου",
    "ConstructionMonitoring": "Παρακολούθηση ανέγερσης",
    "Attachment": "Αρχείο",
    "Communication": "Email",
    "Community": "Κοινότητα",
    "Role": "Ρόλος",
    "User": "Χρήστης",
    "SystemSetting": "Ρύθμιση συστήματος",
}

EXTRA_FIELD_LABELS: dict[tuple[str, str], str] = {
    ("PlotApplication", "protocol_number"): "Αριθμός πρωτοκόλλου",
    ("PlotApplication", "applicant"): "Αιτητής/Αιτήτρια",
    ("PlotApplication", "spouse"): "Σύζυγος/Συμβίος",
    ("PlotApplication", "preference_order"): "Σειρά προτεραιότητας αιτήσεων",
    ("PlotApplication", "attached_documents"): "Επισυναπτόμενα δικαιολογητικά",
    ("PlotApplication", "document_notes"): "Σημειώσεις δικαιολογητικών",
    ("PlotApplication", "has_dwelling"): "(α) Εγγεγραμμένη κατοικία (Ενότ. 10.Δ)",
    ("PlotApplication", "has_residential_land"): "(β) Οικόπεδο ή τεμάχιο σε Οικιστική Ζώνη (Ενότ. 10.Δ)",
    ("PlotApplication", "has_alienated_property"): "Αποξένωση ακίνητης ιδιοκτησίας (Ενότ. 10.Ε)",
    ("PlotApplication", "previous_housing_aid"): "Παραχώρηση άλλης κρατικής στεγαστικής βοήθειας (Ενότ. 20.3)",
    ("PlotApplication", "eligibility_override"): "Χειροκίνητη αλλαγή αποτελέσματος επιλεξιμότητας (Ενότ. 6)",
    ("PlotApplication", "eligibility_override_reason"): "Αιτιολογία χειροκίνητης αλλαγής αποτελέσματος (Ενότ. 6)",
    ("PlotApplication", "incomplete_rejected"): "Απόρριψη αίτησης λόγω ελλείψεων (Ενότ. 5(β), 20.2)",
    ("PlotApplication", "incomplete_rejection_reason"): "Αιτιολογία απόρριψης λόγω ελλείψεων (Ενότ. 5(β))",
    ("PlotApplication", "incomplete_rejected_on"): "Ημερομηνία απόρριψης λόγω ελλείψεων",
    ("PlotApplication", "priority_rank"): "Θέση στον κατάλογο προτεραιοποίησης (χειροκίνητη σειρά)",
    ("ApplicationParty", "role"): "Ρόλος",
    ("IncomeDeclaration", "child"): "Τέκνο",
    ("Case", "community"): "1.1 Κοινότητα / Δ.Δ.",
    ("Case", "case_type"): "1.1 Τύπος διαδικασίας",
    ("Case", "completed_at"): "Ολοκλήρωση αίτησης",
    ("Case", "completed_by"): "Χρήστης ολοκλήρωσης",
    ("Attachment", "filename"): "Όνομα αρχείου",
    ("Attachment", "doc_code"): "Κωδικός δικαιολογητικού",
    ("Attachment", "section_ref"): "Ενότητα",
    ("Attachment", "size_bytes"): "Μέγεθος αρχείου (bytes)",
    ("Communication", "channel"): "Κανάλι",
    ("Communication", "recipient"): "Παραλήπτης",
    ("Communication", "subject"): "Θέμα",
    ("Communication", "body"): "Κείμενο",
    ("Communication", "status"): "Κατάσταση",
    ("Communication", "sent_at"): "Ημερομηνία αποστολής",
}


@lru_cache(maxsize=1)
def _models_by_name() -> dict[str, type[models.Model]]:
    return {model.__name__: model for model in apps.get_models()}


@lru_cache(maxsize=1)
def _form_field_labels() -> dict[tuple[str, str], str]:
    from plot_applications.forms import (
        ApplicationChildForm,
        ApplicationPartyForm,
        IncomeDeclarationForm,
        PlotApplicationForm,
    )

    mapping: dict[tuple[str, str], str] = {}
    for form_cls in (
        PlotApplicationForm,
        ApplicationPartyForm,
        ApplicationChildForm,
        IncomeDeclarationForm,
    ):
        meta = getattr(form_cls, "Meta", None)
        model = getattr(meta, "model", None)
        if model is None:
            continue
        model_name = model.__name__
        for field_name, label in (getattr(meta, "labels", None) or {}).items():
            if label:
                mapping[(model_name, field_name)] = str(label)
        for field_name, form_field in getattr(form_cls, "base_fields", {}).items():
            if (model_name, field_name) not in mapping and getattr(form_field, "label", None):
                mapping[(model_name, field_name)] = str(form_field.label)
    mapping.update(EXTRA_FIELD_LABELS)
    return mapping


def _is_hidden_entry(entry: ActionHistory) -> bool:
    if entry.action != ActionHistory.ActionType.UPDATE or not entry.field_name:
        return False
    model = _models_by_name().get(entry.entity_type)
    if model is None:
        return False
    hidden = getattr(model, "_history_hidden_fields", frozenset())
    return entry.field_name in hidden


def _user_display_map(user_ids) -> dict[int, str]:
    clean_ids = {int(uid) for uid in user_ids if uid and str(uid).isdigit()}
    if not clean_ids:
        return {}
    User = get_user_model()
    result: dict[int, str] = {}
    for user in User.objects.filter(pk__in=clean_ids):
        full_name = user.get_full_name().strip()
        result[user.pk] = f"{full_name} ({user.username})" if full_name else user.username
    return result


def _load_existing_instances(entries: list[ActionHistory]) -> dict[tuple[str, str], models.Model]:
    models_map = _models_by_name()
    ids_by_type: dict[str, set[int]] = {}
    for entry in entries:
        if entry.entity_type in models_map and str(entry.entity_id).isdigit():
            ids_by_type.setdefault(entry.entity_type, set()).add(int(entry.entity_id))
    instances: dict[tuple[str, str], models.Model] = {}
    for entity_type, pks in ids_by_type.items():
        model = models_map[entity_type]
        for obj in model.objects.filter(pk__in=pks):
            instances[(entity_type, str(obj.pk))] = obj
    return instances


def _entity_label(entry: ActionHistory, instances: dict[tuple[str, str], models.Model]) -> str:
    base = ENTITY_LABELS.get(entry.entity_type, entry.entity_type)
    obj = instances.get((entry.entity_type, str(entry.entity_id)))
    if obj is None:
        if entry.section_ref and entry.entity_type in {"Attachment", "Consultation"}:
            return f"{base} ({entry.section_ref})"
        return base
    if entry.entity_type == "ApplicationParty":
        return f"Στοιχεία προσώπου ({obj.get_role_display()})"
    if entry.entity_type == "ApplicationChild":
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return f"{base} ({full_name})" if full_name else base
    if entry.entity_type == "IncomeDeclaration":
        return f"{base} ({obj.member_label})"
    if entry.entity_type == "CompletenessCheck":
        return f"{base} ({obj.sequence}ος έλεγχος)"
    if entry.entity_type == "LandPlot":
        return f"{base} ({obj.parcel_number})"
    if entry.entity_type == "UtilityService":
        return f"{base} ({obj.service_type})"
    if entry.entity_type == "Consultation":
        return f"{obj.section_ref} Διαβούλευση ({obj.department_display})"
    if entry.entity_type in {"MinistryDecisionRound", "ApprovedDesignPlot", "InfrastructureCheck", "Plot"}:
        return f"{base} ({obj.row_label})"
    if entry.entity_type == "Field":
        return f"{base} ({obj.code})"
    if entry.entity_type == "Attachment":
        return f"{base} ({obj.filename})"
    if entry.entity_type == "Communication":
        return f"{base} ({obj.recipient})"
    return base


def _get_model_field(entity_type: str, field_name: str):
    if not field_name:
        return None
    model = _models_by_name().get(entity_type)
    if model is None:
        return None
    try:
        return model._meta.get_field(field_name)
    except Exception:
        return None


def get_field_label(entity_type: str, field_name: str) -> str:
    if not field_name:
        return ""
    labels = _form_field_labels()
    if (entity_type, field_name) in labels:
        return labels[(entity_type, field_name)]
    field = _get_model_field(entity_type, field_name)
    if field is not None:
        help_text = str(getattr(field, "help_text", "") or "").strip()
        if help_text:
            return help_text
        verbose = str(getattr(field, "verbose_name", "") or "").strip()
        if verbose and verbose != field_name.replace("_", " "):
            return verbose
    return field_name


def _format_iso_date(raw: str) -> str | None:
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    return parsed.strftime("%d/%m/%Y")


def _format_iso_datetime(raw: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.strftime("%d/%m/%Y %H:%M")


def _format_scalar_value(entity_type: str, field_name: str, raw: str, fk_cache: dict[tuple[type, str], str]) -> str:
    if raw is None or raw == "":
        return "—"
    field = _get_model_field(entity_type, field_name)
    if field is not None:
        if getattr(field, "choices", None):
            choice_map = {str(k): str(v) for k, v in field.flatchoices}
            if raw in choice_map:
                return choice_map[raw]
        if isinstance(field, models.BooleanField):
            if raw == "True":
                return "Ναι"
            if raw == "False":
                return "Όχι"
        if isinstance(field, models.DateTimeField):
            formatted = _format_iso_datetime(raw)
            if formatted:
                return formatted
        elif isinstance(field, models.DateField):
            formatted = _format_iso_date(raw)
            if formatted:
                return formatted
        if isinstance(field, (models.ForeignKey, models.OneToOneField, models.ManyToManyField)):
            rel_model = field.remote_field.model
            cache_key = (rel_model, raw)
            if cache_key not in fk_cache:
                obj = rel_model.objects.filter(pk=raw).first() if str(raw).isdigit() else None
                fk_cache[cache_key] = str(obj) if obj is not None else f"#{raw}"
            return fk_cache[cache_key]

    if raw == "True":
        return "Ναι"
    if raw == "False":
        return "Όχι"
    if len(raw) == 10 and raw[4:5] == "-" and raw[7:8] == "-":
        formatted_date = _format_iso_date(raw)
        if formatted_date:
            return formatted_date
    return raw


def _attached_documents_diff(old_raw: str, new_raw: str) -> tuple[str, str]:
    try:
        old_codes = json.loads(old_raw or "[]")
    except (ValueError, TypeError):
        old_codes = []
    try:
        new_codes = json.loads(new_raw or "[]")
    except (ValueError, TypeError):
        new_codes = []
    old_set = set(old_codes)
    new_set = set(new_codes)
    removed = [DOCUMENT_LABELS.get(code, code) for code in old_codes if code not in new_set]
    added = [DOCUMENT_LABELS.get(code, code) for code in new_codes if code not in old_set]
    return ("\n".join(removed) or "—"), ("\n".join(added) or "—")


def _format_document_notes(raw: str) -> str:
    if not raw:
        return "—"
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if not isinstance(data, dict) or not data:
        return "—"
    lines = [f"{DOCUMENT_LABELS.get(code, code)}: {note}" for code, note in data.items() if note]
    return "\n".join(lines) if lines else "—"


def _format_change_values(entry: ActionHistory, fk_cache: dict[tuple[type, str], str]) -> tuple[str, str]:
    if entry.entity_type == "PlotApplication" and entry.field_name == "attached_documents":
        return _attached_documents_diff(entry.old_value, entry.new_value)
    if entry.entity_type == "PlotApplication" and entry.field_name == "document_notes":
        return _format_document_notes(entry.old_value), _format_document_notes(entry.new_value)
    return (
        _format_scalar_value(entry.entity_type, entry.field_name, entry.old_value, fk_cache),
        _format_scalar_value(entry.entity_type, entry.field_name, entry.new_value, fk_cache),
    )


def _group_entries(entries: list[ActionHistory]) -> list[list[ActionHistory]]:
    groups: list[list[ActionHistory]] = []
    for entry in entries:
        if not groups:
            groups.append([entry])
            continue
        current_group = groups[-1]
        prev_entry = current_group[-1]
        delta = abs((prev_entry.timestamp - entry.timestamp).total_seconds())
        if entry.user_id == prev_entry.user_id and delta < GROUP_WINDOW_SECONDS:
            current_group.append(entry)
        else:
            groups.append([entry])
    return groups


def _event_action(group: list[ActionHistory]) -> str:
    actions = {entry.action for entry in group}
    if len(actions) == 1:
        return next(iter(actions))
    for entry in group:
        if entry.entity_type in {"PlotApplication", "Case"} and entry.action in {
            ActionHistory.ActionType.CREATE,
            ActionHistory.ActionType.DELETE,
            ActionHistory.ActionType.CANCEL,
        }:
            return entry.action
    return ActionHistory.ActionType.UPDATE


def build_timeline(entries) -> list[dict]:
    """Group `ActionHistory` rows into human-readable timeline events (newest first)."""
    visible_entries = [entry for entry in entries if not _is_hidden_entry(entry)]
    if not visible_entries:
        return []

    users_map = _user_display_map(entry.user_id for entry in visible_entries)
    instances = _load_existing_instances(visible_entries)
    fk_cache: dict[tuple[type, str], str] = {}
    groups = _group_entries(visible_entries)

    events: list[dict] = []
    for group in groups:
        ordered = list(reversed(group))
        has_root_create = any(
            e.entity_type in {"PlotApplication", "Case"}
            and e.action == ActionHistory.ActionType.CREATE
            for e in ordered
        )
        changes: list[dict] = []
        for entry in ordered:
            if (
                has_root_create
                and entry.entity_type == "ApplicationParty"
                and entry.action == ActionHistory.ActionType.CREATE
                and not entry.field_name
            ):
                continue
            entity_label = _entity_label(entry, instances)
            action_label = ACTION_LABELS.get(entry.action, entry.action)
            if entry.field_name:
                old_val, new_val = _format_change_values(entry, fk_cache)
                if (
                    entry.entity_type == "PlotApplication"
                    and entry.field_name == "attached_documents"
                    and old_val == "—"
                    and new_val == "—"
                ):
                    continue
                changes.append(
                    {
                        "entity_type": entry.entity_type,
                        "entity_label": entity_label,
                        "action": entry.action,
                        "action_label": action_label,
                        "field_name": entry.field_name,
                        "field_label": get_field_label(entry.entity_type, entry.field_name),
                        "old_value": old_val,
                        "new_value": new_val,
                        "is_field_update": True,
                    }
                )
            else:
                changes.append(
                    {
                        "entity_type": entry.entity_type,
                        "entity_label": entity_label,
                        "action": entry.action,
                        "action_label": action_label,
                        "field_name": "",
                        "field_label": "",
                        "old_value": "",
                        "new_value": "",
                        "is_field_update": False,
                    }
                )

        if not changes:
            continue

        head = group[0]
        event_act = _event_action(ordered)
        actor = users_map.get(head.user_id, f"Χρήστης #{head.user_id}") if head.user_id else "Σύστημα"
        events.append(
            {
                "timestamp": head.timestamp,
                "user_id": head.user_id,
                "actor": actor,
                "action": event_act,
                "action_label": ACTION_LABELS.get(event_act, event_act),
                "changes": changes,
            }
        )
    return events
