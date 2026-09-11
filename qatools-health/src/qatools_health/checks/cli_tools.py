"""The checks over the command-line tools the QA services shell out to."""

import shutil
from typing import Any

from qatools_health.checks.primitives import BinaryHealthCheck, first_line, run_command
from qatools_health.result import HealthCheckResult
from qatools_health.status import HealthCheckStatus, Severity


class OpencodeHealthCheck(BinaryHealthCheck):
    """The opencode binary resolves and answers."""

    name = "opencode"
    binary = "opencode"
    severity = Severity.CRITICAL
    interval = 900.0


class GhCliHealthCheck(BinaryHealthCheck):
    """The gh binary resolves and answers.

    Pass verify_auth to also run gh auth status, for a service that wants the
    binary and the token as one cell on the dashboard.
    """

    name = "gh"
    binary = "gh"
    interval = 900.0

    def __init__(self, *, verify_auth: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.verify_auth = verify_auth

    async def perform_check(self) -> Any:
        """Read the gh version, then confirm the token when verify_auth is set."""
        version = await super().perform_check()
        if not self.verify_auth or version.status is not HealthCheckStatus.HEALTHY:
            return version
        path = shutil.which(self.binary)
        code, output = await run_command(path, "auth", "status")
        if code != 0:
            return HealthCheckResult.unhealthy(f"gh auth status exited {code}: {first_line(output)}")
        return HealthCheckResult.healthy(f"{version.message}, authenticated")


class AcliHealthCheck(BinaryHealthCheck):
    """The acli binary resolves and answers."""

    name = "acli"
    binary = "acli"
    interval = 900.0


class ArgusCliHealthCheck(BinaryHealthCheck):
    """The argus binary resolves and answers."""

    name = "argus_cli"
    binary = "argus"
    interval = 900.0


class JenkinsCliHealthCheck(BinaryHealthCheck):
    """The jenkins-cli binary resolves and answers."""

    name = "jenkins_cli"
    binary = "jenkins-cli"
    interval = 900.0
