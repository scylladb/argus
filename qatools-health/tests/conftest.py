import pytest
from support import FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
