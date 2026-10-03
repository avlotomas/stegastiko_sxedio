import pytest
from django.contrib.auth import get_user_model

from core.models import Role


@pytest.fixture
def make_user(db):
    """Create a user holding default roles seeded by core migration 0011 (by role name)."""

    def _make_user(username, *role_names, password="secret"):
        user = get_user_model().objects.create_user(username=username, password=password)
        for name in role_names:
            Role.objects.get(name=name).members.add(user)
        return user

    return _make_user
