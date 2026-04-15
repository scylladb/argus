import logging
from collections import defaultdict
from uuid import UUID

from argus.backend.models.github_issue import IssueLink
from argus.backend.models.web import ArgusTest
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.util.common import check_version, chunk

LOGGER = logging.getLogger(__name__)


def build_version_map(links: list[IssueLink]) -> dict[UUID, str | None]:
    """Resolve scylla_version for run_ids by looking up only the correct plugin table.

    1. Batch-fetch ArgusTest records to learn each test's plugin_name.
    2. Group run_ids by plugin_name via link.test_id.
    3. Query only the primary model for each plugin.
    """
    # test_id → plugin_name
    unique_test_ids = {link.test_id for link in links}
    test_plugin_map: dict[UUID, str] = {}
    for batch in chunk(unique_test_ids):
        for test in ArgusTest.filter(id__in=batch).only(["id", "plugin_name"]).all():
            test_plugin_map[test.id] = test.plugin_name

    # run_id → plugin model, grouped (deduplicated)
    runs_by_plugin: dict[str, set[UUID]] = defaultdict(set)
    for link in links:
        plugin_name = test_plugin_map.get(link.test_id)
        if plugin_name:
            runs_by_plugin[plugin_name].add(link.run_id)

    # Query each plugin's primary model only for its own run_ids
    version_map: dict[UUID, str | None] = {}
    for plugin_name, run_ids in runs_by_plugin.items():
        plugin = AVAILABLE_PLUGINS.get(plugin_name)
        if not plugin:
            continue
        resolved = plugin.model.get_versions_by_run_ids(run_ids)
        version_map.update(resolved)
    return version_map


def filter_links_by_version(
    links: list[IssueLink],
    product_version: str,
    include_no_version: bool = False,
    version_map: dict[UUID, str | None] | None = None,
) -> list[IssueLink]:
    """Filter IssueLink records to only those whose associated run matches the given version.

    If version_map is not provided, it is built by resolving test_id → plugin_name
    and querying only the correct plugin table for each run.
    """
    if version_map is None:
        version_map = build_version_map(links)

    def matches(link: IssueLink) -> bool:
        run_version = version_map.get(link.run_id)
        if product_version == "!noVersion":
            return not run_version
        if check_version(product_version, run_version):
            return True
        if include_no_version and not run_version:
            return True
        return False

    return [link for link in links if matches(link)]
