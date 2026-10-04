"""Playwright E2E fixtures (pytest-django live_server)."""

import os

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

import pytest
from django.contrib.auth import get_user_model

from core.models import Role
from tests.fixtures.golden_application import seed_application_cycle

E2E_PASSWORD = "e2e-secret"
E2E_USERNAME = "e2e_clerk"


@pytest.fixture
def make_user(db):
    def _make_user(username, *role_names, password="secret"):
        user = get_user_model().objects.create_user(username=username, password=password)
        for name in role_names:
            Role.objects.get(name=name).members.add(user)
        return user

    return _make_user


@pytest.fixture
def application_cycle(db):
    return seed_application_cycle()


@pytest.fixture
def e2e_user(db, make_user):
    return make_user(E2E_USERNAME, "Λειτουργός καταχώρισης", password=E2E_PASSWORD)


@pytest.fixture
def live_server_url(live_server):
    return live_server.url
