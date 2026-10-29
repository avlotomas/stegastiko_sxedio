"""Configurable display labels of the plot application stages (`ApplicationStage`, §Α.9.1)."""

from core.services import get_setting, set_setting
from plot_applications.models import REJECTION_STAGES, ApplicationStage

APPLICATION_STAGE_LABEL_SETTING_PREFIX = "applicationStageLabel."

DEFAULT_APPLICATION_STAGE_LABELS: dict[str, str] = dict(ApplicationStage.choices)


def application_stage_label_setting_key(stage: str) -> str:
    return f"{APPLICATION_STAGE_LABEL_SETTING_PREFIX}{stage}"


def get_application_stage_label(stage: str) -> str:
    default = DEFAULT_APPLICATION_STAGE_LABELS.get(stage, stage)
    return get_setting(application_stage_label_setting_key(stage), "").strip() or default


def application_stage_choices() -> list[tuple[str, str]]:
    return [(stage, get_application_stage_label(stage)) for stage in ApplicationStage.values]


def application_stage_steps(current_stage: str | None = None) -> list[tuple[str, str]]:
    """Τα βήματα της κανονικής ροής· τα στάδια απόρριψης εμφανίζονται μόνο όταν είναι το τρέχον."""
    return [
        (stage, label)
        for stage, label in application_stage_choices()
        if stage not in REJECTION_STAGES or stage == current_stage
    ]


def save_application_stage_label(stage: str, label: str) -> None:
    number = ApplicationStage.values.index(stage) + 1
    set_setting(
        application_stage_label_setting_key(stage),
        label.strip(),
        f"Στάδιο {number} αίτησης παραχώρησης οικοπέδου (τίτλος εμφάνισης)",
    )
