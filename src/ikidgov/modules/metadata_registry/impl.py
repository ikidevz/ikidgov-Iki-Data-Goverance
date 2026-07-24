import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from ikidgov.core.module_base import Module

DEFAULT_DB_PATH = Path(os.getenv("IKIDGOV_REGISTRY_DB_PATH",
                       os.getenv("IKIDGOV_DB_PATH", "registry.db")))
SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    name TEXT NOT NULL,
    owner TEXT,
    description TEXT,
    tags TEXT,
    UNIQUE(source, name)
);

CREATE TABLE IF NOT EXISTS columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    dtype TEXT,
    classification TEXT,
    sensitivity_level TEXT,
    UNIQUE(dataset_id, name)
);
"""


class MetadataRegistry(Module):
    name = "metadata_registry"

    def __init__(self, db_path: str | None = None):
        selected_db_path = db_path or os.getenv(
            "IKIDGOV_REGISTRY_DB_PATH") or os.getenv("IKIDGOV_DB_PATH")
        if db_path is None and selected_db_path and not os.getenv("IKIDGOV_REGISTRY_DB_PATH") and os.getenv("IKIDGOV_DB_PATH"):
            import warnings

            warnings.warn(
                "IKIDGOV_DB_PATH is deprecated for metadata registry storage. Use IKIDGOV_REGISTRY_DB_PATH instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.db_path = Path(selected_db_path or DEFAULT_DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "actions": ["register_dataset", "register_column", "get_dataset", "list_datasets"]}

    def run(self, **kwargs) -> dict[str, Any]:
        action = kwargs.get("action")
        if not action:
            return self._action_list_datasets()
        if action == "register_dataset":
            return self._action_register_dataset(**kwargs)
        if action == "register_column":
            return self._action_register_column(**kwargs)
        if action == "get_dataset":
            return self._action_get_dataset(**kwargs)
        if action == "list_datasets":
            return self._action_list_datasets()
        raise ValueError(action)

    def _action_register_dataset(self, **kwargs) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "INSERT INTO datasets (source, name, owner, description, tags) VALUES (?, ?, ?, ?, ?) ON CONFLICT(source, name) DO NOTHING",
                (
                    kwargs.get("source"),
                    kwargs.get("name"),
                    kwargs.get("owner"),
                    kwargs.get("description"),
                    json.dumps(kwargs.get("tags") or []),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, source, name, owner, description, tags FROM datasets WHERE source = ? AND name = ?",
                (kwargs.get("source"), kwargs.get("name")),
            ).fetchone()
            return {
                "id": row[0],
                "source": row[1],
                "name": row[2],
                "owner": row[3],
                "description": row[4],
                "tags": json.loads(row[5] or "[]"),
            }
        finally:
            conn.close()

    def _action_register_column(self, **kwargs) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO columns (id, dataset_id, name, dtype, classification, sensitivity_level) VALUES ((SELECT id FROM columns WHERE dataset_id = ? AND name = ?), ?, ?, ?, ?, ?)",
                (
                    kwargs.get("dataset_id"),
                    kwargs.get("name"),
                    kwargs.get("dataset_id"),
                    kwargs.get("name"),
                    kwargs.get("dtype"),
                    kwargs.get("classification"),
                    kwargs.get("sensitivity_level"),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, dataset_id, name, dtype, classification, sensitivity_level FROM columns WHERE dataset_id = ? AND name = ?",
                (kwargs.get("dataset_id"), kwargs.get("name")),
            ).fetchone()
            return {"id": row[0], "dataset_id": row[1], "name": row[2], "dtype": row[3], "classification": row[4], "sensitivity_level": row[5]}
        finally:
            conn.close()

    def _action_get_dataset(self, **kwargs) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, source, name, owner, description, tags FROM datasets WHERE id = ?",
                (kwargs.get("dataset_id"),),
            ).fetchone()
            if not row:
                return {}
            column_rows = conn.execute(
                "SELECT name, dtype, classification, sensitivity_level FROM columns WHERE dataset_id = ? ORDER BY id",
                (row[0],),
            ).fetchall()
            return {
                "id": row[0],
                "source": row[1],
                "name": row[2],
                "owner": row[3],
                "description": row[4],
                "tags": json.loads(row[5] or "[]"),
                "columns": [
                    {
                        "name": column_row[0],
                        "dtype": column_row[1],
                        "classification": column_row[2],
                        "sensitivity_level": column_row[3],
                    }
                    for column_row in column_rows
                ],
            }
        finally:
            conn.close()

    def _action_list_datasets(self) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, source, name, owner, description, tags FROM datasets ORDER BY id").fetchall()
            return [{
                "id": row[0],
                "source": row[1],
                "name": row[2],
                "owner": row[3],
                "description": row[4],
                "tags": json.loads(row[5] or "[]"),
            } for row in rows]
        finally:
            conn.close()
