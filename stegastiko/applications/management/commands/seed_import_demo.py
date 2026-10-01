"""Minimal community + submission cycle (id=1) for testing Excel import."""

from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import Case, SubmissionCycle
from core.models import Community, SystemSetting


class Command(BaseCommand):
    help = "Create demo community (folder code 001) and published SubmissionCycle id=1 for import tests."

    def handle(self, *args, **options):
        community, created = Community.objects.get_or_create(
            community_folder_code="001",
            defaults={
                "district": "ΛΕΥΚΩΣΙΑΣ",
                "municipality_type": "Κοινότητα",
                "municipality": "",
                "name": "ΑΓΙΑ ΒΑΡΒΑΡΑ",
                "contact_email": "demo-agia-varvara@example.org",
                "is_active": True,
            },
        )
        if not created:
            community.name = "ΑΓΙΑ ΒΑΡΒΑΡΑ"
            community.is_active = True
            community.save()

        case, _ = Case.objects.get_or_create(
            community=community,
            case_number="DEMO-CASE-001",
            defaults={
                "start_date": date(2026, 1, 1),
                "contact_email": "demo-case@example.org",
            },
        )

        cycle = SubmissionCycle.objects.filter(pk=1).first()
        if cycle:
            cycle.community = community
            cycle.announcement_date = date(2026, 6, 1)
            cycle.submission_start_date = date(2026, 6, 2)
            cycle.submission_end_date = date(2026, 12, 31)
            cycle.published_at = timezone.now()
            cycle.save()
            self.stdout.write("Updated SubmissionCycle id=1")
        else:
            cycle = SubmissionCycle.objects.create(
                id=1,
                community=community,
                announcement_date=date(2026, 6, 1),
                submission_start_date=date(2026, 6, 2),
                submission_end_date=date(2026, 12, 31),
                published_at=timezone.now(),
            )
            self.stdout.write(self.style.SUCCESS("Created SubmissionCycle id=1"))
        cycle.cases.add(case)

        SystemSetting.objects.update_or_create(
            key="applicationFolderPrefix",
            defaults={"value": "12", "description": "Folder prefix"},
        )
        SystemSetting.objects.update_or_create(
            key="folderSequenceDigits",
            defaults={"value": "3", "description": "Folder sequence width"},
        )
        self.stdout.write(self.style.SUCCESS(f"Community folder code 001 (pk={community.pk})"))
