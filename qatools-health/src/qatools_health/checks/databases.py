"""The checks that query a database."""

from pathlib import Path
from typing import Any

import aiosqlite

from qatools_health.check import HealthCheck
from qatools_health.result import HealthCheckResult
from qatools_health.status import Severity


class SqliteHealthCheck(HealthCheck):
    """Run one query against a SQLite database and report the row.

    A live connection is awaited as it is. A path opens read-write for the one
    query, so a database file that is absent stays absent and the check reports
    UNHEALTHY.
    """

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
        """Open the database if a path was given, then run the query."""
        if self.connection is not None:
            return await self._query(self.connection)
        if not self.db_path.is_file():
            return HealthCheckResult.unhealthy(f"{self.db_path} does not exist")
        uri = f"file:{self.db_path.as_posix()}?mode=rw"
        async with aiosqlite.connect(uri, uri=True, timeout=self.timeout) as connection:
            return await self._query(connection)

    async def _query(self, connection: aiosqlite.Connection) -> HealthCheckResult:
        cursor = await connection.execute(self.query)
        try:
            row = await cursor.fetchone()
        finally:
            await cursor.close()
        return HealthCheckResult.healthy(f"{self.query} returned {row!r}")
