#!/usr/bin/env python3
"""Seed a local Argus dev database with synthetic data.

Usage:
    python dev-db/seed_data.py                    # seed with admin/admin
    python dev-db/seed_data.py --username dev --password dev123
    python dev-db/seed_data.py --create-keyspace  # also create the keyspace
    python dev-db/seed_data.py --force             # wipe and recreate seed data

Run from the repository root so that argus_web.yaml is found automatically.
"""

import argparse
import json
import logging
import os
import random
from datetime import UTC, datetime, timedelta
from time import time
from uuid import uuid4

# Must be set before any cqlengine import
os.environ["CQLENG_ALLOW_SCHEMA_MANAGEMENT"] = "1"

from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster
from argus.backend.cli import sync_models
from werkzeug.security import generate_password_hash

from argus.backend.db import ScyllaCluster
from argus.backend.models.github_issue import GithubIssue, IssueAssignee, IssueLabel, IssueLink
from argus.backend.models.jira import JiraIssue
from argus.backend.models.result import (
    ArgusBestResultData,
    ArgusGenericResultData,
    ArgusGenericResultMetadata,
    ArgusGraphView,
    ColumnMetadata,
)
from argus.backend.models.web import (
    ArgusEvent,
    ArgusEventTypes,
    ArgusGroup,
    ArgusRelease,
    ArgusTest,
    User,
    UserRoles,
)
from argus.backend.plugins.sct.testrun import SCTEvent, SCTEventSeverity, SCTTestRun
from argus.backend.util.config import Config
from argus.common.enums import TestInvestigationStatus, TestStatus

logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger("seed")

# ---------------------------------------------------------------------------
# Default seed content — edit this section to change what gets seeded.
#
# Everything the script creates is driven from this dict.  To add more
# releases, groups, tests, event templates, result tables, or sample
# issues just extend the corresponding list.
# ---------------------------------------------------------------------------

DEFAULT_CONTENT: dict = {
    # ── Release & test hierarchy ────────────────────────────────────────
    "release_name": "seed-release",
    "release_pretty_name": "Seed Release",
    "release_description": "Synthetic data for local development",
    "groups": [
        {
            "name": "longevity-tests",
            "pretty_name": "Longevity Tests",
            "tests": [
                ("longevity-10gb-3h-test", "Longevity 10GB 3h"),
                ("longevity-100gb-12h-test", "Longevity 100GB 12h"),
                ("longevity-large-partition-test", "Longevity Large Partition"),
            ],
        },
        {
            "name": "performance-tests",
            "pretty_name": "Performance Tests",
            "tests": [
                ("perf-regression-latency-test", "Performance Regression Latency"),
                ("perf-throughput-test", "Performance Throughput"),
                ("perf-large-partition-test", "Performance Large Partition"),
            ],
        },
    ],
    # ── Test runs ───────────────────────────────────────────────────────
    # Each profile produces one run per test.
    "run_profiles": [
        # (status, investigation_status)
        (TestStatus.PASSED, TestInvestigationStatus.NOT_INVESTIGATED),
        (TestStatus.PASSED, TestInvestigationStatus.NOT_INVESTIGATED),
        (TestStatus.FAILED, TestInvestigationStatus.IN_PROGRESS),
        (TestStatus.ERROR, TestInvestigationStatus.INVESTIGATED),
        (TestStatus.ABORTED, TestInvestigationStatus.NOT_INVESTIGATED),
    ],
    "branches": ["master", "branch-2025.1", "next", "enterprise", "branch-6.2"],
    "committers": ["jenkins-bot", "dev-user", "ci-runner", "test-automation"],
    "events_per_run": (2, 4),  # (min, max) SCT events per run
    # ── SCT event templates ─────────────────────────────────────────────
    # Each tuple: (severity, event_type, message_template).
    # Templates may use {node}, {step}, {dur}, {size} placeholders.
    "event_templates": [
        (SCTEventSeverity.NORMAL, "CassandraStressEvent", "stress command completed successfully on node {node}"),
        (SCTEventSeverity.NORMAL, "TestFrameworkEvent", "Test step '{step}' passed — duration {dur}s"),
        (
            SCTEventSeverity.WARNING,
            "DatabaseLogEvent",
            "WARN  [shard 0] compaction - Compaction is slow, took {dur}ms for {size}MB",
        ),
        (
            SCTEventSeverity.WARNING,
            "YcsbStressEvent",
            "YCSB stress operation timed out after {dur}ms on loader node {node}",
        ),
        (
            SCTEventSeverity.ERROR,
            "DatabaseLogEvent",
            "ERROR [shard 2] storage_service - Decommission failed: node {node} unreachable",
        ),
        (SCTEventSeverity.ERROR, "CassandraStressEvent", "stress command failed with exit code 1 on node {node}"),
        (
            SCTEventSeverity.CRITICAL,
            "DatabaseLogEvent",
            "CRITICAL [shard 0] database - Commitlog disk error: /var/lib/scylla/commitlog",
        ),
        (SCTEventSeverity.CRITICAL, "InstanceStatusEvent", "Node {node} is down and not responding to health checks"),
    ],
    # ── Performance result tables ───────────────────────────────────────
    # Each entry creates a result table attached to tests whose name
    # starts with the given prefix (empty string = all tests).
    "result_tables": [
        {
            "test_prefix": "perf-",
            "name": "throughput",
            "description_template": "Throughput and latency results for {test_pretty_name}",
            "columns": [
                {"name": "op_rate", "unit": "ops/s", "type": "float", "higher_is_better": True},
                {"name": "latency_99th", "unit": "ms", "type": "float", "higher_is_better": False},
                {"name": "latency_mean", "unit": "ms", "type": "float", "higher_is_better": False},
            ],
            "rows": ["write", "read", "mixed"],
            # Value ranges for random data generation, keyed by column name.
            # Columns not listed here get a uniform (1.0, 100.0) range.
            "value_ranges": {
                "op_rate": (50_000, 200_000),
                "latency_99th": (2.0, 50.0),
                "latency_mean": (0.5, 15.0),
            },
            # Which columns to include in the default graph view.
            "graph_columns": ["op_rate"],
        },
    ],
    # ── Sample issues ───────────────────────────────────────────────────
    # Linked to failed/errored runs (round-robin).
    # Uses nonexistent orgs/repos/projects so links never resolve to real issues.
    "github_issues": [
        {
            "owner": "fake-org",
            "repo": "fake-db",
            "number": 19001,
            "state": "open",
            "title": "Decommission fails intermittently under high load",
            "labels": [{"id": 1, "name": "bug", "color": "d73a4a", "description": "Something isn't working"}],
            "assignees": [{"login": "fake-dev", "html_url": "https://github.com/fake-dev"}],
        },
        {
            "owner": "fake-org",
            "repo": "fake-cluster-tests",
            "number": 5432,
            "state": "open",
            "title": "Stress command timeout on large partitions",
            "labels": [
                {"id": 2, "name": "test-failure", "color": "e4e669", "description": "Test infrastructure issue"},
                {"id": 3, "name": "longevity", "color": "0075ca", "description": "Longevity test related"},
            ],
            "assignees": [],
        },
    ],
    "jira_issues": [
        {
            "summary": "Investigate flaky longevity test failures in CI",
            "key": "SEED-99999",
            "state": "in progress",
            "project": "SEED",
            "permalink": "https://fake-org.atlassian.net/browse/SEED-99999",
            "labels": [{"id": 10, "name": "flaky-test", "color": "fbca04", "description": "Flaky test"}],
            "assignees": ["fake-dev"],
        },
        {
            "summary": "Performance regression in write path after compaction refactor",
            "key": "SEED-88888",
            "state": "open",
            "project": "SEED",
            "permalink": "https://fake-org.atlassian.net/browse/SEED-88888",
            "labels": [
                {"id": 11, "name": "perf-regression", "color": "d93f0b", "description": "Performance regression"}
            ],
            "assignees": [],
        },
        {
            "summary": "Node decommission timeout under mixed workloads",
            "key": "SEED-77777",
            "state": "in review",
            "project": "SEED",
            "permalink": "https://fake-org.atlassian.net/browse/SEED-77777",
            "labels": [
                {"id": 12, "name": "topology", "color": "0e8a16", "description": "Topology operations"},
                {"id": 1, "name": "bug", "color": "d73a4a", "description": "Something isn't working"},
            ],
            "assignees": ["fake-dev"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Counters for summary
# ---------------------------------------------------------------------------
COUNTS = {
    "users": 0,
    "releases": 0,
    "groups": 0,
    "tests": 0,
    "runs": 0,
    "sct_events": 0,
    "argus_events": 0,
    "result_tables": 0,
    "result_cells": 0,
    "best_results": 0,
    "graph_views": 0,
    "github_issues": 0,
    "jira_issues": 0,
    "issue_links": 0,
}


# ---------------------------------------------------------------------------
# 1. Database setup
# ---------------------------------------------------------------------------


def maybe_create_keyspace(config: dict):
    """Create the keyspaces using a raw Cassandra connection (before cqlengine)."""
    contact_points = config["SCYLLA_CONTACT_POINTS"]
    username = config["SCYLLA_USERNAME"]
    password = config["SCYLLA_PASSWORD"]
    keyspace = config["SCYLLA_KEYSPACE_NAME"]
    rf = config.get("SCYLLA_REPLICATION_FACTOR", 1)

    auth = PlainTextAuthProvider(username=username, password=password)
    cluster = Cluster(contact_points=contact_points, auth_provider=auth, protocol_version=4)
    session = cluster.connect()

    for ks in [keyspace, "argus_tablets"]:
        LOGGER.info("Creating keyspace '%s' (RF=%s) if it does not exist...", ks, rf)
        session.execute(
            f"CREATE KEYSPACE IF NOT EXISTS {ks} "
            f"WITH replication = {{'class': 'NetworkTopologyStrategy', 'replication_factor': {rf}}}"
            f" AND tablets = {{'enabled': true}}"
        )
        LOGGER.info("Keyspace '%s' is ready.", ks)

    cluster.shutdown()


def setup_db():
    """Connect to ScyllaDB and synchronize all table schemas."""
    LOGGER.info("Connecting to ScyllaDB...")
    cluster = ScyllaCluster.get()
    LOGGER.info("Syncing core tables and types...")
    sync_models(cluster.config["SCYLLA_KEYSPACE_NAME"])
    LOGGER.info("Schema sync complete.")
    return cluster


# ---------------------------------------------------------------------------
# 2. Admin user
# ---------------------------------------------------------------------------


def create_admin_user(username: str, password: str) -> User:
    """Create an admin user with all roles."""
    existing = list(User.filter(username=username).limit(1))
    if existing:
        LOGGER.info("  User '%s' already exists, skipping.", username)
        return existing[0]

    user = User.create(
        id=uuid4(),
        username=username,
        full_name=username.title() + " User",
        password=generate_password_hash(password),
        email=f"{username}@localhost",
        registration_date=datetime.now(UTC),
        roles=[UserRoles.User.value, UserRoles.Admin.value, UserRoles.Manager.value],
        api_token=str(uuid4()),
    )
    COUNTS["users"] += 1
    LOGGER.info("  Created admin user '%s' (password: %s)", username, password)
    return user


# ---------------------------------------------------------------------------
# 3. Release hierarchy
# ---------------------------------------------------------------------------


def create_release_hierarchy(admin_user: User, content: dict):
    """Create the seed release with groups and tests. Returns (release, groups_dict, tests_list)."""
    release_name = content["release_name"]
    existing = list(ArgusRelease.filter(name=release_name).limit(1))
    if existing:
        LOGGER.info("  Release '%s' already exists, skipping hierarchy creation.", release_name)
        release = existing[0]
        groups = {g.name: g for g in ArgusGroup.filter(release_id=release.id).all()}
        tests = list(ArgusTest.filter(release_id=release.id).all())
        return release, groups, tests

    release = ArgusRelease.create(
        id=uuid4(),
        name=release_name,
        pretty_name=content["release_pretty_name"],
        description=content["release_description"],
        enabled=True,
        perpetual=False,
        dormant=False,
        assignee=[admin_user.id],
    )
    COUNTS["releases"] += 1
    LOGGER.info("  Created release '%s'", release.name)

    groups = {}
    tests = []
    for gdef in content["groups"]:
        group = ArgusGroup.create(
            id=uuid4(),
            release_id=release.id,
            name=gdef["name"],
            pretty_name=gdef["pretty_name"],
            build_system_id=f"{release_name}/{gdef['name']}",
            enabled=True,
        )
        COUNTS["groups"] += 1
        groups[gdef["name"]] = group
        LOGGER.info("    Created group '%s'", group.name)

        for test_name, pretty_name in gdef["tests"]:
            build_system_id = f"{release_name}/{gdef['name']}/{test_name}"
            test = ArgusTest.create(
                id=uuid4(),
                group_id=group.id,
                release_id=release.id,
                name=test_name,
                pretty_name=pretty_name,
                build_system_id=build_system_id,
                build_system_url=f"http://jenkins.localhost/job/{build_system_id}",
                plugin_name="scylla-cluster-tests",
                enabled=True,
            )
            COUNTS["tests"] += 1
            tests.append(test)
            LOGGER.info("      Created test '%s'", test.name)

    return release, groups, tests


# ---------------------------------------------------------------------------
# 4. SCT test runs
# ---------------------------------------------------------------------------


def create_test_runs(tests: list[ArgusTest], admin_user: User, content: dict):
    """Create SCT test runs per test, spread over the last 30 days."""
    run_profiles = content["run_profiles"]
    all_runs = []
    now = datetime.now(UTC)

    for test in tests:
        existing = list(SCTTestRun.filter(build_id=test.build_system_id).limit(1))
        if existing:
            LOGGER.info("  Runs for test '%s' already exist, skipping.", test.name)
            runs = list(SCTTestRun.filter(build_id=test.build_system_id).all())
            all_runs.extend(runs)
            continue

        for i, (status, inv_status) in enumerate(run_profiles):
            start = now - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
            end = (
                start + timedelta(minutes=random.randint(30, 360))
                if status != TestStatus.RUNNING
                else datetime.fromtimestamp(0, UTC)
            )
            build_number = (i + 1) * 10 + random.randint(0, 9)

            run = SCTTestRun.create(
                build_id=test.build_system_id,
                start_time=start,
                id=uuid4(),
                release_id=test.release_id,
                group_id=test.group_id,
                test_id=test.id,
                assignee=admin_user.id,
                status=status.value,
                investigation_status=inv_status.value,
                heartbeat=int(time()),
                end_time=end,
                build_job_url=f"http://jenkins.localhost/job/{test.build_system_id}/{build_number}",
                build_number=build_number,
                product_version=f"2025.1.{random.randint(0, 5)}",
                test_name=test.name,
                scm_revision_id=f"{random.randint(0, 0xFFFFFFFF):08x}{random.randint(0, 0xFFFFFFFF):08x}",
                branch_name=random.choice(content["branches"]),
                origin_url="https://github.com/scylladb/scylla-cluster-tests.git",
                started_by=random.choice(content["committers"]),
                config_files=[f"test-cases/{test.name}.yaml"],
                scylla_version=f"6.{random.randint(0, 2)}.{random.randint(0, 9)}",
                region_name=["us-east-1"],
            )
            COUNTS["runs"] += 1
            all_runs.append(run)

        LOGGER.info("    Created %d runs for test '%s'", len(run_profiles), test.name)

    return all_runs


# ---------------------------------------------------------------------------
# 5. SCT events per run
# ---------------------------------------------------------------------------


def _events_exist_for_run(run_id) -> bool:
    """Check whether any SCT events already exist for a run (across all severities)."""
    for severity in SCTEventSeverity:
        if list(SCTEvent.filter(run_id=run_id, severity=severity.value).limit(1)):
            return True
    return False


def create_sct_events(runs: list[SCTTestRun], content: dict):
    """Create SCT events per run with varying severities.

    NOTE: The real event-submission path (sct/service.py) also enqueues
    ERROR/CRITICAL events into SCTUnprocessedEvent for the embedding
    pipeline.  This seed script intentionally skips that step — devs
    working on similar-events / embeddings should seed via the API or
    add SCTUnprocessedEvent writes here.
    """
    event_templates = content["event_templates"]
    min_events, max_events = content["events_per_run"]

    if runs and _events_exist_for_run(runs[0].id):
        LOGGER.info("  SCT events already exist, skipping.")
        return

    for run in runs:
        num_events = random.randint(min_events, max_events)
        templates = random.sample(event_templates, k=min(num_events, len(event_templates)))

        for j, (severity, event_type, msg_template) in enumerate(templates):
            ts_offset = timedelta(minutes=random.randint(1, 120))
            ts = run.start_time + ts_offset
            node = f"10.0.{random.randint(0, 3)}.{random.randint(10, 200)}"
            message = msg_template.format(
                node=node,
                step=f"step-{random.randint(1, 20)}",
                dur=random.randint(100, 9999),
                size=random.randint(50, 2000),
            )

            SCTEvent.create(
                run_id=run.id,
                severity=severity.value,
                ts=ts,
                event_id=uuid4(),
                event_type=event_type,
                message=message,
                node=node,
            )
            COUNTS["sct_events"] += 1

    LOGGER.info("  Created %d SCT events across %d runs", COUNTS["sct_events"], len(runs))


# ---------------------------------------------------------------------------
# 6. Argus events (activity feed)
# ---------------------------------------------------------------------------


def create_argus_events(runs: list[SCTTestRun], admin_user: User):
    """Create 1-2 Argus activity events per run."""
    if runs:
        sample = list(ArgusEvent.filter(run_id=runs[0].id).limit(1))
        if sample:
            LOGGER.info("  Argus events already exist, skipping.")
            return

    for run in runs:
        # Status change event
        body = json.dumps(
            {
                "message": f"Status changed to {run.status}",
                "old_status": TestStatus.CREATED.value,
                "new_status": run.status,
            }
        )
        ArgusEvent.create(
            id=uuid4(),
            release_id=run.release_id,
            group_id=run.group_id,
            test_id=run.test_id,
            run_id=run.id,
            user_id=admin_user.id,
            kind=ArgusEventTypes.TestRunStatusChanged.value,
            body=body,
            created_at=run.start_time + timedelta(seconds=random.randint(10, 300)),
        )
        COUNTS["argus_events"] += 1

        # Occasionally add an investigation status change
        if run.investigation_status != TestInvestigationStatus.NOT_INVESTIGATED.value:
            body = json.dumps(
                {
                    "message": f"Investigation status changed to {run.investigation_status}",
                    "old_status": TestInvestigationStatus.NOT_INVESTIGATED.value,
                    "new_status": run.investigation_status,
                }
            )
            ArgusEvent.create(
                id=uuid4(),
                release_id=run.release_id,
                group_id=run.group_id,
                test_id=run.test_id,
                run_id=run.id,
                user_id=admin_user.id,
                kind=ArgusEventTypes.TestRunInvestigationStatusChanged.value,
                body=body,
                created_at=run.start_time + timedelta(minutes=random.randint(5, 60)),
            )
            COUNTS["argus_events"] += 1

    LOGGER.info("  Created %d Argus activity events", COUNTS["argus_events"])


# ---------------------------------------------------------------------------
# 7. Result data (driven by content["result_tables"])
# ---------------------------------------------------------------------------


def _seed_result_table(test: ArgusTest, table_def: dict, test_runs: list[SCTTestRun]):
    """Populate one result table for a single test (cells, best results, graph view)."""
    table_name = table_def["name"]
    columns = table_def["columns"]
    rows = table_def["rows"]
    value_ranges = table_def.get("value_ranges", {})
    graph_columns = table_def.get("graph_columns", [])
    desc_template = table_def.get("description_template", "Results for {test_pretty_name}")

    # Check if metadata already exists
    if list(ArgusGenericResultMetadata.filter(test_id=test.id, name=table_name).limit(1)):
        LOGGER.info("  Result metadata for test '%s' already exists, skipping.", test.name)
        return

    ArgusGenericResultMetadata.create(
        test_id=test.id,
        name=table_name,
        description=desc_template.format(test_pretty_name=test.pretty_name),
        columns_meta=[ColumnMetadata(**col) for col in columns],
        rows_meta=rows,
        sut_package_name="scylla-server",
    )
    COUNTS["result_tables"] += 1

    best_values: dict[str, tuple[float, datetime, object]] = {}

    for run in test_runs:
        for col_def in columns:
            col_name = col_def["name"]
            lo, hi = value_ranges.get(col_name, (1.0, 100.0))
            for row_name in rows:
                value = random.uniform(lo, hi)
                ArgusGenericResultData.create(
                    test_id=test.id,
                    name=table_name,
                    run_id=run.id,
                    column=col_name,
                    row=row_name,
                    sut_timestamp=run.start_time,
                    value=value,
                    status="UNSET",
                )
                COUNTS["result_cells"] += 1

                key = f"{col_name}:{row_name}"
                cur = best_values.get(key)
                better = col_def["higher_is_better"]
                if cur is None or (better and value > cur[0]) or (not better and value < cur[0]):
                    best_values[key] = (value, run.start_time, run.id)

    for key, (value, result_date, run_id) in best_values.items():
        ArgusBestResultData.create(
            test_id=test.id,
            name=table_name,
            result_date=result_date,
            key=key,
            value=value,
            run_id=run_id,
        )
        COUNTS["best_results"] += 1

    if graph_columns:
        graphs = {}
        for row_name in rows:
            for graph_col in graph_columns:
                graphs[f"{row_name} {graph_col}"] = json.dumps(
                    {"table": table_name, "column": graph_col, "row": row_name}
                )
        ArgusGraphView.create(
            test_id=test.id,
            id=uuid4(),
            name=f"{test.pretty_name} — Overview",
            description=f"Default graph view for {table_name} metrics",
            graphs=graphs,
        )
        COUNTS["graph_views"] += 1

    LOGGER.info(
        "    Created results for test '%s': %d cells, %d best results",
        test.name,
        len(test_runs) * len(columns) * len(rows),
        len(best_values),
    )


def create_result_data(tests: list[ArgusTest], all_runs: list[SCTTestRun], content: dict):
    """Create result metadata, data cells, best results, and graph views."""
    for table_def in content["result_tables"]:
        test_prefix = table_def["test_prefix"]
        matching = [t for t in tests if t.name.startswith(test_prefix)] if test_prefix else tests
        for test in matching:
            test_runs = [r for r in all_runs if r.test_id == test.id]
            _seed_result_table(test, table_def, test_runs)


# ---------------------------------------------------------------------------
# 8. GitHub and Jira issues
# ---------------------------------------------------------------------------


def create_issues(runs: list[SCTTestRun], admin_user: User, content: dict):
    """Create sample GitHub/Jira issues and link them to failed runs."""
    failed_runs = [r for r in runs if r.status in (TestStatus.FAILED.value, TestStatus.ERROR.value)]
    if not failed_runs:
        LOGGER.info("  No failed runs to link issues to, skipping.")
        return

    # Check if issues already exist for any failed run
    for fr in failed_runs:
        sample = list(IssueLink.filter(run_id=fr.id).limit(1))
        if sample:
            LOGGER.info("  Issues already exist, skipping.")
            return

    issues_to_link: list[tuple[object, str]] = []

    # GitHub issues
    for gh_def in content.get("github_issues", []):
        gh_issue = GithubIssue.create(
            id=uuid4(),
            user_id=admin_user.id,
            type="issues",
            owner=gh_def["owner"],
            repo=gh_def["repo"],
            number=gh_def["number"],
            state=gh_def["state"],
            title=gh_def["title"],
            labels=[IssueLabel(**lbl) for lbl in gh_def.get("labels", [])],
            assignees=[IssueAssignee(**a) for a in gh_def.get("assignees", [])],
            url=f"https://github.com/{gh_def['owner']}/{gh_def['repo']}/issues/{gh_def['number']}",
        )
        COUNTS["github_issues"] += 1
        issues_to_link.append((gh_issue, "github"))

    # Jira issues
    for jira_def in content.get("jira_issues", []):
        jira_issue = JiraIssue.create(
            id=uuid4(),
            user_id=admin_user.id,
            summary=jira_def["summary"],
            key=jira_def["key"],
            state=jira_def["state"],
            project=jira_def["project"],
            permalink=jira_def["permalink"],
            labels=[IssueLabel(**lbl) for lbl in jira_def.get("labels", [])],
            assignees=jira_def.get("assignees", []),
        )
        COUNTS["jira_issues"] += 1
        issues_to_link.append((jira_issue, "jira"))

    # Link issues to failed runs (round-robin)
    for idx, (issue, issue_type) in enumerate(issues_to_link):
        target_run = failed_runs[idx % len(failed_runs)]
        IssueLink.create(
            run_id=target_run.id,
            issue_id=issue.id,
            release_id=target_run.release_id,
            group_id=target_run.group_id,
            test_id=target_run.test_id,
            user_id=admin_user.id,
            type=issue_type,
        )
        COUNTS["issue_links"] += 1

    LOGGER.info(
        "  Created %d GitHub issues, %d Jira issues, %d issue links",
        COUNTS["github_issues"],
        COUNTS["jira_issues"],
        COUNTS["issue_links"],
    )


# ---------------------------------------------------------------------------
# 9. Cleanup (--force)
# ---------------------------------------------------------------------------


def cleanup_seed_data(content: dict):
    """Remove all data created by a previous seed run."""
    LOGGER.info("Cleaning up previous seed data...")
    release_name = content["release_name"]

    releases = list(ArgusRelease.filter(name=release_name).all())
    if not releases:
        LOGGER.info("  No existing seed data found.")
        return

    release = releases[0]
    tests = list(ArgusTest.filter(release_id=release.id).all())
    groups = list(ArgusGroup.filter(release_id=release.id).all())

    # Collect all result table names from content for cleanup
    result_table_names = [t["name"] for t in content.get("result_tables", [])]

    # Delete runs and their events/results
    for test in tests:
        runs = list(SCTTestRun.filter(build_id=test.build_system_id).all())
        for run in runs:
            # SCT events — partition key is (run_id, severity), delete whole partitions
            for severity in SCTEventSeverity:
                SCTEvent.filter(run_id=run.id, severity=severity.value).delete()

            # Argus events
            argus_events = list(ArgusEvent.filter(run_id=run.id).all())
            for ev in argus_events:
                ev.delete()

            # Issue links
            links = list(IssueLink.filter(run_id=run.id).all())
            for link in links:
                for model_cls in (GithubIssue, JiraIssue):
                    try:
                        model_cls.get(id=link.issue_id).delete()
                    except model_cls.DoesNotExist:
                        pass
                link.delete()

            run.delete()

        # Delete result data
        for table_name in result_table_names:
            for m in ArgusGenericResultMetadata.filter(test_id=test.id, name=table_name).all():
                m.delete()
            ArgusGenericResultData.filter(test_id=test.id, name=table_name).delete()
            for b in ArgusBestResultData.filter(test_id=test.id, name=table_name).all():
                b.delete()

        # Delete graph views
        for v in ArgusGraphView.filter(test_id=test.id).all():
            v.delete()

        test.delete()

    for group in groups:
        group.delete()

    release.delete()
    LOGGER.info("  Cleanup complete.")


# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------


def print_summary(username: str, password: str):
    LOGGER.info("")
    LOGGER.info("=" * 60)
    LOGGER.info("  Seed Data Summary")
    LOGGER.info("=" * 60)
    for key, count in COUNTS.items():
        if count > 0:
            LOGGER.info("  %-20s %d", key.replace("_", " ").title(), count)
    LOGGER.info("-" * 60)
    LOGGER.info("  Login at:  http://localhost:5000")
    LOGGER.info("  Username:  %s", username)
    LOGGER.info("  Password:  %s", password)
    LOGGER.info("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Seed a local Argus dev database with synthetic data.",
    )
    parser.add_argument("--username", default="admin", help="Admin username (default: admin)")
    parser.add_argument("--password", default="admin", help="Admin password (default: admin)")
    parser.add_argument("--create-keyspace", action="store_true", help="Create the keyspace if it does not exist")
    parser.add_argument("--force", action="store_true", help="Delete existing seed data and recreate it")
    args = parser.parse_args()

    content = DEFAULT_CONTENT

    # Load config first (before connecting)
    config = Config.load_yaml_config()

    # Optionally create keyspace before cqlengine connects
    if args.create_keyspace:
        maybe_create_keyspace(config)

    # Connect and sync schema
    setup_db()

    # Force cleanup
    if args.force:
        cleanup_seed_data(content)

    LOGGER.info("")
    LOGGER.info("Seeding data...")

    LOGGER.info("[1/7] Creating admin user...")
    admin_user = create_admin_user(args.username, args.password)

    LOGGER.info("[2/7] Creating release hierarchy...")
    release, groups, tests = create_release_hierarchy(admin_user, content)

    LOGGER.info("[3/7] Creating test runs...")
    all_runs = create_test_runs(tests, admin_user, content)

    LOGGER.info("[4/7] Creating SCT events...")
    create_sct_events(all_runs, content)

    LOGGER.info("[5/7] Creating activity events...")
    create_argus_events(all_runs, admin_user)

    LOGGER.info("[6/7] Creating performance result data...")
    create_result_data(tests, all_runs, content)

    LOGGER.info("[7/7] Creating issues...")
    create_issues(all_runs, admin_user, content)

    print_summary(args.username, args.password)


if __name__ == "__main__":
    main()
