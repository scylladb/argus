from uuid import UUID


from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTTestRun


class NemesisStatsService:
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_nemesis_data(self, test_id: UUID):
        rows = SCTTestRun.filter(test_id=test_id).only(["id", "nemesis_data", "investigation_status", "packages"]).all()
        nemesis_data = []
        for run in [row for row in rows if row["investigation_status"].lower() != "ignored"]:
            try:
                version = [package.version for package in run["packages"] if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                continue
            if not run["nemesis_data"]:
                continue
            for nemesis in [nemesis for nemesis in run["nemesis_data"] if nemesis.status in ("succeeded", "failed")]:
                nemesis_data.append(
                    {
                        "version": version,
                        "name": nemesis.name.split("disrupt_")[-1],
                        "start_time": nemesis.start_time,
                        "duration": nemesis.end_time - nemesis.start_time,
                        "status": nemesis.status,
                        "run_id": run["id"],
                        "stack_trace": nemesis.stack_trace,
                    }
                )
        return nemesis_data
