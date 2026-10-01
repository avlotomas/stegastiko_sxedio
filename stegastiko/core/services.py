import smtplib

from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection

from core.models import SystemSetting

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


def get_setting(key: str, default_value: str = "") -> str:
    setting = SystemSetting.objects.filter(key=key).first()
    if setting:
        return setting.value
    return default_value


def set_setting(key: str, value: str, description: str = "") -> None:
    defaults = {"value": value}
    if description:
        defaults["description"] = description
    SystemSetting.objects.update_or_create(key=key, defaults=defaults)


def smtp_settings() -> dict:
    return {key: get_setting(key, default) for key, default in SMTP_SETTING_DEFAULTS.items()}


def smtp_is_configured() -> bool:
    smtp = smtp_settings()
    return bool(smtp["smtpHost"] and smtp["smtpFromEmail"])


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send one plain-text email through the SMTP server configured in the Settings."""
    smtp = smtp_settings()
    if not (smtp["smtpHost"] and smtp["smtpFromEmail"]):
        raise ValidationError(
            "Δεν έχει ρυθμιστεί ο διακομιστής SMTP (Ρυθμίσεις συστήματος)."
        )
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
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=smtp["smtpFromEmail"],
        to=[recipient],
        connection=connection,
    )
    try:
        message.send()
    except (smtplib.SMTPException, OSError) as exc:
        raise ValidationError(f"Αποτυχία αποστολής email: {exc}")
