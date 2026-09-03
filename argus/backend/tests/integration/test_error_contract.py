"""check_response driven by real backend error responses.

The happy path returns HTTP 200 + {"status": "ok"}; errors come back as
HTTP 200 + {"status": "error", "response": {...}} (except AuthorizationError,
a genuine 403). These tests make the live backend produce each reachable
shape and assert the client turns every one of them into ArgusClientError.
The envelope shapes a healthy backend cannot produce (string "response",
missing body) are unit-tested in argus/client/tests/test_check_response.py.
"""

import uuid

import pytest

from argus.client.base import ArgusClientError

pytestmark = pytest.mark.docker_required


def test_backend_exception_envelope(sct_client):
    # The run was never submitted, so the status lookup raises server-side;
    # api_exception_handler wraps it as HTTP 200 + status=error with the
    # exception's arguments, and the client relays the first argument.
    with pytest.raises(ArgusClientError) as excinfo:
        sct_client.get_status()
    assert "API Error encountered" in excinfo.value.args[0]
    assert excinfo.value.args[1]


def test_validation_error_envelope(sct_client):
    # An empty body fails pydantic validation server-side; the resulting
    # RequestValidationError envelope must surface as ArgusClientError, not
    # as a KeyError/IndexError while unpacking the error body.
    response = sct_client.post(
        endpoint=sct_client.Routes.SET_SCT_RUNNER,
        location_params={"id": str(sct_client.run_id)},
        body={},
    )
    assert response.status_code == 200
    assert response.json()["response"]["exception"] == "RequestValidationError"
    with pytest.raises(ArgusClientError) as excinfo:
        sct_client.check_response(response)
    assert "API Error encountered" in excinfo.value.args[0]


def test_non_200_response(sct_client):
    # A path FastAPI cannot route is a real 404 (no exception handler turns
    # routing misses into the 200 envelope); check_response must fail on the
    # status code alone.
    response = sct_client.get(endpoint=f"/nonexistent/{uuid.uuid4()}", location_params={})
    assert response.status_code == 404
    with pytest.raises(ArgusClientError) as excinfo:
        sct_client.check_response(response)
    message, expected, got, method, _path = excinfo.value.args
    assert "Unexpected HTTP Response" in message
    assert (expected, got, method) == (200, 404, "GET")
