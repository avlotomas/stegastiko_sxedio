"""In-place UI text customization and Edit Mode (§Α.9.1)."""

import re

from django.core.exceptions import PermissionDenied, ValidationError

from cases.section_labels import (
    CASE_SECTION_LABEL_SETTING_PREFIX,
    DEFAULT_CASE_SECTION_LABELS,
    get_case_section_label,
    save_case_section_label,
)
from cases.subsection_labels import (
    CASE_SUBSECTION_LABEL_SETTING_PREFIX,
    DEFAULT_CASE_SUBSECTION_LABELS,
    get_case_subsection_label,
    save_case_subsection_label,
)
from core.branding import (
    APP_SUBTITLE_DEFAULT,
    APP_SUBTITLE_SETTING_KEY,
    APP_TITLE_DEFAULT,
    APP_TITLE_SETTING_KEY,
    get_app_subtitle,
    get_app_title,
)
from core.function_catalog import EDIT
from core.menu_labels import (
    DEFAULT_MENU_LABELS,
    MENU_LABEL_FIELDS,
    MENU_LABEL_SETTING_PREFIX,
    get_menu_labels,
    save_menu_label,
)
from core.permissions import has_access, require_access
from core.services import delete_setting, get_settings_by_prefix, set_setting
from plot_applications.stage_labels import (
    APPLICATION_STAGE_LABEL_SETTING_PREFIX,
    DEFAULT_APPLICATION_STAGE_LABELS,
    get_application_stage_label,
    save_application_stage_label,
)

UI_TEXT_SETTING_PREFIX = "uiText."
UI_EDIT_MODE_SESSION_KEY = "ui_edit_mode"

UI_TEXT_EDIT_FUNCTIONS = (
    "settings_branding",
    "settings_menu_labels",
    "settings_section_labels",
    "settings_subsection_labels",
    "settings_plot_application_labels",
)

_UI_TEXT_KEY_RE = re.compile(r"^uiText\.[A-Za-z0-9_.-]{1,56}$")
_MENU_DESCRIPTIONS = {key: description for key, _, description in MENU_LABEL_FIELDS}


def can_edit_ui_texts(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return any(has_access(user, func, EDIT) for func in UI_TEXT_EDIT_FUNCTIONS)


def require_ui_text_edit_access(user) -> None:
    if not can_edit_ui_texts(user):
        raise PermissionDenied("Δεν έχετε πρόσβαση σε αυτή τη λειτουργία.")


def get_ui_text_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {
        APP_TITLE_SETTING_KEY: APP_TITLE_DEFAULT,
        APP_SUBTITLE_SETTING_KEY: APP_SUBTITLE_DEFAULT,
    }
    for key, default in DEFAULT_MENU_LABELS.items():
        defaults[f"{MENU_LABEL_SETTING_PREFIX}{key}"] = default
    for key, default in DEFAULT_CASE_SECTION_LABELS.items():
        defaults[f"{CASE_SECTION_LABEL_SETTING_PREFIX}{key}"] = default
    for key, default in DEFAULT_CASE_SUBSECTION_LABELS.items():
        defaults[f"{CASE_SUBSECTION_LABEL_SETTING_PREFIX}{key}"] = default
    for key, default in DEFAULT_APPLICATION_STAGE_LABELS.items():
        defaults[f"{APPLICATION_STAGE_LABEL_SETTING_PREFIX}{key}"] = default
    return defaults


def get_ui_text_overrides() -> dict[str, str]:
    overrides = {
        key: value
        for key, value in get_settings_by_prefix(UI_TEXT_SETTING_PREFIX).items()
        if value.strip()
    }
    app_title = get_app_title()
    if app_title != APP_TITLE_DEFAULT:
        overrides[APP_TITLE_SETTING_KEY] = app_title
    app_subtitle = get_app_subtitle()
    if app_subtitle != APP_SUBTITLE_DEFAULT:
        overrides[APP_SUBTITLE_SETTING_KEY] = app_subtitle
    for key, label in get_menu_labels().items():
        if label != DEFAULT_MENU_LABELS.get(key):
            overrides[f"{MENU_LABEL_SETTING_PREFIX}{key}"] = label
    for key, default in DEFAULT_CASE_SECTION_LABELS.items():
        current = get_case_section_label(key)
        if current != default:
            overrides[f"{CASE_SECTION_LABEL_SETTING_PREFIX}{key}"] = current
    for key, default in DEFAULT_CASE_SUBSECTION_LABELS.items():
        current = get_case_subsection_label(key)
        if current != default:
            overrides[f"{CASE_SUBSECTION_LABEL_SETTING_PREFIX}{key}"] = current
    for key, default in DEFAULT_APPLICATION_STAGE_LABELS.items():
        current = get_application_stage_label(key)
        if current != default:
            overrides[f"{APPLICATION_STAGE_LABEL_SETTING_PREFIX}{key}"] = current
    return overrides


def _require_non_empty_text(value: str, max_length: int = 2000) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError("Το κείμενο δεν μπορεί να είναι κενό.")
    if len(cleaned) > max_length:
        raise ValidationError(f"Το κείμενο υπερβαίνει τους {max_length} χαρακτήρες.")
    return cleaned


def save_ui_text_entry(
    user,
    key: str,
    value: str = "",
    description: str = "",
    *,
    reset: bool = False,
) -> str:
    require_ui_text_edit_access(user)
    key = (key or "").strip()
    if not key or len(key) > 64:
        raise ValidationError("Μη έγκυρο κλειδί κειμένου.")

    if key in (APP_TITLE_SETTING_KEY, APP_SUBTITLE_SETTING_KEY):
        require_access(user, "settings_branding", EDIT)
        default = (
            APP_TITLE_DEFAULT if key == APP_TITLE_SETTING_KEY else APP_SUBTITLE_DEFAULT
        )
        desc = (
            "Τίτλος εφαρμογής (κεφαλίδα, πάνω αριστερά)"
            if key == APP_TITLE_SETTING_KEY
            else "Υπότιτλος εφαρμογής (κεφαλίδα, πάνω αριστερά)"
        )
        cleaned = default if reset else _require_non_empty_text(value, max_length=512)
        set_setting(key, cleaned, desc)
        return cleaned

    if key.startswith(MENU_LABEL_SETTING_PREFIX):
        require_access(user, "settings_menu_labels", EDIT)
        menu_key = key.removeprefix(MENU_LABEL_SETTING_PREFIX)
        if menu_key not in DEFAULT_MENU_LABELS:
            raise ValidationError("Μη έγκυρο κλειδί μενού.")
        default = DEFAULT_MENU_LABELS[menu_key]
        cleaned = default if reset else _require_non_empty_text(value, max_length=64)
        save_menu_label(menu_key, cleaned, _MENU_DESCRIPTIONS.get(menu_key, menu_key))
        return cleaned

    if key.startswith(CASE_SECTION_LABEL_SETTING_PREFIX):
        require_access(user, "settings_section_labels", EDIT)
        section_key = key.removeprefix(CASE_SECTION_LABEL_SETTING_PREFIX)
        if section_key not in DEFAULT_CASE_SECTION_LABELS:
            raise ValidationError("Μη έγκυρο κλειδί ενότητας.")
        default = DEFAULT_CASE_SECTION_LABELS[section_key]
        cleaned = default if reset else _require_non_empty_text(value, max_length=255)
        save_case_section_label(section_key, cleaned)
        return cleaned

    if key.startswith(CASE_SUBSECTION_LABEL_SETTING_PREFIX):
        require_access(user, "settings_subsection_labels", EDIT)
        subsection_key = key.removeprefix(CASE_SUBSECTION_LABEL_SETTING_PREFIX)
        if subsection_key not in DEFAULT_CASE_SUBSECTION_LABELS:
            raise ValidationError("Μη έγκυρο κλειδί υποενότητας.")
        default = DEFAULT_CASE_SUBSECTION_LABELS[subsection_key]
        cleaned = default if reset else _require_non_empty_text(value, max_length=255)
        save_case_subsection_label(subsection_key, cleaned)
        return cleaned

    if key.startswith(APPLICATION_STAGE_LABEL_SETTING_PREFIX):
        require_access(user, "settings_plot_application_labels", EDIT)
        stage = key.removeprefix(APPLICATION_STAGE_LABEL_SETTING_PREFIX)
        if stage not in DEFAULT_APPLICATION_STAGE_LABELS:
            raise ValidationError("Μη έγκυρο κλειδί σταδίου αίτησης.")
        default = DEFAULT_APPLICATION_STAGE_LABELS[stage]
        cleaned = default if reset else _require_non_empty_text(value, max_length=128)
        save_application_stage_label(stage, cleaned)
        return cleaned

    if _UI_TEXT_KEY_RE.match(key):
        if reset:
            delete_setting(key)
            return ""
        cleaned = _require_non_empty_text(value, max_length=2000)
        desc = (description or "").strip()[:255] or f"Κείμενο οθόνης ({key})"
        set_setting(key, cleaned, desc)
        return cleaned

    raise ValidationError("Μη επιτρεπτό κλειδί κειμένου.")
