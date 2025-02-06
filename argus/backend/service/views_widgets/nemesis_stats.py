from dataclasses import dataclass
from uuid import UUID


from argus.backend.db import ScyllaCluster

@dataclass
class NemesisStats:
    version: str
    name: str
    duration: int
    status: str


class NemesisStatsService:

    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_nemesis_data(self, test_id: UUID):
        runs_details_query = self.cluster.prepare(
            f"SELECT id, nemesis_data, investigation_status, packages FROM {"sct_test_run"} WHERE test_id = ?")
        rows = self.cluster.session.execute(runs_details_query, parameters=(test_id,)).all()
        nemesis_data = []
        for test in [row for row in rows if row["investigation_status"].lower() != "ignored"]:
            try:
                version = [package.version for package in test["packages"] if package.name == "scylla-server"][0]
            except (IndexError, TypeError):
                continue
            if not test["nemesis_data"]:
                continue
            for nemesis in [nemesis for nemesis in test["nemesis_data"]  if nemesis.status in ("succeeded", "failed")]:
                nemesis_data.append({"version": version, "name": nemesis.name.split("disrupt_")[-1], "duration": nemesis.end_time - nemesis.start_time,
                                    "status": nemesis.status})
        return nemesis_data
