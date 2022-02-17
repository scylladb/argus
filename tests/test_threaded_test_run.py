from uuid import uuid4
import logging
import time
import pytest
from mocks.mock_cluster import MockSession
from argus.db.testrun import TestRunWithHeartbeat, TestRunInfo
from argus.db.interface import ArgusDatabase

LOGGER = logging.getLogger(__name__)


class FakeCursor:
    # pylint: disable=too-few-public-methods
    @staticmethod
    def one():
        return True


def test_heartbeat_thread(completed_testrun: TestRunInfo, mock_cluster: ArgusDatabase, monkeypatch: pytest.MonkeyPatch, mock_cql_engine):
    # pylint: disable=unused-argument
    monkeypatch.setattr(MockSession, "MOCK_RESULT_SET", FakeCursor())
    test_id = uuid4()
    test_run = TestRunWithHeartbeat(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="k0machi",
                                    run_info=completed_testrun, heartbeat_interval=3)

    old_ts = test_run.heartbeat
    for i in range(1, 4):
        LOGGER.info("Checking timestamp %s", i)
        time.sleep(5)
        new_ts = test_run.heartbeat
        assert new_ts != old_ts
        old_ts = new_ts

    test_run.shutdown()
    time.sleep(0.5)
    assert not test_run._thread.is_alive()  # pylint: disable=protected-access


def test_heartbeat_thread_shutdown(completed_testrun: TestRunInfo, mock_cluster: ArgusDatabase,
                                   monkeypatch: pytest.MonkeyPatch, mock_cql_engine):
    # pylint: disable=unused-argument
    monkeypatch.setattr(MockSession, "MOCK_RESULT_SET", FakeCursor())
    test_id = uuid4()
    test_run = TestRunWithHeartbeat(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="k0machi",
                                    run_info=completed_testrun, heartbeat_interval=15)

    test_run.shutdown()
    assert not test_run._thread.is_alive()  # pylint: disable=protected-access
