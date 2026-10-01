from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from cases.models import Consultation
from core.models import ReminderRead
from core.services import get_setting

CONSULTATION_DUE_REMINDER_DAYS_KEY = "consultationDueReminderDays"
CONSULTATION_DUE_REMINDER_DAYS_DEFAULT = 7
CONSULTATION_DUE_REMINDER_TYPE = "consultation_due"


@dataclass(frozen=True)
class ReminderItem:
    key: str
    reminder_type: str
    title: str
    details: str
    case_number: str
    due_date: object
    days_left: int
    target_url: str
    is_read: bool
    read_at: object


def consultation_due_reminder_days() -> int:
    raw_value = get_setting(
        CONSULTATION_DUE_REMINDER_DAYS_KEY, str(CONSULTATION_DUE_REMINDER_DAYS_DEFAULT)
    )
    try:
        days = int(raw_value)
    except (TypeError, ValueError):
        return CONSULTATION_DUE_REMINDER_DAYS_DEFAULT
    return max(days, 0)


def consultation_due_reminder_key(consultation_id: int) -> str:
    return f"{CONSULTATION_DUE_REMINDER_TYPE}:{consultation_id}"


def consultation_due_reminders(user, include_read=False):
    today = timezone.localdate()
    reminder_days = consultation_due_reminder_days()
    until = today + timedelta(days=reminder_days)
    queryset = (
        Consultation.objects.select_related("case")
        .filter(
            due_date__isnull=False,
            response_date__isnull=True,
        )
        .filter(Q(due_date__lte=until))
        .order_by("due_date", "id")
    )

    reminders = []
    read_map = {
        row.reminder_key: row.read_at
        for row in ReminderRead.objects.filter(
            user=user, reminder_type=CONSULTATION_DUE_REMINDER_TYPE
        )
    }
    for consultation in queryset:
        key = consultation_due_reminder_key(consultation.pk)
        read_at = read_map.get(key)
        if read_at and not include_read:
            continue
        due_date = consultation.due_date
        days_left = (due_date - today).days
        reminders.append(
            ReminderItem(
                key=key,
                reminder_type=CONSULTATION_DUE_REMINDER_TYPE,
                title="Προθεσμία απάντησης διαβούλευσης",
                details=consultation.row_label,
                case_number=consultation.case.case_number,
                due_date=due_date,
                days_left=days_left,
                target_url=reverse(
                    "cases:section_edit",
                    args=[
                        consultation.case_id,
                        "5"
                        if consultation.stage == Consultation.Stage.SUITABILITY
                        else "8",
                    ],
                ),
                is_read=read_at is not None,
                read_at=read_at,
            )
        )
    return reminders


def mark_reminder_read(user, reminder_key: str, reminder_type: str) -> None:
    ReminderRead.objects.update_or_create(
        user=user,
        reminder_key=reminder_key,
        defaults={"reminder_type": reminder_type, "read_at": timezone.now()},
    )
