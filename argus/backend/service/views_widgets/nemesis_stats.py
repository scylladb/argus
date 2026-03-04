from collections import defaultdict
from uuid import UUID


from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis, SCTTestRun
from argus.backend.util.common import chunk
from argus.backend.util.nemesis_map import get_nemesis_name


class NemesisStatsService:
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_nemesis_data(self, test_id: UUID):
        runs = SCTTestRun.filter(test_id=test_id).only(["id", "investigation_status", "packages"]).all()
        filtered_runs = [row for row in runs if row["investigation_status"].lower() != "ignored"]

        if not filtered_runs:
            return []

        # Batch-fetch all nemesis rows for all run IDs to stay within the IN statement limit
        run_ids = [run["id"] for run in filtered_runs]
        stmt = self.cluster.prepare(
            f"SELECT run_id, name, start_time, end_time, status, stack_trace FROM {SCTNemesis.table_name()} WHERE run_id IN ?"
        )
        nemeses_by_run: dict[UUID, list] = defaultdict(list)
        for batch in chunk(run_ids):
            for nem in self.cluster.session.execute(stmt, [batch]):
                nemeses_by_run[nem["run_id"]].append(nem)

        nemesis_data = []
        for run in filtered_runs:
            try:
                version = [package.version for package in run["packages"] if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                continue
            for nem in nemeses_by_run.get(run["id"], []):
                if nem["status"] not in ("succeeded", "failed"):
                    continue
                nemesis_data.append(
                    {
                        "version": version,
                        "name": get_nemesis_name(nem["name"]),
                        "start_time": nem["start_time"],
                        "duration": nem["end_time"] - nem["start_time"],
                        "status": nem["status"],
                        "run_id": run["id"],
                        "stack_trace": nem["stack_trace"],
                    }
                )
        return nemesis_data
