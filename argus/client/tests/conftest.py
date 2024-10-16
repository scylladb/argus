import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="module", autouse=True)
def test_dir():
    return Path(__file__).parent


@pytest.fixture(scope="module", autouse=True)
def env_dir(test_dir):
    env_dir = test_dir / 'test_env'
    if env_dir.exists():
        shutil.rmtree(env_dir)
    yield env_dir
    if env_dir.exists():
        shutil.rmtree(env_dir)
