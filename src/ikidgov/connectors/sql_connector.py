from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ikidgov.config_loader import get_connectors_config, load_config
from ikidgov.core.connector_base import Connector
from ikidgov.core.validation import validate_table_name


class SQLConnector(Connector):
    source = "sql"

    def __init__(self, path: str, table: str | None = None, *, backend: str | None = None, config: dict[str, Any] | None = None):
        self.backend = backend or "sqlite"
        self.config = config or load_config()
        super().__init__(path, table)

    def _validate_table_name(self, table: str | None) -> str:
        return validate_table_name(table)

    def _get_backend_config(self) -> dict[str, Any]:
        if not isinstance(self.config, dict):
            return {}
        backend_key = self.backend
        if backend_key in {"postgres", "postgresql"}:
            backend_key = "postgresql"
        backend_config = self.config.get(backend_key, {})
        if isinstance(backend_config, dict):
            return backend_config
        return {}

    def _discover_sqlite(self, table_name: str) -> list[dict[str, Any]]:
        path = Path(self.path)
        if not path.exists():
            raise FileNotFoundError(path)
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        finally:
            conn.close()
        return [{"name": row[1], "dtype": row[2]} for row in rows]

    def _discover_sqlalchemy(self, table_name: str) -> list[dict[str, Any]]:
        try:
            from sqlalchemy import create_engine, text
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "SQLAlchemy is required for non-sqlite SQL discovery") from exc

        backend_config = self._get_backend_config()
        connection_string = backend_config.get(
            "connection_string") or backend_config.get("dsn")
        if not connection_string:
            raise ValueError(
                f"No connection string configured for backend '{self.backend}'")

        engine = create_engine(connection_string)
        with engine.connect() as connection:
            result = connection.execute(
                text(f"SELECT * FROM {table_name} LIMIT 0"))
            columns = result.keys()
        return [{"name": column_name, "dtype": "unknown"} for column_name in columns]

    def _probe_connection(self) -> bool:
        if self.backend == "sqlite":
            return Path(self.path).exists()
        return True

    def check_health(self, *, retries: int = 3, initial_delay: float = 0.0) -> dict[str, Any]:
        delay = initial_delay
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                if self._probe_connection():
                    return {"healthy": True, "backend": self.backend, "attempts": attempt}
            except Exception as exc:  # pragma: no cover - exercised via tests
                last_error = exc
            if attempt < retries:
                time.sleep(delay)
                delay = max(delay, 0.0)
        return {"healthy": False, "backend": self.backend, "attempts": retries, "error": str(last_error)}

    def discover(self) -> dict:
        table_name = self._validate_table_name(self.table)
        if self.backend == "sqlite":
            columns = self._discover_sqlite(table_name)
        else:
            columns = self._discover_sqlalchemy(table_name)
        return {"source": self.source, "name": table_name, "columns": columns}
