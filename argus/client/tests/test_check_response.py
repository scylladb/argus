"""Unit tests for ArgusClient.check_response.

Pins the client-side handling of every response envelope the backend can
produce. The standard error envelope (error_handlers.api_exception_handler)
is a dict carrying "arguments"; the DB-outage handler puts a plain string
under "response" instead, and any non-200 status must fail on the status
code alone. Shapes that a healthy live backend cannot be made to produce
are covered here; the reachable ones are also driven end-to-end in
argus/backend/tests/integration/test_error_contract.py.
"""

import pytest
import requests

from argus.client.base import ArgusClient, ArgusClientError

URL = "https://argus.scylladb.com/api/v1/client/testrun/generic/submit"


def _response(requests_mock, json: dict, status_code: int = 200) -> requests.Response:
    requests_mock.post(URL, json=json, status_code=status_code)
    return requests.post(URL)


def test_ok_envelope_passes(requests_mock):
    ArgusClient.check_response(_response(requests_mock, {"status": "ok", "response": True}))


def test_non_200_raises_on_status_code_alone(requests_mock):
    response = _response(requests_mock, {"status": "ok"}, status_code=500)
    with pytest.raises(ArgusClientError) as excinfo:
        ArgusClient.check_response(response)
    message, expected, got, method, path = excinfo.value.args
    assert "Unexpected HTTP Response" in message
    assert (expected, got, method) == (200, 500, "POST")
    assert path == "/api/v1/client/testrun/generic/submit"


def test_expected_code_override(requests_mock):
    response = _response(requests_mock, {"status": "ok"}, status_code=201)
    ArgusClient.check_response(response, expected_code=201)


def test_error_envelope_with_arguments(requests_mock):
    response = _response(requests_mock, {
        "status": "error",
        "response": {
            "trace_id": "abc",
            "exception": "APIException",
            "message": "boom",
            "arguments": ["boom", "extra"],
        },
    })
    with pytest.raises(ArgusClientError) as excinfo:
        ArgusClient.check_response(response)
    assert "API Error encountered" in excinfo.value.args[0]
    assert excinfo.value.args[1] == "boom"


def test_error_envelope_with_empty_arguments_falls_back_to_exception_name(requests_mock):
    response = _response(requests_mock, {
        "status": "error",
        "response": {"exception": "RequestValidationError", "arguments": []},
    })
    with pytest.raises(ArgusClientError) as excinfo:
        ArgusClient.check_response(response)
    assert excinfo.value.args[1] == "RequestValidationError"


def test_error_envelope_with_string_response(requests_mock):
    # Shape produced by the backend DB-outage handler.
    response = _response(requests_mock, {
        "status": "error",
        "response": "Cluster seems down. Attempting reconnect in 9 tries.",
    })
    with pytest.raises(ArgusClientError) as excinfo:
        ArgusClient.check_response(response)
    assert excinfo.value.args[1] == "Cluster seems down. Attempting reconnect in 9 tries."


def test_error_envelope_without_response_body(requests_mock):
    response = _response(requests_mock, {"status": "error"})
    with pytest.raises(ArgusClientError) as excinfo:
        ArgusClient.check_response(response)
    assert excinfo.value.args[1] == "#NoMessage"
