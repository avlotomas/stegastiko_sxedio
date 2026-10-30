import pytest
from django.core import serializers
from django.core.management import call_command

from core.models import ActionHistory, Community


@pytest.mark.django_db
def test_loaddata_does_not_record_history(tmp_path):
    community = Community.objects.create(
        district="Λευκωσία",
        name="Δοκιμαστική",
        contact_email="test@example.com",
        community_folder_code="ZZ99",
    )
    fixture = tmp_path / "community.json"
    fixture.write_text(serializers.serialize("json", [community]), encoding="utf-8")
    community.delete()
    ActionHistory.objects.all().delete()

    call_command("loaddata", str(fixture), verbosity=0)

    assert Community.objects.filter(community_folder_code="ZZ99").exists()
    assert not ActionHistory.objects.exists()


@pytest.mark.django_db
def test_regular_save_still_records_history():
    Community.objects.create(
        district="Λευκωσία",
        name="Δοκιμαστική",
        contact_email="test@example.com",
        community_folder_code="ZZ98",
    )

    assert ActionHistory.objects.filter(action=ActionHistory.ActionType.CREATE).exists()
