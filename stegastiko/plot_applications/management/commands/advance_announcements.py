"""Management command `advance_announcements`: closes the objection period of announcements whose 21 days have elapsed."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import SubmissionCycle
from plot_applications.announcement_workflow import refresh_time_based_stages


class Command(BaseCommand):
    help = "Κλείνει αυτόματα την περίοδο ενστάσεων των γνωστοποιήσεων (Στάδιο 3, Επιτροπή Εξέτασης Ενστάσεων) όταν παρέλθουν οι 21 ημέρες."

    def handle(self, *args, **options):
        today = timezone.localdate()
        advanced = 0
        for cycle in SubmissionCycle.objects.filter(published_at__isnull=False):
            if refresh_time_based_stages(cycle, today=today):
                advanced += 1
        self.stdout.write(f"Ενημερώθηκαν {advanced} γνωστοποιήσεις.")
