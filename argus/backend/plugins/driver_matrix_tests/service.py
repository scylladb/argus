import base64
import logging
from uuid import UUID
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease, ArgusTest
from argus.backend.plugins.driver_matrix_tests.model import DriverTestRun


LOGGER = logging.getLogger(__name__)

class DriverMatrixService:
    def tested_versions_report(self, build_id: str) -> dict:
        db = ScyllaCluster.get()
        all_runs_for_test_query = db.prepare(f"SELECT * FROM {DriverTestRun.table_name()} WHERE build_id = ?")

        rows = list(db.session.execute(all_runs_for_test_query, parameters=(build_id,)).all())

        if len(rows) == 0:
            raise Exception(f"No results for build_id {build_id}", build_id)

        latest = rows[0]
        try:
            test: ArgusTest = ArgusTest.get(id=latest["test_id"])
            release: ArgusRelease = ArgusRelease.get(id=latest["release_id"])
        except (ArgusTest.DoesNotExist, ArgusRelease.DoesNotExist):
            raise Exception(f"Unable to find release and test information for build_id {build_id} and run_id {latest['id']}", build_id, latest["id"])
        

        version_map = {}

        for row in rows:
            driver_versions = [(col["name"], col["driver"]) for col in row["test_collection"]]
            for version, driver_type in driver_versions:
                driver_type = driver_type if driver_type else "Unknown"
                versions: list = version_map.get(driver_type, [])
                if version not in versions:
                    versions.append(version)
                    versions.sort()
                version_map[driver_type] = versions

        response = {
            "release": release.name,
            "test": test.name,
            "build_id": build_id,
            "versions": version_map,
        }
        return response

    def submit_driver_result(self, run_id: UUID | str, driver_name: str, driver_type: str, raw_xml: str) -> bool:
        xml_data = base64.decodebytes(bytes(raw_xml, encoding="utf-8"))
        DriverTestRun.submit_driver_result(UUID(run_id), driver_name, driver_type, xml_data)
        return True

    def submit_driver_failure(self, run_id: UUID | str, driver_name: str, driver_type: str, failure_reason: str) -> bool:
        DriverTestRun.submit_driver_failure(UUID(run_id), driver_name, driver_type, failure_reason)
        return True

    def submit_env_info(self, run_id: UUID | str, raw_env: str) -> bool:
        DriverTestRun.submit_env_info(UUID(run_id), raw_env)
        return True
