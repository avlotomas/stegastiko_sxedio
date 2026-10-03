from core.services import get_setting

APP_TITLE_SETTING_KEY = "appTitle"
APP_TITLE_DEFAULT = "Στεγαστικό Σχέδιο"


def get_app_title() -> str:
    value = get_setting(APP_TITLE_SETTING_KEY, APP_TITLE_DEFAULT).strip()
    return value or APP_TITLE_DEFAULT
