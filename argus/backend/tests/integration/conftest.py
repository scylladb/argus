"""End-to-end scaffolding for the argus.client integration suite.

These tests drive the real ``argus.client`` classes -- requests.Session,
urllib3 retries, ``Authorization: token`` headers, replay log -- against the
real FastAPI app served over an actual socket, backed by the session-scoped
Docker ScyllaDB from ``argus/backend/tests/conftest.py``.

Ground rules, shared with the rest of the backend suite:

- pytest must run from the repo root (``StaticFiles("public")`` and the
  vector-store volume mount are cwd-relative).
- Rows created by tests are not cleaned up; the keyspace dies with the
  session containers. Mint unique ids/names per test.
- Incompatible with pytest-xdist (fixed container names and host ports).
"""

import threading
import time
import uuid
from datetime import UTC, datetime

import uvicorn
from _pytest.fixtures import fixture

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, User, UserRoles
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.user import UserService
from argus.client.base import ArgusClient
from argus.client.driver_matrix_tests.client import ArgusDriverMatrixClient
from argus.client.generic.client import ArgusGenericClient
from argus.client.sct.client import ArgusSCTClient


@fixture(scope='session')
def live_server(argus_db) -> str:
    import argus_backend
    app = argus_backend.create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="argus-e2e-uvicorn", daemon=True)
    thread.start()
    # Fail here rather than through the clients' connect-retry backoff.
    deadline = time.time() + 30
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("uvicorn thread died during startup")
        if time.time() > deadline:
            server.should_exit = True
            raise RuntimeError("uvicorn did not start within 30 seconds")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@fixture(scope='session')
def api_user(argus_db) -> User:
    """A persisted user for real token auth.

    ``load_user`` resolves the Authorization header via
    ``User.get(api_token=...)``, so unlike ``logged_in_user`` this one must
    exist in the database.
    """
    suffix = time.time_ns()
    user = User(
        username=f"e2e_client_{suffix}",
        full_name="E2E Client User",
        email=f"e2e-client-{suffix}@scylladb.com",
        registration_date=datetime.now(UTC),
        roles=[UserRoles.User.value],
    )
    user.save()
    yield user
    user.delete()


@fixture(scope='session')
def api_token(api_user) -> str:
    return UserService().get_or_generate_token(api_user)


@fixture
def make_client(live_server, api_token, tmp_path):
    """Factory for client instances pointed at the live server.

    ``use_tunnel=False`` is explicit so an ambient ARGUS_USE_TUNNEL cannot
    spawn the tunnel monitor thread. Every produced client is closed on
    teardown (requests session + replay-log file handle).
    """
    created: list[ArgusClient] = []

    def _make(cls: type[ArgusClient], /, **kwargs) -> ArgusClient:
        kwargs.setdefault("auth_token", api_token)
        kwargs.setdefault("base_url", live_server)
        kwargs.setdefault("log_dir", tmp_path)
        kwargs.setdefault("use_tunnel", False)
        client = cls(**kwargs)
        created.append(client)
        return client

    yield _make
    for client in created:
        client.close()


@fixture
def sct_client(make_client) -> ArgusSCTClient:
    return make_client(ArgusSCTClient, run_id=uuid.uuid4())


@fixture
def generic_client(make_client) -> ArgusGenericClient:
    return make_client(ArgusGenericClient)


@fixture
def driver_matrix_client(make_client) -> ArgusDriverMatrixClient:
    return make_client(ArgusDriverMatrixClient, run_id=uuid.uuid4())


def _plugin_test(release_manager_service: ReleaseManagerService, group: ArgusGroup,
                 release: ArgusRelease, plugin_name: str, prefix: str) -> ArgusTest:
    name = f"{prefix}_{time.time_ns()}"
    return release_manager_service.create_test(name, name, name, name,
                                               group_id=str(group.id), release_id=str(release.id),
                                               plugin_name=plugin_name)


@fixture
def generic_test(release_manager_service, group: ArgusGroup, release: ArgusRelease) -> ArgusTest:
    return _plugin_test(release_manager_service, group, release, "generic", "e2e_generic")


@fixture
def driver_matrix_test(release_manager_service, group: ArgusGroup, release: ArgusRelease) -> ArgusTest:
    return _plugin_test(release_manager_service, group, release, "driver-matrix-tests", "e2e_dmt")


@fixture
def sirenada_test(release_manager_service, group: ArgusGroup, release: ArgusRelease) -> ArgusTest:
    return _plugin_test(release_manager_service, group, release, "sirenada", "e2e_sirenada")
