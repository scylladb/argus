import subprocess
import venv
from pathlib import Path

import pytest


def run_command(command: list[str], cwd: str = None, env=None):
    result = subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    print(result.stdout)
    return result


def create_virtualenv(env_dir: Path):
    venv.create(env_dir, with_pip=True)
    pip_path = env_dir / 'bin' / 'pip'
    return pip_path


def extract_version_from_pyproject(pyproject_file: Path) -> str:
    with pyproject_file.open() as file:
        for line in file:
            if line.strip().startswith("version"):
                return line.split('=')[1].strip().strip('"')


def test_should_build_package():
    run_command(['poetry', 'build'])


def test_should_create_env_and_install(test_dir: Path, env_dir: Path) -> None:
    pyproject_file = test_dir.parents[2] / 'pyproject.toml'
    version = extract_version_from_pyproject(pyproject_file)

    dist_dir = test_dir.parents[2] / 'dist'
    package_path = dist_dir / f"argus_alm-{version}-py3-none-any.whl"

    pip_path = create_virtualenv(env_dir)
    run_command([pip_path, 'install', str(package_path)])


def test_should_import_installed_package(env_dir):
    python_path = env_dir / 'bin' / 'python'

    run_command([python_path, '-c', 'import argus.client; import argus.common; '
                                    'from argus.client.sct.client import ArgusSCTClient'], env={"PYTHONPATH": str(env_dir)})
    with pytest.raises(subprocess.CalledProcessError):
        run_command([python_path, '-c', 'import argus.client.tests.test_package'], env={"PYTHONPATH": str(env_dir)})
