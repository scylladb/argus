import subprocess
import venv
from pathlib import Path

import pytest


def run_command(command: list[str], cwd: str = None, env=None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    print(result.stdout)
    return result


@pytest.fixture(scope='module', name='build_and_install')
def fixture_build_and_install(test_dir: Path, env_dir: Path):
    """Fixture to build and install the package."""
    dist_dir = env_dir / 'dist'

    # Build the package
    run_command(['uv', 'build', '-o', str(dist_dir)], cwd=str(test_dir.parent.parent.parent))

    package_path = next(dist_dir.glob("argus_alm-*-py3-none-any.whl"))

    # install
    run_command(['uv', 'tool', 'install', str(package_path)])

    yield package_path

    run_command(['uv', 'tool', 'uninstall', 'argus-alm'])


def test_should_import_installed_package(env_dir):

    python_exec = ['uv', 'tool', 'run', '--from', 'argus-alm', 'python']
    run_command(python_exec + ['-c', 'import argus.client; import argus.common; '
                               'from argus.client.sct.client import ArgusSCTClient'])
    with pytest.raises(subprocess.CalledProcessError):
        run_command(python_exec + ['-c', 'import argus.client.tests.test_package'])


def test_should_run_cli(build_and_install):
    """Test that the CLI can be run successfully."""
    run_command(['uv', 'tool', 'run', '--from', 'argus-alm', 'argus-client-generic', '--help'])
    run_command(['uv', 'tool', 'run', '--from', 'argus-alm', 'argus-driver-matrix-client', '--help'])
