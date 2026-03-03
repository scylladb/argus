from uuid import UUID


from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTNemesis, SCTTestRun
from argus.backend.util.nemesis_map import get_nemesis_name


class NemesisStatsService:
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_nemesis_data(self, test_id: UUID):
        runs = SCTTestRun.filter(test_id=test_id).only(["id", "investigation_status", "packages"]).all()
        nemesis_data = []
        for run in [row for row in runs if row["investigation_status"].lower() != "ignored"]:
            try:
                version = [package.version for package in run["packages"] if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                continue
            for nemesis in SCTNemesis.filter(run_id=run["id"]).all():
                if nemesis.status not in ("succeeded", "failed"):
                    continue
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
