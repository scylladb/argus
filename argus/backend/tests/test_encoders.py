import json

import pytest

from argus.backend.util.encoders import ArgusJSONEncoder


def test_encoder_decodes_bytes_to_str():
    assert json.dumps({"value": b"hello"}, cls=ArgusJSONEncoder) == '{"value": "hello"}'


def test_encoder_replaces_undecodable_bytes():
    payload = json.dumps({"value": b"\xff\xfe"}, cls=ArgusJSONEncoder)
    assert json.loads(payload)["value"] == b"\xff\xfe".decode("utf-8", errors="replace")


def test_encoder_still_raises_for_unsupported_types():
    with pytest.raises(TypeError):
        json.dumps({"value": object()}, cls=ArgusJSONEncoder)
