"""Signal wiring for the per-request SystemSetting memo (core.services.get_setting)."""

from django.core.signals import got_request_exception, request_finished, request_started
from django.db.models.signals import post_delete, post_save

from core.models import SystemSetting
from core.services import begin_settings_memo, end_settings_memo, invalidate_settings_memo


def _request_started(sender, **kwargs):
    begin_settings_memo()


def _request_ended(sender, **kwargs):
    end_settings_memo()


def _setting_changed(sender, **kwargs):
    invalidate_settings_memo()


def connect():
    request_started.connect(_request_started, dispatch_uid="core.settings_memo.start")
    request_finished.connect(_request_ended, dispatch_uid="core.settings_memo.finish")
    got_request_exception.connect(_request_ended, dispatch_uid="core.settings_memo.exception")
    post_save.connect(
        _setting_changed, sender=SystemSetting, dispatch_uid="core.settings_memo.save"
    )
    post_delete.connect(
        _setting_changed, sender=SystemSetting, dispatch_uid="core.settings_memo.delete"
    )
