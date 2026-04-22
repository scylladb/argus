#!/usr/bin/env python3
"""Bulk-seed test runs to reproduce dashboard slowness at scale.

Usage:
    python dev-db/bulk_seed_runs.py --runs 1000
    python dev-db/bulk_seed_runs.py --runs 10000
    python dev-db/bulk_seed_runs.py --runs 1000 --release seed-release

Adds N runs spread evenly across all tests of the given release.
Runs from the repository root so argus_web.yaml is found automatically.
"""

import argparse
import logging
import os
import random
from datetime import UTC, datetime, timedelta
from time import time
from uuid import uuid4

os.environ["CQLENG_ALLOW_SCHEMA_MANAGEMENT"] = "1"

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease, ArgusTest, User
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sct.udt import CloudSetupDetails, CloudNodesInfo
from argus.backend.util.config import Config
from argus.common.enums import TestInvestigationStatus, TestStatus
from argus.backend.cli import sync_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOGGER = logging.getLogger("bulk_seed")

STATUSES = [
    (TestStatus.PASSED, TestInvestigationStatus.NOT_INVESTIGATED),
    (TestStatus.PASSED, TestInvestigationStatus.NOT_INVESTIGATED),
    (TestStatus.FAILED, TestInvestigationStatus.IN_PROGRESS),
    (TestStatus.ERROR, TestInvestigationStatus.INVESTIGATED),
    (TestStatus.ABORTED, TestInvestigationStatus.NOT_INVESTIGATED),
]
BRANCHES = ["master", "branch-2025.1", "next", "enterprise", "branch-6.2"]
COMMITTERS = ["jenkins-bot", "dev-user", "ci-runner", "test-automation"]
REGIONS = [["us-east-1"], ["eu-west-1"], ["us-west-2"]]
VERSIONS = [f"6.{minor}.{patch}" for minor in range(3) for patch in range(10)]
IMAGE_IDS = [
    "ami-0abcdef1234567890",
    "ami-0fedcba9876543210",
    "ami-0a1b2c3d4e5f67890",
    "ami-0deadbeefcafe0000",
    "ami-0cafebabe12345678",
]


def setup_db():
    Config.load_yaml_config()
    cluster = ScyllaCluster.get()
    sync_models(cluster.config["SCYLLA_KEYSPACE_NAME"])
    return cluster


def bulk_seed(release_name: str, total_runs: int, batch_log: int = 500):
    tests = list(ArgusTest.filter(release_id=ArgusRelease.filter(name=release_name).get().id).all())
    if not tests:
        LOGGER.error("No tests found for release '%s'", release_name)
        return

    admin = list(User.filter(username="admin").limit(1))
    admin_user = admin[0] if admin else None

    LOGGER.info("Found %d tests in release '%s'. Creating %d runs...", len(tests), release_name, total_runs)
    now = datetime.now(UTC)
    created = 0

    for i in range(total_runs):
        test = tests[i % len(tests)]
        status, inv_status = random.choice(STATUSES)
        start = now - timedelta(days=random.randint(1, 365), hours=random.randint(0, 23))
        end = (
            start + timedelta(minutes=random.randint(30, 360))
            if status != TestStatus.RUNNING
            else datetime.fromtimestamp(0, UTC)
        )
        build_number = random.randint(1, 9999)

        SCTTestRun.create(
            build_id=test.build_system_id,
            start_time=start,
            id=uuid4(),
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id,
            assignee=admin_user.id if admin_user else uuid4(),
            status=status.value,
            investigation_status=inv_status.value,
            heartbeat=int(time()),
            end_time=end,
            build_job_url=f"http://jenkins.localhost/job/{test.build_system_id}/{build_number}",
            build_number=build_number,
            product_version=f"2025.1.{random.randint(0, 9)}",
            test_name=test.name,
            scm_revision_id=f"{random.randint(0, 0xFFFFFFFF):08x}{random.randint(0, 0xFFFFFFFF):08x}",
            branch_name=random.choice(BRANCHES),
            origin_url="https://github.com/scylladb/scylla-cluster-tests.git",
            started_by=random.choice(COMMITTERS),
            config_files=[f"test-cases/{test.name}.yaml"],
            scylla_version=random.choice(VERSIONS),
            region_name=random.choice(REGIONS),
            cloud_setup=CloudSetupDetails(
                backend="aws",
                db_node=CloudNodesInfo(
                    image_id=random.choice(IMAGE_IDS),
                    instance_type="i3.2xlarge",
                    node_amount=3,
                    post_behaviour="keep",
                ),
            ),
        )
        created += 1
        if created % batch_log == 0:
            LOGGER.info("  %d / %d runs created...", created, total_runs)

    LOGGER.info("Done. Created %d runs across %d tests.", created, len(tests))


def main():
    parser = argparse.ArgumentParser(description="Bulk-seed test runs for performance testing.")
    parser.add_argument("--runs", type=int, default=1000, help="Number of runs to create (default: 1000)")
    parser.add_argument("--release", default="seed-release", help="Release name (default: seed-release)")
    args = parser.parse_args()

    setup_db()
    bulk_seed(args.release, args.runs)


if __name__ == "__main__":
    main()
