import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Community


class Command(BaseCommand):
    help = "Load communities from areas.csv (legacy prototype source)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(
                Path(__file__).resolve().parents[4]
                / "Στεγαστικό_Λευκωσίας_Codex (1)"
                / "stegastiko_nicosia"
                / "data"
                / "areas.csv"
            ),
            help="CSV path with community rows.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file does not exist: {csv_path}")

        created_count = 0
        updated_count = 0
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                district = (row.get("επαρχία") or "").strip()
                name = (row.get("περιοχή_όπως_στο_παράρτημα") or "").strip()
                municipality_type = (row.get("τύπος") or "").strip()
                municipality = (row.get("δήμος") or "").strip()
                source_line = (row.get("γραμμή_πηγής") or "").strip()
                source_col = (row.get("στήλη_πηγής") or "").strip()
                if not district or not name:
                    continue

                folder_code = f"{source_line}{source_col}".zfill(4)
                default_email = f"community-{folder_code}@example.org"
                obj, created = Community.objects.update_or_create(
                    district=district,
                    name=name,
                    defaults={
                        "municipality_type": municipality_type,
                        "municipality": municipality,
                        "contact_email": default_email,
                        "community_folder_code": folder_code,
                        "is_active": True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Communities loaded. Created: {created_count}, Updated: {updated_count}"
            )
        )
