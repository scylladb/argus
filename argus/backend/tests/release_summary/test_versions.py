import pytest

from argus.common.versions import ScyllaVersion, parse_version


@pytest.mark.parametrize(("raw", "version", "family"), [
    ("2025.1.0~rc2", "2025.1.0~rc2", "2025.1.0"),
    ("2025.1.0.rc0.0.20250128.f407799f252d", "2025.1.0~rc0", "2025.1.0"),
    ("2025.1.0.0.20250325.9dca28d2b818", "2025.1.0", "2025.1.0"),
    ("2024.1.0~dev", "2024.1.0~dev", "2024.1.0"),
    ("2025.1.1", "2025.1.1", "2025.1.1"),
    ("6.0.0~rc0-0.20240101.abcdef", "6.0.0~rc0", "6.0.0"),
])
def test_parse_version_reads_the_version_and_its_family(raw, version, family):
    parsed = parse_version(raw)

    assert str(parsed) == version
    assert parsed.family == family


@pytest.mark.parametrize("raw", [None, "", "master", "2025.1", "rc1"])
def test_parse_version_leaves_out_what_does_not_parse(raw):
    assert parse_version(raw) is None


def test_versions_of_a_family_run_from_dev_through_the_rcs_to_the_final_build():
    raws = ["2025.1.0", "2025.1.0~rc10", "2025.1.0~rc2", "2025.1.0~dev", "2025.1.0~rc0"]

    ordered = sorted((parse_version(raw) for raw in raws), key=ScyllaVersion.sort_key)

    assert [str(version) for version in ordered] == [
        "2025.1.0~dev", "2025.1.0~rc0", "2025.1.0~rc2", "2025.1.0~rc10", "2025.1.0"]


def test_families_compare_by_number():
    assert parse_version("2025.1.10").sort_key() > parse_version("2025.1.9").sort_key()
