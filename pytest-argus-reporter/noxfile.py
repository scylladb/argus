import nox

nox.options.default_venv_backend = "uv"


@nox.session(python=["3.10", "3.11", "3.12", "3.13", "3.14"])
def tests(session):
    """Run the test suite with coverage."""

    session.install(".[dev]")
    session.run(
        "pytest",
        "-p",
        "no:argus-reporter",
        "--cov",
        "pytest_argus_reporter",
        "--cov-report=term-missing",
        "--cov-report=xml",
        *session.posargs,
    )


@nox.session(python=["3.10", "3.11", "3.12", "3.13", "3.14"])
def pre_commit(session):
    """Run pre-commit checks."""
    session.install(".[dev]")
    session.run("pre-commit", "run", "-a")
