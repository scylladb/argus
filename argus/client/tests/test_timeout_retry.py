"""Tests for timeout and retry functionality in ArgusClient."""
from unittest.mock import patch
from uuid import uuid4

from argus.client.base import ArgusClient
from argus.client.sct.client import ArgusSCTClient
from argus.client.generic.client import ArgusGenericClient
from argus.client.driver_matrix_tests.client import ArgusDriverMatrixClient
from argus.client.sirenada.client import ArgusSirenadaClient


def test_argus_client_default_timeout():
    """Test that ArgusClient uses default timeout of 60 seconds."""
    client = ArgusClient(
        auth_token="test_token",
        base_url="https://test.example.com"
    )
    assert client._timeout == 60


def test_argus_client_custom_timeout():
    """Test that ArgusClient accepts custom timeout."""
    client = ArgusClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=120
    )
    assert client._timeout == 120


def test_argus_client_session_has_retry_adapter():
    """Test that ArgusClient session is configured with retry adapter."""
    client = ArgusClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        max_retries=5
    )

    # Check that adapters are mounted
    assert "https://" in client.session.adapters
    assert "http://" in client.session.adapters

    # Check that the adapter has retry configuration
    adapter = client.session.get_adapter("https://test.example.com")
    assert adapter.max_retries.total == 5
    assert adapter.max_retries.backoff_factor == 1
    assert adapter.max_retries.status == 0
    assert adapter.max_retries.status_forcelist == set()


def test_get_request_uses_timeout(requests_mock):
    """Test that GET requests include timeout parameter."""
    requests_mock.get(
        "https://test.example.com/api/v1/client/testrun/test-type/test-id/get",
        json={"status": "ok", "response": {}},
        status_code=200
    )

    client = ArgusClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=30
    )

    with patch.object(client.session, 'get', wraps=client.session.get) as mock_get:
        try:
            client.get(
                endpoint=ArgusClient.Routes.GET,
                location_params={"type": "test-type", "id": "test-id"}
            )
        except Exception:
            pass  # We're just checking the call arguments

        # Verify timeout was passed to the request
        assert mock_get.called
        call_kwargs = mock_get.call_args.kwargs
        assert 'timeout' in call_kwargs
        assert call_kwargs['timeout'] == 30


def test_post_request_uses_timeout(requests_mock):
    """Test that POST requests include timeout parameter."""
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        json={"status": "ok"},
        status_code=200
    )

    client = ArgusClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=45
    )

    with patch.object(client.session, 'post', wraps=client.session.post) as mock_post:
        try:
            client.post(
                endpoint=ArgusClient.Routes.SUBMIT,
                location_params={"type": "test-type"},
                body={"test": "data"}
            )
        except Exception:
            pass  # We're just checking the call arguments

        # Verify timeout was passed to the request
        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        assert 'timeout' in call_kwargs
        assert call_kwargs['timeout'] == 45


def test_retry_configuration_is_correct():
    """Test that the retry adapter is correctly configured."""
    client = ArgusClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        max_retries=5
    )

    # Get the adapter
    adapter = client.session.get_adapter("https://test.example.com")

    # Verify retry configuration
    assert adapter.max_retries.total == 5
    assert adapter.max_retries.backoff_factor == 1
    assert adapter.max_retries.status == 0
    assert adapter.max_retries.status_forcelist == set()
    assert "GET" in adapter.max_retries.allowed_methods
    assert "POST" in adapter.max_retries.allowed_methods


def test_sct_client_passes_timeout_and_retries():
    """Test that ArgusSCTClient passes timeout and retry parameters to parent."""
    run_id = uuid4()
    client = ArgusSCTClient(
        run_id=run_id,
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=90,
        max_retries=5
    )

    assert client._timeout == 90
    adapter = client.session.get_adapter("https://test.example.com")
    assert adapter.max_retries.total == 5


def test_generic_client_passes_timeout_and_retries():
    """Test that ArgusGenericClient passes timeout and retry parameters to parent."""
    client = ArgusGenericClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=75,
        max_retries=4
    )

    assert client._timeout == 75
    adapter = client.session.get_adapter("https://test.example.com")
    assert adapter.max_retries.total == 4


def test_driver_matrix_client_passes_timeout_and_retries():
    """Test that ArgusDriverMatrixClient passes timeout and retry parameters to parent."""
    run_id = uuid4()
    client = ArgusDriverMatrixClient(
        run_id=run_id,
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=100,
        max_retries=2
    )

    assert client._timeout == 100
    adapter = client.session.get_adapter("https://test.example.com")
    assert adapter.max_retries.total == 2


def test_sirenada_client_passes_timeout_and_retries():
    """Test that ArgusSirenadaClient passes timeout and retry parameters to parent."""
    client = ArgusSirenadaClient(
        auth_token="test_token",
        base_url="https://test.example.com",
        timeout=80,
        max_retries=6
    )

    assert client._timeout == 80
    adapter = client.session.get_adapter("https://test.example.com")
    assert adapter.max_retries.total == 6


def test_client_uses_default_values_when_not_specified():
    """Test that client uses defaults when timeout and retries not specified."""
    run_id = uuid4()
    client = ArgusSCTClient(
        run_id=run_id,
        auth_token="test_token",
        base_url="https://test.example.com"
    )

    # Should use default timeout of 60 and default retries of 3
    assert client._timeout == 60
    adapter = client.session.get_adapter("https://test.example.com")
    assert adapter.max_retries.total == 3
