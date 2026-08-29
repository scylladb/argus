"""Token auth over the live socket -- the smallest end-to-end round trip.

Every other test in this suite authenticates implicitly; these localize an
auth regression to the token pipeline itself (``load_user`` resolving
``Authorization: token <api_token>`` against a persisted user).
"""

import uuid

import pytest

from argus.client.base import ArgusClientError
from argus.client.generic.client import ArgusGenericClient

pytestmark = pytest.mark.docker_required


def test_persisted_token_authenticates(generic_client, generic_test):
    generic_client.submit_generic_run(
        build_id=generic_test.build_system_id,
        run_id=str(uuid.uuid4()),
        started_by="e2e_auth_user",
        build_url="http://example.com/job/1/",
    )


def test_unknown_token_raises_client_error(make_client, generic_test):
    client = make_client(ArgusGenericClient, auth_token="garbage-token")
    with pytest.raises(ArgusClientError):
        client.submit_generic_run(
            build_id=generic_test.build_system_id,
            run_id=str(uuid.uuid4()),
            started_by="e2e_auth_user",
            build_url="http://example.com/job/1/",
        )
