from pathlib import Path
from typing import Any

import aiosqlite

from qatools_health.check import HealthCheck
from qatools_health.result import HealthCheckResult
from qatools_health.status import Severity


class SqliteHealthCheck(HealthCheck):
    name = "sqlite"
    severity = Severity.CRITICAL
    interval = 60.0
    timeout = 5.0

    def __init__(
        self,
        connection: aiosqlite.Connection | str | Path,
        *,
        query: str = "SELECT 1",
        **kwargs: Any,
    ) -> None:
        self.query = query
        if isinstance(connection, aiosqlite.Connection):
            self.connection = connection
            self.db_path = None
        else:
            self.connection = None
            self.db_path = Path(connection)
            if kwargs.get("name") is None:
                kwargs["name"] = f"sqlite:{self.db_path.stem}"
        super().__init__(**kwargs)

    async def perform_check(self) -> Any:
        if self.connection is not None:
            cursor = await self.connection.execute(self.query)
            try:
                row = await cursor.fetchone()
            finally:
                await cursor.close()
        else:
            async with aiosqlite.connect(self.db_path, timeout=self.timeout) as connection:
                cursor = await connection.execute(self.query)
                row = await cursor.fetchone()
        return HealthCheckResult.healthy(f"{self.query} returned {row!r}")
