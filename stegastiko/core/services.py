from core.models import SystemSetting


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
