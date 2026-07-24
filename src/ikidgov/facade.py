"""Unified facade over the whole ikidgov toolkit.

ikidgov is deliberately composed of small, independent modules (metadata
registry, connectors, classification engine, policy engine, access control)
plus a handful of cross-cutting concerns that live outside any single module
(config resolution, connection-string resolution, SQL execution, audit
logging). That composability is great for the library internals, but it
means any *caller* that wants to do something end-to-end -- "scan this file
and classify it", "check whether analyst can select from dataset 3", "compile
grants and apply them to postgres" -- has to know about, import, and wire
together five or six different subsystems correctly, in the correct order.

``DataGovernance`` (Facade design pattern) is that single, simplified entry
point. It does not add new behavior; it only orchestrates the existing
modules so that a caller has one object to import and one place to look for
"how do I do X". Each subsystem is still reachable directly through the
module `interface.py` files for callers who want the fine-grained API -- the
facade is an additive convenience layer, not a replacement.

    from ikidgov.facade import DataGovernance

    gov = DataGovernance(config_path="config/governance.yaml")

    dataset = gov.scan("csv", "customers.csv", owner="jdoe")
    gov.classify(dataset["columns"])
    decision = gov.check_access(actor_role="analyst", action_type="select",
                                 dataset_id=dataset["dataset"]["id"])
    grants = gov.compile_grants("restrict_pii", "employees", dialect="mysql")

Layout
------
``DataGovernance`` groups related operations behind small nested facades
that are attached as attributes:

- ``.registry``      -> discovery + metadata registry (scan/register/list)
- ``.classification`` -> column classification
- ``.policy``        -> access decisions + SQL grant compilation
- ``.access_control`` -> role / permission / access CRUD
- ``.provisioning``  -> connection strings, SQL execution, DB account setup

The most common single-call operations are also exposed directly on
``DataGovernance`` itself (``scan``, ``classify``, ``check_access``,
``compile_grants``) so simple call sites don't need to reach into a
sub-facade at all.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from ikidgov.config_loader import load_config
from ikidgov.core.decision import Decision

__all__ = [
    "DataGovernance",
    "RegistryFacade",
    "ClassificationFacade",
    "PolicyFacade",
    "AccessControlFacade",
    "ProvisioningFacade",
    "MissingConnectionError",
]


class MissingConnectionError(SystemExit):
    """Raised when a dialect has no resolvable connection string.

    Subclasses SystemExit (rather than a plain exception) so callers that
    treat this as a fatal, actionable configuration error -- the historical
    behavior of the enterprise setup script -- keep working unchanged.
    """


# --------------------------------------------------------------------------
# Discovery + metadata registry
# --------------------------------------------------------------------------

class RegistryFacade:
    """Schema discovery (connectors) fronted by the metadata registry.

    Wraps the connectors package (`csv`, `json`, `sql`) and the
    `metadata_registry` module so "discover a schema and register it" is a
    single call instead of a connector lookup + a register_dataset call +
    an N-way register_column loop.
    """

    def __init__(self, *, config: dict[str, Any] | None = None):
        self._config = config

    def scan(
        self,
        source_type: str,
        path: str,
        *,
        table: str | None = None,
        owner: str | None = None,
        backend: str = "sqlite",
        description: str | None = None,
        tags: list | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Discover a schema and register it (+ its columns) in one call."""
        connector = self._build_connector(
            source_type, path, table=table, backend=backend, config=config or self._config)
        discovered = connector.discover()

        from ikidgov.modules.metadata_registry import interface as registry

        dataset = registry.register_dataset(
            source=discovered["source"], name=discovered["name"],
            owner=owner, description=description, tags=tags,
        )
        columns = []
        for column in discovered["columns"]:
            columns.append(registry.register_column(
                dataset_id=dataset["id"], name=column["name"], dtype=column.get("dtype")))
        return {"dataset": dataset, "columns": discovered["columns"], "registered_columns": columns}

    def register_dataset(self, source: str, name: str, owner: str | None = None,
                         description: str | None = None, tags: list | None = None) -> dict:
        from ikidgov.modules.metadata_registry import interface as registry
        return registry.register_dataset(source=source, name=name, owner=owner, description=description, tags=tags)

    def register_column(self, dataset_id: int, name: str, dtype: str | None = None,
                        classification: str | None = None, sensitivity_level: str = "unclassified") -> dict:
        from ikidgov.modules.metadata_registry import interface as registry
        return registry.register_column(dataset_id=dataset_id, name=name, dtype=dtype,
                                        classification=classification, sensitivity_level=sensitivity_level)

    def get_dataset(self, dataset_id: int) -> dict:
        from ikidgov.modules.metadata_registry import interface as registry
        return registry.get_dataset(dataset_id)

    def list_datasets(self) -> dict:
        from ikidgov.modules.metadata_registry import interface as registry
        return registry.list_datasets()

    @staticmethod
    def _build_connector(source_type: str, path: str, *, table: str | None,
                         backend: str, config: dict[str, Any] | None):
        if source_type == "csv":
            from ikidgov.connectors.csv_connector import CSVConnector
            return CSVConnector(path)
        if source_type == "json":
            from ikidgov.connectors.json_connector import JSONConnector
            return JSONConnector(path)
        if source_type == "sql":
            from ikidgov.connectors.sql_connector import SQLConnector
            return SQLConnector(path, table, backend=backend, config=config)
        raise ValueError(f"Unknown source_type: {source_type!r}")


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

class ClassificationFacade:
    """Tags discovered columns with a PII / sensitivity detector."""

    def classify(self, columns: list[dict], detector_name: str = "builtin") -> dict:
        from ikidgov.modules.classification_engine.interface import classify
        return classify(columns=columns, detector_name=detector_name)


# --------------------------------------------------------------------------
# Policy: decisions + grant compilation
# --------------------------------------------------------------------------

class PolicyFacade:
    """Access decisions and role-grant SQL compilation."""

    def check(self, actor_role: str, action_type: str, dataset_id: int | None = None,
              column: str | None = None, role_permissions: set[str] | list[str] | None = None) -> Decision:
        from ikidgov.modules.policy_engine.interface import check
        return check(actor_role=actor_role, action_type=action_type, dataset_id=dataset_id,
                     column=column, role_permissions=role_permissions)

    def compile_grants(self, policy_name: str, table: str, dialect: str = "generic",
                       config_path: str | None = None, config: dict | None = None) -> dict:
        from ikidgov.modules.policy_engine.interface import compile as compile_policy
        return compile_policy(policy_name=policy_name, table=table, dialect=dialect,
                              config_path=config_path, config=config)

    def load_policy_definition(self, policy_path=None) -> dict:
        from ikidgov.modules.policy_engine.impl import PolicyEngine
        return PolicyEngine().load_policy_definition(policy_path)

    def validate_policy_deployment(self, policy: dict | None, *, approver_role: str | None = None) -> dict:
        from ikidgov.modules.policy_engine.impl import PolicyEngine
        return PolicyEngine().validate_policy_deployment(policy, approver_role=approver_role)


# --------------------------------------------------------------------------
# Access control: role / permission / access CRUD
# --------------------------------------------------------------------------

class AccessControlFacade:
    """Role / permission / access-entry CRUD, one flat surface.

    Every method mirrors `modules.access_control.interface`, just grouped
    under a single object instead of a dozen loose module-level functions.
    """

    def __init__(self, db_path: str | None = None, backend: str = "sqlite"):
        self.db_path = db_path
        self.backend = backend

    def _kwargs(self, db_path: str | None, backend: str | None) -> dict:
        return {"db_path": db_path if db_path is not None else self.db_path,
                "backend": backend or self.backend}

    # -- roles ------------------------------------------------------------
    def create_role(self, name: str, description: str | None = None, *, db_path: str | None = None,
                    backend: str | None = None, **kwargs) -> dict:
        from ikidgov.modules.access_control.interface import create_role
        return create_role(name=name, description=description, **self._kwargs(db_path, backend), **kwargs)

    def get_role(self, item_id: int, *, db_path: str | None = None, backend: str | None = None) -> dict:
        from ikidgov.modules.access_control.interface import get_role
        return get_role(item_id, **self._kwargs(db_path, backend))

    def list_roles(self, *, db_path: str | None = None, backend: str | None = None) -> list[dict]:
        from ikidgov.modules.access_control.interface import list_roles
        return list_roles(**self._kwargs(db_path, backend))

    def update_role(self, item_id: int, name: str | None = None, description: str | None = None,
                    *, db_path: str | None = None, backend: str | None = None, **kwargs) -> dict:
        from ikidgov.modules.access_control.interface import update_role
        return update_role(item_id, name=name, description=description, **self._kwargs(db_path, backend), **kwargs)

    def delete_role(self, item_id: int, *, db_path: str | None = None, backend: str | None = None, **kwargs) -> bool:
        from ikidgov.modules.access_control.interface import delete_role
        return delete_role(item_id, **self._kwargs(db_path, backend), **kwargs)

    # -- permissions --------------------------------------------------------
    def create_permission(self, name: str, description: str | None = None, *, db_path: str | None = None,
                          backend: str | None = None, **kwargs) -> dict:
        from ikidgov.modules.access_control.interface import create_permission
        return create_permission(name=name, description=description, **self._kwargs(db_path, backend), **kwargs)

    def get_permission(self, item_id: int, *, db_path: str | None = None, backend: str | None = None) -> dict:
        from ikidgov.modules.access_control.interface import get_permission
        return get_permission(item_id, **self._kwargs(db_path, backend))

    def list_permissions(self, *, db_path: str | None = None, backend: str | None = None) -> list[dict]:
        from ikidgov.modules.access_control.interface import list_permissions
        return list_permissions(**self._kwargs(db_path, backend))

    def update_permission(self, item_id: int, name: str | None = None, description: str | None = None,
                          *, db_path: str | None = None, backend: str | None = None, **kwargs) -> dict:
        from ikidgov.modules.access_control.interface import update_permission
        return update_permission(item_id, name=name, description=description, **self._kwargs(db_path, backend), **kwargs)

    def delete_permission(self, item_id: int, *, db_path: str | None = None, backend: str | None = None, **kwargs) -> bool:
        from ikidgov.modules.access_control.interface import delete_permission
        return delete_permission(item_id, **self._kwargs(db_path, backend), **kwargs)

    # -- access entries -----------------------------------------------------
    def create_access(self, name: str, description: str | None = None, *, db_path: str | None = None,
                      backend: str | None = None, **kwargs) -> dict:
        from ikidgov.modules.access_control.interface import create_access
        return create_access(name=name, description=description, **self._kwargs(db_path, backend), **kwargs)

    def get_access(self, item_id: int, *, db_path: str | None = None, backend: str | None = None) -> dict:
        from ikidgov.modules.access_control.interface import get_access
        return get_access(item_id, **self._kwargs(db_path, backend))

    def list_accesses(self, *, db_path: str | None = None, backend: str | None = None) -> list[dict]:
        from ikidgov.modules.access_control.interface import list_accesses
        return list_accesses(**self._kwargs(db_path, backend))

    def update_access(self, item_id: int, name: str | None = None, description: str | None = None,
                      *, db_path: str | None = None, backend: str | None = None, **kwargs) -> dict:
        from ikidgov.modules.access_control.interface import update_access
        return update_access(item_id, name=name, description=description, **self._kwargs(db_path, backend), **kwargs)

    def delete_access(self, item_id: int, *, db_path: str | None = None, backend: str | None = None, **kwargs) -> bool:
        from ikidgov.modules.access_control.interface import delete_access
        return delete_access(item_id, **self._kwargs(db_path, backend), **kwargs)


# --------------------------------------------------------------------------
# Provisioning: connection strings, SQL execution, DB account setup
# --------------------------------------------------------------------------

class ProvisioningFacade:
    """Everything needed to talk to a real database over a connection string.

    This is the generic machinery behind "resolve where the database is,
    run SQL against it, and provision least-privilege accounts from the
    governance config" -- deliberately kept free of any example-specific
    schema/table knowledge so it's reusable outside `examples/enterprise_setup.py`.
    """

    #: env var name per non-sqlite dialect; callers may override/extend.
    DEFAULT_DIALECT_ENV_VARS = {
        "postgresql": "IKIDGOV_POSTGRES_URL",
        "mysql": "IKIDGOV_MYSQL_URL",
        "mssql": "IKIDGOV_MSSQL_URL",
    }

    def __init__(self, *, root: Path | None = None, dialect_env_vars: dict[str, str] | None = None):
        self.root = root or Path.cwd()
        self.dialect_env_vars = dict(
            dialect_env_vars or self.DEFAULT_DIALECT_ENV_VARS)

    # -- connection resolution ----------------------------------------------
    @staticmethod
    def normalize_local_url(connection_string: str) -> str:
        """Rewrite `localhost` to 127.0.0.1 (some environments resolve it oddly)."""
        return (
            connection_string
            .replace("//localhost:", "//127.0.0.1:")
            .replace("//localhost/", "//127.0.0.1/")
        )

    @staticmethod
    def mask_connection_string(connection_string: str) -> str:
        """Redact user:password@ credentials before printing/logging a connection string."""
        return re.sub(r"//([^/@]+)@", "//***:***@", connection_string)

    def load_env_file(self, env_file: Path | None = None) -> dict[str, str]:
        """Load simple KEY=VALUE pairs from a .env file. Missing file -> {}."""
        path = env_file or (self.root / ".env")
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def resolve_connection_string(
        self,
        dialect: str,
        *,
        cli_override: str | None,
        config: dict | None,
        sqlite_path: Path,
        env_file: Path | None = None,
    ) -> str:
        """Resolve a SQLAlchemy connection string for `dialect`.

        Priority: --connection-string override > env var > governance config
        (connection_string/dsn, or connection_string_env/dsn_env resolved
        against the environment) > the same config keys resolved against a
        .env file > (sqlite only) a local file. Never falls back to a
        guessed/default credential -- raises an actionable
        ``MissingConnectionError`` instead.
        """
        if dialect == "sqlite":
            return cli_override or f"sqlite:///{sqlite_path}"

        if cli_override:
            return self.normalize_local_url(cli_override)

        env_var = self.dialect_env_vars[dialect]
        from_env = os.getenv(env_var)
        if from_env:
            return self.normalize_local_url(from_env)

        dialect_config = (config or {}).get(
            dialect, {}) if isinstance(config, dict) else {}
        if isinstance(dialect_config, dict):
            from_config = dialect_config.get(
                "connection_string") or dialect_config.get("dsn")
            if from_config:
                return self.normalize_local_url(str(from_config))
            for env_key in ("connection_string_env", "dsn_env"):
                env_name = dialect_config.get(env_key)
                if isinstance(env_name, str) and env_name:
                    from_config_env = os.getenv(env_name)
                    if from_config_env:
                        return self.normalize_local_url(from_config_env)

        dotenv_values = self.load_env_file(env_file)
        from_dotenv = dotenv_values.get(env_var)
        if from_dotenv:
            return self.normalize_local_url(from_dotenv)
        if isinstance(dialect_config, dict):
            for env_key in ("connection_string_env", "dsn_env"):
                env_name = dialect_config.get(env_key)
                if isinstance(env_name, str) and env_name:
                    from_dotenv_config = dotenv_values.get(env_name)
                    if from_dotenv_config:
                        return self.normalize_local_url(from_dotenv_config)

        raise MissingConnectionError(
            f"No connection configured for '{dialect}'. Set {env_var} (directly or in "
            f"{env_file or (self.root / '.env')}), pass --connection-string, or add a "
            f"'{dialect}.connection_string' entry to your governance config."
        )

    # -- SQL execution --------------------------------------------------------
    @staticmethod
    def split_sql_statements(sql_text: str, *, dialect: str) -> list[str]:
        """Split a SQL script into individually-executable statements.

        MSSQL scripts use 'GO' batch separators; every other dialect is
        split on top-level ';' outside single-quoted strings.
        """
        if dialect == "mssql":
            batches = re.split(r"(?im)^\s*GO\s*$", sql_text)
            return [batch.strip() for batch in batches if batch.strip()]

        statements: list[str] = []
        buffer: list[str] = []
        in_quote = False
        for ch in sql_text:
            buffer.append(ch)
            if ch == "'":
                in_quote = not in_quote
            elif ch == ";" and not in_quote:
                statement = "".join(buffer).strip()
                if statement.strip(";").strip():
                    statements.append(statement)
                buffer = []
        trailing = "".join(buffer).strip()
        if trailing:
            statements.append(trailing)
        return statements

    def apply_sql(self, connection_string: str, sql_text: str, *, dialect: str, dry_run: bool,
                  on_dry_run: Any = None) -> int:
        """Execute `sql_text` against `connection_string`. Returns statement count."""
        statements = self.split_sql_statements(sql_text, dialect=dialect)
        if dry_run:
            if on_dry_run:
                on_dry_run(len(statements), dialect)
            return len(statements)
        if not statements:
            return 0

        from sqlalchemy import create_engine, text

        try:
            engine = create_engine(connection_string)
        except Exception as exc:
            raise SystemExit(
                f"Failed to execute SQL for '{dialect}': could not create a SQLAlchemy engine. "
                f"Check the connection string, install the matching driver, and ensure the target is reachable."
            ) from exc

        try:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
        except Exception as exc:
            raise SystemExit(
                f"Failed to execute SQL for '{dialect}': {exc}") from exc
        finally:
            engine.dispose()
        return len(statements)

    # -- lightweight schema-drift helper -------------------------------------
    @staticmethod
    def ensure_sqlite_column(db_path: Path | str, table: str, column: str, column_type: str = "TEXT") -> None:
        """Add `column` to `table` if it's missing. No-op if the DB/table doesn't exist yet."""
        path = Path(db_path)
        if not path.exists():
            return
        connection = sqlite3.connect(path)
        try:
            columns = [row[1] for row in connection.execute(
                f"PRAGMA table_info({table})")]
            if columns and column not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                connection.commit()
        finally:
            connection.close()

    # -- least-privilege account provisioning -------------------------------
    def provision_role_accounts(
        self,
        dialect: str,
        connection_string: str,
        *,
        policy_name: str,
        table: str,
        dry_run: bool,
        config: dict | None,
        statement_transform: Any = None,
        on_skip: Any = None,
        on_apply: Any = None,
    ) -> dict:
        """Compile per-role CREATE USER / CREATE ROLE / GRANT SQL and apply it.

        Roles without a configured password are the policy engine's
        responsibility to reject; callers typically pre-filter `config`
        (see e.g. `examples/enterprise_setup.py`'s
        `_roles_with_configured_passwords`) so those roles are skipped with
        a clear message via `on_skip` instead of raising.
        """
        if dialect == "sqlite":
            return {"applied": 0, "skipped": True, "reason": "sqlite has no server-side accounts"}

        from ikidgov.modules.policy_engine.interface import compile as compile_policy

        try:
            policy_sql = compile_policy("restrict_pii" if policy_name is None else policy_name,
                                        table, dialect=dialect, config=config)
        except ValueError as exc:
            if on_skip:
                on_skip(str(exc))
            return {"applied": 0, "skipped": True, "reason": str(exc)}

        statements = policy_sql.get("sql", [])
        if not statements:
            if on_skip:
                on_skip("no role accounts configured")
            return {"applied": 0, "skipped": True, "reason": "no role accounts configured"}

        if statement_transform:
            statements = [statement_transform(
                statement) for statement in statements]

        count = self.apply_sql(connection_string, "\n".join(
            statements), dialect=dialect, dry_run=dry_run)
        if on_apply and not dry_run:
            on_apply(count)
        return {"applied": count, "skipped": False, "sql": statements}


# --------------------------------------------------------------------------
# The facade itself
# --------------------------------------------------------------------------

class DataGovernance:
    """Single entry point for the whole ikidgov toolkit.

    Instantiate once per governance context (a config file, a database) and
    use the sub-facades -- or the convenience methods below -- instead of
    reaching into `ikidgov.modules.*` directly.
    """

    def __init__(
        self,
        config_path: str | os.PathLike[str] | None = None,
        *,
        config: dict[str, Any] | None = None,
        db_path: str | None = None,
        backend: str = "sqlite",
        root: Path | None = None,
    ):
        self.config_path = config_path
        self.config: dict[str, Any] = config if config is not None else load_config(
            str(config_path) if config_path is not None else None)

        self.registry = RegistryFacade(config=self.config)
        self.classification = ClassificationFacade()
        self.policy = PolicyFacade()
        self.access_control = AccessControlFacade(
            db_path=db_path, backend=backend)
        self.provisioning = ProvisioningFacade(root=root or Path.cwd())

    def reload_config(self, path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
        """Re-resolve the governance config and refresh dependent sub-facades."""
        self.config_path = path if path is not None else self.config_path
        self.config = load_config(
            str(self.config_path) if self.config_path is not None else None)
        self.registry = RegistryFacade(config=self.config)
        return self.config

    def describe(self) -> dict[str, Any]:
        """Introspection summary of every wired-up module -- useful for debugging/docs."""
        from ikidgov.modules.classification_engine.impl import ClassificationEngine
        from ikidgov.modules.policy_engine.impl import PolicyEngine
        from ikidgov.modules.access_control.impl import AccessControlModule

        return {
            "config_loaded": bool(self.config),
            "modules": {
                "classification_engine": ClassificationEngine().describe(),
                "policy_engine": PolicyEngine().describe(),
                "access_control": AccessControlModule().describe(),
            },
        }

    # -- top-level convenience methods (delegate to sub-facades) ------------
    def scan(self, source_type: str, path: str, *, table: str | None = None, owner: str | None = None,
             backend: str = "sqlite", description: str | None = None, tags: list | None = None) -> dict[str, Any]:
        """Discover a schema (csv/json/sql) and register it + its columns."""
        return self.registry.scan(source_type, path, table=table, owner=owner, backend=backend,
                                  description=description, tags=tags, config=self.config)

    def classify(self, columns: list[dict], detector_name: str = "builtin") -> dict:
        """Tag a set of discovered columns with a PII/sensitivity detector."""
        return self.classification.classify(columns, detector_name=detector_name)

    def check_access(self, actor_role: str, action_type: str, dataset_id: int | None = None,
                     column: str | None = None, role_permissions: set[str] | list[str] | None = None) -> Decision:
        """Evaluate a fail-closed access decision for `actor_role` performing `action_type`."""
        return self.policy.check(actor_role, action_type, dataset_id=dataset_id,
                                 column=column, role_permissions=role_permissions)

    def compile_grants(self, policy_name: str, table: str, dialect: str = "generic") -> dict:
        """Compile role-based grants into dialect-specific SQL for `table`."""
        return self.policy.compile_grants(policy_name, table, dialect=dialect, config=self.config)

    def scan_and_classify(self, source_type: str, path: str, *, table: str | None = None,
                          owner: str | None = None, backend: str = "sqlite",
                          detector_name: str = "builtin") -> dict[str, Any]:
        """Convenience: scan + register a source, then classify its columns in one call."""
        scanned = self.scan(source_type, path, table=table,
                            owner=owner, backend=backend)
        classification = self.classify(
            scanned["columns"], detector_name=detector_name)
        return {**scanned, "classification": classification}
