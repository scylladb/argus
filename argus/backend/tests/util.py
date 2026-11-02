import json
import re
import uuid

from argus.backend.models.web import ArgusTest
from argus.backend.plugins.sct.testrun import SCTTestRunSubmissionRequest


def client_post(api_client, path: str, payload: dict | None = None):
    return api_client.post(path, json=payload or {})


def script_value(page: str, name: str):
    """Decode the literal a page assigns to `const <name>` in its script."""
    match = re.search(rf"const {name} = (.*);", page)
    assert match, f"const {name} not found in the page"
    return json.loads(match.group(1))


def get_fake_test_run(
        test: ArgusTest,
        schema_version: str = "1.0.0",
        job_url: str = "http://example.com/job/42",
        started_by: str = "default_user",
        commit_id: str = "default_commit_id",
        sct_config: dict | None = None,
        origin_url: str | None = None,
        branch_name: str | None = "main",
        runner_public_ip: str | None = None,
        runner_private_ip: str | None = None
) -> tuple[str, SCTTestRunSubmissionRequest]:
    run_id = str(uuid.uuid4())
    return "scylla-cluster-tests", SCTTestRunSubmissionRequest(
        schema_version=schema_version,
        run_id=run_id,
        job_name=test.build_system_id,
        job_url=job_url,
        started_by=started_by,
        commit_id=commit_id,
        sct_config=sct_config,
        origin_url=origin_url,
        branch_name=branch_name,
        runner_public_ip=runner_public_ip,
        runner_private_ip=runner_private_ip
    )
