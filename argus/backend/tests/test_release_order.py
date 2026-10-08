from types import SimpleNamespace

from argus.backend.service.argus_service import release_sort_key
from argus.backend.util.common import version_key


def test_version_key_lists_the_newer_year_first():
    assert version_key("scylla-2026.3") < version_key("scylla-2025.1")


def test_version_key_compares_numbers_by_value():
    assert version_key("manager-3.12") < version_key("manager-3.9")


def test_version_key_lists_a_release_before_its_suffixed_branch():
    assert version_key("enterprise-2024.1") < version_key("enterprise-2024.1/releng-testing")


def test_release_sort_key_reads_a_missing_priority_as_zero():
    unset = SimpleNamespace(priority=None, dormant=False, name="scylla-2025.1")
    zero = SimpleNamespace(priority=0, dormant=False, name="scylla-2025.1")

    assert release_sort_key(unset) == release_sort_key(zero)


def test_release_sort_key_lists_priority_before_name_and_dormant_last():
    releases = [
        SimpleNamespace(priority=0, dormant=False, name="scylla-2025.1"),
        SimpleNamespace(priority=50, dormant=True, name="scylla-old"),
        SimpleNamespace(priority=10, dormant=False, name="scylla-master"),
        SimpleNamespace(priority=None, dormant=False, name="scylla-2026.1"),
    ]

    ordered = [release.name for release in sorted(releases, key=release_sort_key)]

    assert ordered == ["scylla-master", "scylla-2026.1", "scylla-2025.1", "scylla-old"]
