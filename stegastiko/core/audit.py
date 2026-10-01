from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from core.middleware import get_current_user
from core.models import ActionHistory, AuditedModel, serialize_field_value


def _is_audited_instance(instance):
    return isinstance(instance, AuditedModel)


def _trackable_fields(instance):
    return [
        field
        for field in instance._meta.concrete_fields
        if field.name not in {"id", "created_at", "updated_at"}
    ]


def _persist_history(instance, action, field_name="", old_value="", new_value=""):
    user = get_current_user()
    user_id = user.id if user and user.is_authenticated else None
    case_id, application_id, section_ref = instance._audit_context()
    ActionHistory.objects.create(
        entity_type=instance.__class__.__name__,
        entity_id=str(instance.pk or ""),
        action=action,
        field_name=field_name,
        old_value=serialize_field_value(old_value),
        new_value=serialize_field_value(new_value),
        user_id=user_id,
        section_ref=section_ref,
        case_id=case_id,
        application_id=application_id,
    )


@receiver(pre_save)
def audited_pre_save(sender, instance, **kwargs):
    if not _is_audited_instance(instance):
        return
    if instance._state.adding:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    instance._previous_values = {
        field.name: getattr(previous, field.attname)
        for field in _trackable_fields(instance)
    }


@receiver(post_save)
def audited_post_save(sender, instance, created, **kwargs):
    if not _is_audited_instance(instance):
        return
    if created:
        _persist_history(instance, ActionHistory.ActionType.CREATE)
        return
    previous_values = getattr(instance, "_previous_values", {})
    for field in _trackable_fields(instance):
        old_value = previous_values.get(field.name)
        new_value = getattr(instance, field.attname)
        if old_value != new_value:
            _persist_history(
                instance,
                ActionHistory.ActionType.UPDATE,
                field_name=field.name,
                old_value=instance._audit_value(field.name, old_value),
                new_value=instance._audit_value(field.name, new_value),
            )


@receiver(post_delete)
def audited_post_delete(sender, instance, **kwargs):
    if not _is_audited_instance(instance):
        return
    _persist_history(instance, ActionHistory.ActionType.DELETE)


@receiver(m2m_changed)
def audited_m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Many-to-many links are not concrete fields, so they need their own audit event."""
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if not _is_audited_instance(instance):
        return
    field_name = sender._meta.db_table
    for field in instance._meta.many_to_many:
        if field.remote_field.through is sender:
            field_name = field.name
            break

    if action == "post_clear":
        _persist_history(
            instance, ActionHistory.ActionType.UPDATE, field_name=field_name, old_value="*", new_value=""
        )
        return

    for pk in sorted(pk_set or ()):
        if action == "post_add":
            _persist_history(
                instance, ActionHistory.ActionType.UPDATE, field_name=field_name, new_value=pk
            )
        else:
            _persist_history(
                instance, ActionHistory.ActionType.UPDATE, field_name=field_name, old_value=pk
            )
