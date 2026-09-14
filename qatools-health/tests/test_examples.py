import importlib
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(autouse=True)
def examples_on_path(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    yield
    for module in ("service", "gated_worker", "upstream"):
        sys.modules.pop(module, None)


async def test_the_service_example_reports_the_outage_and_the_recovery():
    service = importlib.import_module("service")

    lines = []
    await service.main(duration=3.4, outage_after=1.6, outage_for=0.9, emit=lines.append)
    events = [line for line in lines if line.startswith(("service ", "upstream "))]
    assert events == [
        "service HEALTHY: every dependency healthy (not healthy: optional_cache)",
        "upstream goes down",
        "service UNHEALTHY: upstream_api unhealthy (not healthy: optional_cache, upstream_api)",
        "upstream comes back",
        "service HEALTHY: every dependency healthy (not healthy: optional_cache)",
    ]
    assert 'healthcheck_status{service="example"} 2.0' in lines
    assert 'healthcheck_dependency_up{dependency="optional_cache",service="example"} 0.0' in lines


async def test_the_gated_example_pauses_the_publisher_and_tells_both_subscribers():
    gated_worker = importlib.import_module("gated_worker")

    lines = []
    publisher = await gated_worker.main(duration=3.0, outage_after=1.2, outage_for=1.0, emit=lines.append)
    gate = [line.split(":")[0] for line in lines if line.startswith(("publisher resumes", "publisher pauses"))]
    auditor = [line for line in lines if line.startswith("auditor")]
    assert gate == ["publisher resumes", "publisher pauses", "publisher resumes"]
    assert auditor == [
        "auditor heard upstream_api HEALTHY",
        "auditor heard upstream_api UNHEALTHY",
        "auditor heard upstream_api HEALTHY",
    ]
    assert "probe loops for the shared upstream: 2 checks" in lines
    down = lines.index("publisher pauses: upstream_api unhealthy (sqlite:reports=HEALTHY, upstream_api=UNHEALTHY)")
    back = next(index for index, line in enumerate(lines) if line.startswith("upstream comes back"))
    assert not [line for line in lines[down:back] if line.startswith("publisher: report")]
    assert publisher.published > 0
