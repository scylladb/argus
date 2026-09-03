import shutil
from typing import Any

from qatools_health.checks.primitives import BinaryHealthCheck, first_line, run_command
from qatools_health.result import HealthCheckResult
from qatools_health.status import HealthCheckStatus


class OpencodeHealthCheck(BinaryHealthCheck):
    name = "opencode"
    binary = "opencode"
    critical = True
    interval = 900.0


class GhCliHealthCheck(BinaryHealthCheck):
    name = "gh"
    binary = "gh"
    interval = 900.0

    def __init__(self, *, verify_auth: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.verify_auth = verify_auth

    async def perform_check(self) -> Any:
        version = await super().perform_check()
        if not self.verify_auth or version.status is not HealthCheckStatus.HEALTHY:
            return version
        path = shutil.which(self.binary)
        code, output = await run_command(path, "auth", "status")
        if code != 0:
            return HealthCheckResult(self.failure_status, f"gh auth status exited {code}: {first_line(output)}")
        return HealthCheckResult.healthy(f"{version.message}, authenticated")


class AcliHealthCheck(BinaryHealthCheck):
    name = "acli"
    binary = "acli"
    interval = 900.0


class Md2AdfHealthCheck(BinaryHealthCheck):
    name = "md2adf"
    binary = "md2adf"
    interval = 900.0


class ArgusCliHealthCheck(BinaryHealthCheck):
    name = "argus_cli"
    binary = "argus"
    interval = 900.0


class JenkinsCliHealthCheck(BinaryHealthCheck):
    name = "jenkins_cli"
    binary = "jenkins-cli"
    interval = 900.0
