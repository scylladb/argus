from uuid import UUID
from argus.backend.util.enums import TestStatus
from argus.client.base import ArgusClient
from argus.backend.plugins.driver_matrix_tests.model import RawMatrixTestResult


class ArgusDriverMatrixClient(ArgusClient):
    test_type = "driver-matrix-tests"
    schema_version: None = "v1"

    def __init__(self, run_id: UUID, auth_token: str, base_url: str, api_version="v1") -> None:
        super().__init__(auth_token, base_url, api_version)
        self.run_id = run_id

    def submit_driver_matrix_run(self, job_name: str, job_url: str,
                                 results: list[RawMatrixTestResult], test_environment: dict[str, str]) -> None:
        response = super().submit_run(run_type=self.test_type, run_body={
            "run_id": str(self.run_id),
            "job_name": job_name,
            "job_url": job_url,
            "test_environment": test_environment,
            "matrix_results": results
        })

        self.check_response(response)

    def set_matrix_status(self, status: TestStatus):
        response = super().set_status(run_type=self.test_type, run_id=self.run_id, new_status=status)
        self.check_response(response)
