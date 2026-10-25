from core.services import get_setting

APP_TITLE_SETTING_KEY = "appTitle"
APP_TITLE_DEFAULT = "Στεγαστικό Σχέδιο"

APP_SUBTITLE_SETTING_KEY = "appSubtitle"
APP_SUBTITLE_DEFAULT = "Επαρχία Λευκωσίας"


def get_app_title() -> str:
    value = get_setting(APP_TITLE_SETTING_KEY, APP_TITLE_DEFAULT).strip()
    return value or APP_TITLE_DEFAULT


def get_app_subtitle() -> str:
    value = get_setting(APP_SUBTITLE_SETTING_KEY, APP_SUBTITLE_DEFAULT).strip()
    return value or APP_SUBTITLE_DEFAULT
