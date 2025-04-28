import logging
from uuid import UUID
import json
import re
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTTestRun

LOGGER = logging.getLogger(__name__)


class GraphedStatsService:
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_graphed_stats(self, test_id: UUID, filters=None):
        rows = SCTTestRun.filter(test_id=test_id).only([
            "build_id",
            "start_time",
            "end_time",
            "id",
            "nemesis_data",
            "investigation_status",
            "packages",
            "status"
        ]).all()

        release_data = {
            "test_runs": [],
            "nemesis_data": []
        }

        filter_patterns = []
        if filters:
            try:
                filter_patterns = [re.compile(pattern) for pattern in json.loads(filters)]
            except (json.JSONDecodeError, re.error) as e:
                LOGGER.error(f"Error parsing filters: {e}")

        for run in [row for row in rows if row["investigation_status"].lower() != "ignored"]:
            # Skip if build_id matches any filter pattern
            if filter_patterns and any(pattern.search(run["build_id"]) for pattern in filter_patterns):
                continue
            try:
                version = [package.version for package in run["packages"] if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                version = "unknown"

            duration = (run["end_time"] - run["start_time"]).total_seconds() if run["end_time"] else 0
            release_data["test_runs"].append({
                "build_id": run["build_id"],
                "start_time": run["start_time"].timestamp(),
                "duration": duration,
                "status": run["status"],
                "version": version,
                "run_id": str(run["id"]),
                "investigation_status": run["investigation_status"]
            })

            if run["nemesis_data"]:
                for nemesis in [n for n in run["nemesis_data"] if n.status in ("succeeded", "failed")]:
                    release_data["nemesis_data"].append({
                        "version": version,
                        "name": nemesis.name.split("disrupt_")[-1],
                        "start_time": nemesis.start_time,
                        "duration": nemesis.end_time - nemesis.start_time,
                        "status": nemesis.status,
                        "run_id": str(run["id"]),
                        "stack_trace": nemesis.stack_trace,
                        "build_id": run["build_id"]
                    })

        return release_data
