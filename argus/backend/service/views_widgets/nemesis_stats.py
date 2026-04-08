from collections import defaultdict
from uuid import UUID


from argus.backend.db import ScyllaCluster
from argus.backend.util.common import chunk
from argus.backend.plugins.sct.testrun import SCTNemesis, SCTTestRun
from argus.backend.util.nemesis_map import get_nemesis_name


class NemesisStatsService:
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_nemesis_data(self, test_id: UUID):
        rows = SCTTestRun.filter(test_id=test_id).only(
            ["id", "investigation_status", "packages"]).all()
        nemesis_data = []

        nemesis_rows = []
        for batch in chunk({r.id for r in rows}):
            # Typically this should result in <100 runs per test, but
            # we batch to make sure we don't exceed max cartesian product
            nemesis_rows.extend(SCTNemesis.filter(run_id__in=batch).all())

        nemesis_runs_data = defaultdict(list)
        for row in nemesis_rows:
            nemesis_runs_data[row.run_id].append(row)

        for run in [row for row in rows if row["investigation_status"].lower() != "ignored"]:
            try:
                version = [package.version for package in run["packages"]
                           if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                continue
            if not (nems := nemesis_runs_data.get(run["id"])):
                continue
            for nemesis in [nemesis for nemesis in nems if nemesis.status in ("succeeded", "failed")]:
                nemesis_data.append(
                    {
                        "version": version,
                        "name": get_nemesis_name(nemesis.name),
                        "start_time": nemesis.start_time,
                        "duration": nemesis.end_time - nemesis.start_time,
                        "status": nemesis.status,
                        "run_id": run["id"],
                        "stack_trace": nemesis.stack_trace,
                    }
                )
        return nemesis_data
