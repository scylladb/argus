import pytest

from argus.backend.service.jenkins_service import parse_test_metadata_from_description


def test_parse_metadata_from_valid_description():
    description = """
        <div style="margin: 12px 4px;">
            <a href='https://argus.scylladb.com/tests/scylla-cluster-tests/abc123'>
                Argus: <span style='font-weight: 500'>abc123</span>
            </a>
        </div>
        <div style="margin: 4px; font-size: 0.85em; color: #555;">
            <b>Metadata:</b> tier=tier1 |
            type=longevity |
            duration=short |
            backends=['aws', 'gce']
        </div>
    """
    result = parse_test_metadata_from_description(description)
    assert result == {
        "tier": "tier1",
        "test_type": "longevity",
        "duration_class": "short",
        "supported_backends": ["aws", "gce"],
    }


def test_parse_metadata_returns_none_for_empty():
    assert parse_test_metadata_from_description(None) is None
    assert parse_test_metadata_from_description("") is None


def test_parse_metadata_returns_none_when_no_metadata_block():
    description = "<div><a href='#'>Argus: abc</a></div>"
    assert parse_test_metadata_from_description(description) is None


def test_parse_metadata_single_backend():
    description = "<b>Metadata:</b> tier=sanity | type=functional | duration=short | backends=['docker']"
    result = parse_test_metadata_from_description(description)
    assert result["supported_backends"] == ["docker"]
    assert result["tier"] == "sanity"


def test_parse_metadata_n_a_values():
    description = "<b>Metadata:</b> tier=n/a | type=n/a | duration=n/a | backends=n/a"
    result = parse_test_metadata_from_description(description)
    assert result["tier"] == "n/a"
    assert result["supported_backends"] == ["n/a"]
