import os
import re
import sqlite3
import warnings
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


class SqliteCrudBase:
    """Generic CRUD base for simple lookup entities across SQLite and SQLAlchemy-backed databases."""

    def __init__(self, db_path: str | None = None, entities: dict[str, dict[str, str]] | None = None, backend: str = "sqlite"):
        self.db_path = str(db_path or os.getenv(
            "IKIGOV_ACCESS_CONTROL_DB_PATH") or os.getenv("IKIGOV_DB_PATH") or "crud.db")
        if db_path is None and os.getenv("IKIGOV_DB_PATH") and not os.getenv("IKIGOV_ACCESS_CONTROL_DB_PATH"):
            warnings.warn(
                "IKIGOV_DB_PATH is deprecated for access control storage. Use IKIGOV_ACCESS_CONTROL_DB_PATH instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.entities = entities or {}
        self.backend = (backend or "sqlite").lower()
        self._engine: Engine | None = None
        self._init_db()

    def _connect(self):
        if self.backend == "sqlite":
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        if self.backend in {"mysql", "postgresql", "postgres", "mssql", "sqlserver"}:
            if self._engine is None:
                url = self._connection_url()
                if self.backend in {"postgresql", "postgres"}:
                    self._engine = create_engine(url)
                elif self.backend == "mysql":
                    self._engine = create_engine(url)
                else:
                    self._engine = create_engine(url)
            return self._engine.connect()
        raise ValueError(f"Unsupported backend: {self.backend}")

    def _connection_url(self) -> str:
        raw = self.db_path if isinstance(
            self.db_path, str) else str(self.db_path)
        if raw.startswith(("postgresql://", "postgres://", "mysql://", "mysql+pymysql://", "mssql://", "mssql+pyodbc://")):
            return raw
        if self.backend in {"postgresql", "postgres"}:
            env_value = os.getenv("IKIGOV_POSTGRES_URL")
            if env_value:
                return env_value
            raise ValueError(
                "No PostgreSQL connection URL configured. Set IKIGOV_POSTGRES_URL.")
        if self.backend == "mysql":
            env_value = os.getenv("IKIGOV_MYSQL_URL")
            if env_value:
                return env_value
            raise ValueError(
                "No MySQL connection URL configured. Set IKIGOV_MYSQL_URL.")
        if self.backend in {"mssql", "sqlserver"}:
            env_value = os.getenv("IKIGOV_MSSQL_URL")
            if env_value:
                return env_value
            raise ValueError(
                "No MSSQL connection URL configured. Set IKIGOV_MSSQL_URL.")
        raise ValueError(
            f"No connection URL configured for backend {self.backend!r}. Set the appropriate IKIGOV_*_URL environment variable.")

    def _validate_identifier(self, identifier: str, kind: str = "identifier") -> None:
        from ikidgov.core.validation import validate_identifier

        validate_identifier(identifier, kind=kind)

    def _table_name(self, entity_key: str) -> str:
        entity_spec = self.entities[entity_key]
        table_name = entity_spec["table"]
        self._validate_identifier(table_name, kind="table")
        return table_name

    def _init_db(self) -> None:
        if self.backend == "sqlite":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            try:
                for entity_spec in self.entities.values():
                    table_name = entity_spec["table"]
                    self._validate_identifier(table_name, kind="table")
                    conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            description TEXT,
                            UNIQUE(name)
                        )
                        """
                    )
                conn.commit()
            finally:
                conn.close()
            return

        if self.backend in {"mysql", "postgresql", "postgres", "mssql", "sqlserver"}:
            conn = self._connect()
            try:
                for entity_spec in self.entities.values():
                    table_name = entity_spec["table"]
                    if self.backend == "mysql":
                        conn.execute(text(
                            f"CREATE TABLE IF NOT EXISTS {table_name} (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, description TEXT, UNIQUE(name))"))
                    elif self.backend in {"postgresql", "postgres"}:
                        conn.execute(text(
                            f"CREATE TABLE IF NOT EXISTS {table_name} (id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL, description TEXT, UNIQUE(name))"))
                    else:
                        conn.execute(text(
                            f"CREATE TABLE IF NOT EXISTS {table_name} (id INT IDENTITY(1,1) PRIMARY KEY, name NVARCHAR(255) NOT NULL, description NVARCHAR(MAX), UNIQUE(name))"))
                conn.commit()
            finally:
                conn.close()
            return

    def create(self, entity_key: str, name: str, description: str | None = None, **kwargs: Any) -> dict[str, Any]:
        table_name = self._table_name(entity_key)
        if self.backend == "sqlite":
            conn = self._connect()
            try:
                cursor = conn.execute(
                    f"INSERT INTO {table_name} (name, description) VALUES (?, ?)",
                    (name, description),
                )
                conn.commit()
                row = conn.execute(
                    f"SELECT id, name, description FROM {table_name} WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
                return self._row_to_dict(row)
            finally:
                conn.close()

        conn = self._connect()
        try:
            result = conn.execute(text(f"INSERT INTO {table_name} (name, description) VALUES (:name, :description)"), {
                                  "name": name, "description": description})
            conn.commit()
            insert_id = result.lastrowid if hasattr(
                result, "lastrowid") else None
            if insert_id is None:
                row = conn.execute(text(f"SELECT TOP 1 id, name, description FROM {table_name} WHERE name = :name ORDER BY id DESC"), {"name": name}).fetchone() if self.backend in {
                    "mssql", "sqlserver"} else conn.execute(text(f"SELECT id, name, description FROM {table_name} WHERE name = :name ORDER BY id DESC LIMIT 1"), {"name": name}).fetchone()
            else:
                row = conn.execute(text(f"SELECT id, name, description FROM {table_name} WHERE id = :id"), {
                                   "id": insert_id}).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def get(self, entity_key: str, item_id: int) -> dict[str, Any]:
        table_name = self._table_name(entity_key)
        conn = self._connect()
        try:
            if self.backend == "sqlite":
                row = conn.execute(
                    f"SELECT id, name, description FROM {table_name} WHERE id = ?",
                    (item_id,),
                ).fetchone()
            else:
                row = conn.execute(text(f"SELECT id, name, description FROM {table_name} WHERE id = :id"), {
                                   "id": item_id}).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list(self, entity_key: str) -> list[dict[str, Any]]:
        table_name = self._table_name(entity_key)
        conn = self._connect()
        try:
            if self.backend == "sqlite":
                rows = conn.execute(
                    f"SELECT id, name, description FROM {table_name} ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute(
                    text(f"SELECT id, name, description FROM {table_name} ORDER BY id")).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def update(self, entity_key: str, item_id: int, **updates: Any) -> dict[str, Any]:
        table_name = self._table_name(entity_key)
        assignments: list[str] = []
        if "name" in updates and updates.get("name") is not None:
            assignments.append("name = ?" if self.backend ==
                               "sqlite" else "name = :name")
        if "description" in updates and updates.get("description") is not None:
            assignments.append("description = ?" if self.backend ==
                               "sqlite" else "description = :description")
        if not assignments:
            return self.get(entity_key, item_id)

        conn = self._connect()
        try:
            if self.backend == "sqlite":
                params: list[Any] = []
                for update_key in ("name", "description"):
                    if update_key in updates and updates.get(update_key) is not None:
                        params.append(updates[update_key])
                params.append(item_id)
                conn.execute(
                    f"UPDATE {table_name} SET {', '.join(assignments)} WHERE id = ?",
                    params,
                )
            else:
                params: dict[str, Any] = {}
                if "name" in updates and updates.get("name") is not None:
                    params["name"] = updates["name"]
                if "description" in updates and updates.get("description") is not None:
                    params["description"] = updates["description"]
                params["id"] = item_id
                conn.execute(text(
                    f"UPDATE {table_name} SET {', '.join(assignments)} WHERE id = :id"), params)
            conn.commit()
            row = conn.execute(text(f"SELECT id, name, description FROM {table_name} WHERE id = :id"), {"id": item_id}).fetchone() if self.backend != "sqlite" else conn.execute(
                f"SELECT id, name, description FROM {table_name} WHERE id = ?",
                (item_id,),
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def delete(self, entity_key: str, item_id: int) -> bool:
        table_name = self._table_name(entity_key)
        conn = self._connect()
        try:
            if self.backend == "sqlite":
                cursor = conn.execute(
                    f"DELETE FROM {table_name} WHERE id = ?", (item_id,))
            else:
                cursor = conn.execute(
                    text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": item_id})
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        if not row:
            return {}
        if hasattr(row, "keys"):
            return {"id": row["id"], "name": row["name"], "description": row["description"]}
        return {"id": row[0], "name": row[1], "description": row[2]}
