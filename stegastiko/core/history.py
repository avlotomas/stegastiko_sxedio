from core.models import ActionHistory


def history_for_instance(instance):
    return ActionHistory.objects.filter(
        entity_type=instance.__class__.__name__,
        entity_id=str(instance.pk),
    ).order_by("-timestamp", "-id")


def history_for_context(case_id=None, application_id=None):
    queryset = ActionHistory.objects.all()
    if case_id is not None:
        queryset = queryset.filter(case_id=case_id)
    if application_id is not None:
        queryset = queryset.filter(application_id=application_id)
    return queryset.order_by("-timestamp", "-id")
