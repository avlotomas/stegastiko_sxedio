import re
import smtplib
import threading

from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import escape

from core.models import SystemSetting

_BOLD_ITALIC_NOTE_RE = re.compile(r"\*\*\*([^\n*]+?)\*\*\*")


def email_body_to_html(body: str) -> str:
    """Convert plain-text email body with `***note***` markers into HTML with `<strong><em>note</em></strong>`."""
    escaped = escape(body or "")
    formatted = _BOLD_ITALIC_NOTE_RE.sub(r"<strong><em>\1</em></strong>", escaped)
    return formatted.replace("\n", "<br>\n")

SMTP_SECURITY_CHOICES = (
    ("starttls", "STARTTLS"),
    ("ssl", "SSL/TLS"),
    ("none", "Χωρίς κρυπτογράφηση"),
)
SMTP_SETTING_DEFAULTS = {
    "smtpHost": "",
    "smtpPort": "587",
    "smtpSecurity": "starttls",
    "smtpUsername": "",
    "smtpPassword": "",
    "smtpFromEmail": "",
}
SMTP_TIMEOUT_SECONDS = 30


class _SettingsMemo(threading.local):
    """Per-request memo of every SystemSetting (see core.signals).

    While a request is being served (`active`), the first lookup loads all settings in
    one query and later lookups are served from memory, so a page costs O(1) setting
    queries however many labels it renders. Outside a request (management commands,
    direct calls in tests) every lookup reads the database, so values never go stale
    across processes or test transactions. Saving / deleting a setting clears the memo.
    """

    active = False
    values = None


_settings_memo = _SettingsMemo()


def begin_settings_memo() -> None:
    _settings_memo.active = True
    _settings_memo.values = None


def end_settings_memo() -> None:
    _settings_memo.active = False
    _settings_memo.values = None


def invalidate_settings_memo() -> None:
    _settings_memo.values = None


def get_setting(key: str, default_value: str = "") -> str:
    if _settings_memo.active:
        if _settings_memo.values is None:
            _settings_memo.values = dict(SystemSetting.objects.values_list("key", "value"))
        return _settings_memo.values.get(key, default_value)
    setting = SystemSetting.objects.filter(key=key).first()
    if setting:
        return setting.value
    return default_value


def get_settings_by_prefix(prefix: str) -> dict[str, str]:
    if _settings_memo.active:
        if _settings_memo.values is None:
            _settings_memo.values = dict(SystemSetting.objects.values_list("key", "value"))
        return {
            key: value
            for key, value in _settings_memo.values.items()
            if key.startswith(prefix)
        }
    return dict(
        SystemSetting.objects.filter(key__startswith=prefix).values_list("key", "value")
    )


def set_setting(key: str, value: str, description: str = "") -> None:
    defaults = {"value": value}
    if description:
        defaults["description"] = description
    SystemSetting.objects.update_or_create(key=key, defaults=defaults)


def delete_setting(key: str) -> None:
    for setting in SystemSetting.objects.filter(key=key):
        setting.delete()


def smtp_settings() -> dict:
    return {key: get_setting(key, default) for key, default in SMTP_SETTING_DEFAULTS.items()}


def smtp_is_configured() -> bool:
    smtp = smtp_settings()
    return bool(smtp["smtpHost"] and smtp["smtpFromEmail"])


def require_smtp_configured() -> dict:
    """The SMTP settings, or a ValidationError when the server is not configured."""
    smtp = smtp_settings()
    if not (smtp["smtpHost"] and smtp["smtpFromEmail"]):
        raise ValidationError(
            "Δεν έχει ρυθμιστεί ο διακομιστής SMTP (Ρυθμίσεις συστήματος)."
        )
    return smtp


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send one plain-text email through the SMTP server configured in the Settings."""
    smtp = require_smtp_configured()
    try:
        port = int(smtp["smtpPort"])
    except ValueError:
        raise ValidationError("Μη έγκυρη θύρα SMTP (Ρυθμίσεις συστήματος).")
    connection = get_connection(
        host=smtp["smtpHost"],
        port=port,
        username=smtp["smtpUsername"] or None,
        password=smtp["smtpPassword"] or None,
        use_tls=smtp["smtpSecurity"] == "starttls",
        use_ssl=smtp["smtpSecurity"] == "ssl",
        timeout=SMTP_TIMEOUT_SECONDS,
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=smtp["smtpFromEmail"],
        to=[recipient],
        connection=connection,
    )
    if _BOLD_ITALIC_NOTE_RE.search(body or ""):
        message.attach_alternative(email_body_to_html(body), "text/html")
    try:
        message.send()
    except (smtplib.SMTPException, OSError) as exc:
        raise ValidationError(f"Αποτυχία αποστολής email: {exc}")
