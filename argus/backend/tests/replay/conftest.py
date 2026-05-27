"""Local conftest for the replay tests.

The parent ``conftest.py`` has a session-scope autouse fixture that boots a
ScyllaDB Docker container before any test in ``argus/backend/tests`` runs.
The replay-service tests are pure unit tests that don't touch the database,
so override the heavyweight fixtures with no-ops here. This lets developers
iterate on the replay logic with ``pytest argus/backend/tests/replay`` and
no Docker daemon.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def argus_db():
    yield None


@pytest.fixture(scope="session")
def argus_app():
    yield None


@pytest.fixture(scope="session", autouse=True)
def app_context(argus_db, argus_app):
    yield
