import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from qatools_health.check import HealthCheck
from qatools_health.result import HealthCheckResult


class SqliteHealthCheck(HealthCheck):
    name = "sqlite"
    critical = True
    interval = 60.0
    timeout = 5.0

    def __init__(
        self,
        connection: sqlite3.Connection | str | Path,
        *,
        query: str = "SELECT 1",
        **kwargs: Any,
    ) -> None:
        self.query = query
        if isinstance(connection, sqlite3.Connection):
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
            row = self.connection.execute(self.query).fetchone()
        else:
            row = await asyncio.to_thread(self._open_and_query)
        return HealthCheckResult.healthy(f"{self.query} returned {row!r}")

    def _open_and_query(self) -> Any:
        with closing(sqlite3.connect(self.db_path, timeout=self.timeout)) as connection:
            return connection.execute(self.query).fetchone()
