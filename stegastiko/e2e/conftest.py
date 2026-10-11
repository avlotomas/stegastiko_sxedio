"""Playwright E2E fixtures (pytest-django live_server)."""

import os

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections

from core.models import Role
from tests.fixtures.golden_application import seed_application_cycle

E2E_PASSWORD = "e2e-secret"
E2E_USERNAME = "e2e_clerk"


@pytest.fixture(scope="session")
def _seed_snapshot(django_db_setup, django_db_blocker):
    """Migration-seeded data (roles, settings) captured when the test DB was created.

    Any transactional test flushes the database on teardown, so E2E tests cannot rely on
    the seed still being there. Django's own serialized_rollback cannot restore it here:
    the snapshot lives on the connection object, and once Playwright starts its event loop
    Django hands out a fresh connection object without it.
    """
    return getattr(connections["default"], "_test_serialized_contents", None)


@pytest.fixture
def db(transactional_db, _seed_snapshot):
    """Live-server tests are transactional; restore the seed if an earlier test flushed it."""
    if _seed_snapshot and not Role.objects.exists():
        connection.creation.deserialize_db_from_string(_seed_snapshot)


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
