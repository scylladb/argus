"""Regression guard for ArgusGenericClient.trigger_jobs URL construction.

The planner router is mounted at ``/api/v1/planning`` -- outside the
``/api/v1/client`` sub-tree every other client route lives under. The client
used to prefix this route with ``/client`` too, 404ing against any real
server; this test drives the real URL end-to-end.

``mock_jenkins_service`` patches the backend import site, which works here
because uvicorn serves the app from within this process.
"""

from datetime import UTC, datetime

import pytest
from cassandra.util import uuid_from_time

pytestmark = pytest.mark.docker_required


def test_trigger_jobs_reaches_planner_endpoint(generic_client, mock_jenkins_service):
    result = generic_client.trigger_jobs(
        common_params={},
        params=[],
        plan_id=str(uuid_from_time(datetime.now(tz=UTC))),
    )
    assert result["status"] == "ok"
    # No plan matches the fresh id: the service reports (False, "No plans to
    # trigger"), serialized as a 2-element list. Reaching the service at all
    # proves the URL resolves.
    assert result["response"] == [False, "No plans to trigger"]
    mock_jenkins_service.return_value.build_job.assert_not_called()
