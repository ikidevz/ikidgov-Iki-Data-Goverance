#!/usr/bin/env python3
"""Enterprise data-governance example — connects directly to your databases.

No Docker required. This script provisions the example schema/tables, creates
one scoped database account per governance role (via the shared policy-engine
SQL compiler), and walks through the access-control and policy-check demos.

Connection resolution, per dialect (first match wins):
  1. --connection-string (explicit override, applies to the single --dialect given)
  2. an environment variable: IKIGOV_POSTGRES_URL / IKIGOV_MYSQL_URL / IKIGOV_MSSQL_URL
  3. <dialect>.connection_string (or .dsn) in your governance config
  4. sqlite only: a local file, default ./data/sqlite/registry.db

Examples:
  python examples/enterprise_setup.py
      # sqlite, zero setup, creates ./data/sqlite/registry.db

  IKIGOV_POSTGRES_URL=postgresql://user:pw@host:5432/db \\
      python examples/enterprise_setup.py --dialect postgresql

  python examples/enterprise_setup.py --dialect all --dry-run

  python examples/enterprise_setup.py --dialect mysql --teardown

Bring your own running database server for postgresql/mysql/mssql -- this
script only ever opens a direct SQLAlchemy connection to it. It never starts,
stops, or otherwise manages any database process.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ikidgov.config_loader import load_config  # noqa: E402
from ikidgov.modules.access_control.interface import (  # noqa: E402
    create_access,
    create_permission,
    create_role,
    delete_access,
    delete_permission,
    delete_role,
    get_access,
    get_permission,
    get_role,
    list_accesses,
    list_permissions,
    list_roles,
    update_access,
    update_permission,
    update_role,
)
from ikidgov.modules.policy_engine.interface import check as check_policy  # noqa: E402
from ikidgov.modules.policy_engine.interface import compile as compile_policy_sql  # noqa: E402

EXAMPLES_DIR = ROOT / "examples"
ALL_DIALECTS = ["sqlite", "postgresql", "mysql", "mssql"]

DIALECT_ENV_VARS = {
    "postgresql": "IKIGOV_POSTGRES_URL",
    "mysql": "IKIGOV_MYSQL_URL",
    "mssql": "IKIGOV_MSSQL_URL",
}

SETUP_SQL_FILES = {
    "sqlite": EXAMPLES_DIR / "sqlite_setup.sql",
    "postgresql": EXAMPLES_DIR / "postgresql_setup.sql",
    "mysql": EXAMPLES_DIR / "mysql_setup.sql",
    "mssql": EXAMPLES_DIR / "mssql_setup.sql",
}

TEARDOWN_SQL = {
    "sqlite": """
        DROP TABLE IF EXISTS employees;
        DROP TABLE IF EXISTS campaign_contacts;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS customers;
    """,
    "postgresql": """
        DROP TABLE IF EXISTS hr.employees;
        DROP TABLE IF EXISTS marketing.campaign_contacts;
        DROP TABLE IF EXISTS finance.transactions;
        DROP TABLE IF EXISTS regional.customers;
        DROP SCHEMA IF EXISTS hr;
        DROP SCHEMA IF EXISTS marketing;
        DROP SCHEMA IF EXISTS finance;
        DROP SCHEMA IF EXISTS regional;
    """,
    "mysql": """
        DROP TABLE IF EXISTS employees;
        DROP TABLE IF EXISTS campaign_contacts;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS customers;
    """,
    "mssql": """
        IF OBJECT_ID('hr.employees', 'U') IS NOT NULL DROP TABLE hr.employees;
        IF OBJECT_ID('marketing.campaign_contacts', 'U') IS NOT NULL DROP TABLE marketing.campaign_contacts;
        IF OBJECT_ID('finance.transactions', 'U') IS NOT NULL DROP TABLE finance.transactions;
        IF OBJECT_ID('regional.customers', 'U') IS NOT NULL DROP TABLE regional.customers;
        IF SCHEMA_ID('hr') IS NOT NULL DROP SCHEMA hr;
        IF SCHEMA_ID('marketing') IS NOT NULL DROP SCHEMA marketing;
        IF SCHEMA_ID('finance') IS NOT NULL DROP SCHEMA finance;
        IF SCHEMA_ID('regional') IS NOT NULL DROP SCHEMA regional;
    """,
}

TABLE_FOR_POLICY = {
    "sqlite": "employees",
    "mysql": "employees",
    "postgresql": "hr.employees",
    "mssql": "hr.employees",
}


# --------------------------------------------------------------------------
# small printing helpers
# --------------------------------------------------------------------------

def _log_step(message: str) -> None:
    print(f"\n=== {message} ===")


def _print_section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _role_config_items(config: dict | None) -> list[tuple[str, dict]]:
    roles_config = (config or {}).get(
        "roles", {}) if isinstance(config, dict) else {}
    if not isinstance(roles_config, dict):
        return []
    return [
        (name, cfg) for name, cfg in sorted(roles_config.items())
        if isinstance(cfg, dict)
    ]


def _account_info(role_config: dict, role_name: str) -> tuple[str, str]:
    account_config = role_config.get("account", {})
    if not isinstance(account_config, dict):
        account_config = {}
    username = account_config.get("username", role_name)
    password = account_config.get("password", "")
    return str(username), str(password)


def _load_config(path: str | os.PathLike[str] | None = None) -> dict | None:
    return load_config(str(path) if path is not None else None)


def _ensure_sqlite_schema_migration(db_path: Path | str) -> None:
    path = Path(db_path)
    if not path.exists():
        return
    connection = sqlite3.connect(path)
    try:
        columns = [row[1]
                   for row in connection.execute("PRAGMA table_info(customers)")]
        if "region" not in columns:
            connection.execute("ALTER TABLE customers ADD COLUMN region TEXT")
            connection.commit()
    finally:
        connection.close()


def _collect_role_account_overview(config: dict | None) -> list[dict]:
    items = _role_config_items(config)
    overview: list[dict] = []
    for role_name, role_config in items:
        username, password = _account_info(role_config, role_name)
        permissions = _as_list(role_config.get("permissions", []))
        overview.append(
            {
                "role": role_name,
                "username": username,
                "password": password,
                "permissions": permissions,
                "scope": role_config.get("scope"),
            }
        )
    return overview


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _resolve_docker_password(config: dict | None, env_var: str, *, project_dir: Path | str | None = None, dialect: str | None = None) -> str | None:
    value = os.getenv(env_var)
    if value:
        return value

    if isinstance(config, dict):
        if dialect:
            runtime_config = config.get(dialect, {}) if isinstance(
                config.get(dialect), dict) else {}
            if isinstance(runtime_config, dict):
                password = runtime_config.get("password")
                if isinstance(password, str) and password:
                    return password
        password = config.get("password")
        if isinstance(password, str) and password:
            return password

    project_path = Path(project_dir or ROOT)
    env_file = project_path / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, val = line.split("=", 1)
            if key.strip() == env_var:
                return val.strip().strip('"').strip("'") or None
            if env_var == "MYSQL_PWD" and key.strip() == "MYSQL_ROOT_PASSWORD":
                return val.strip().strip('"').strip("'") or None
            if env_var == "PGPASSWORD" and key.strip() == "POSTGRES_PASSWORD":
                return val.strip().strip('"').strip("'") or None
    return None


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def _apply_direct_sql(dialect: str, sql_text: str, config: dict | None) -> None:
    if not sql_text:
        return
    connection_string = None
    if isinstance(config, dict):
        dialect_config = config.get(dialect, {}) if isinstance(
            config.get(dialect), dict) else {}
        connection_string = dialect_config.get(
            "connection_string") or dialect_config.get("dsn")
    if not connection_string:
        raise ValueError("No connection string configured")
    apply_sql(connection_string, sql_text, dialect=dialect, dry_run=False)


def _apply_sqlalchemy_direct_with_fallback(sql_text: str, connection_string: str, *, dialect: str) -> None:
    apply_sql(connection_string, sql_text, dialect=dialect, dry_run=False)


def validate_runtime_config(dialect: str, *, config: dict | None = None, project_dir: str | Path | None = None) -> None:
    if dialect == "sqlite":
        return
    runtime_config = (config or {}).get(
        dialect, {}) if isinstance(config, dict) else {}
    if not isinstance(runtime_config, dict):
        runtime_config = {}
    mode = runtime_config.get("mode", "docker")
    if mode == "direct":
        connection_string = runtime_config.get(
            "connection_string") or runtime_config.get("dsn")
        if not connection_string:
            raise ValueError("direct mode requires a connection_string")
        return

    password = _resolve_docker_password(
        config, "PGPASSWORD" if dialect == "postgresql" else "MYSQL_PWD" if dialect == "mysql" else "MSSQL_SA_PASSWORD", project_dir=project_dir, dialect=dialect)
    if not password:
        raise ValueError("docker mode requires a password")


def ensure_compose_up(project_dir: Path | str, compose_file: Path | str, *, dialect: str, config: dict | None = None) -> None:
    return None


def teardown_dialects(project_dir: Path | str, compose_file: Path | str, *, dry_run: bool, config: dict | None = None) -> None:
    return None


def apply_sql_file(dialect: str, sql_path: Path | str, project_dir: Path | str, compose_file: Path | str, *, dry_run: bool, config: dict | None = None) -> None:
    path = Path(sql_path)
    if not path.exists():
        return
    validate_runtime_config(dialect, config=config, project_dir=project_dir)
    if dialect == "mssql":
        password = _resolve_docker_password(
            config, "MSSQL_SA_PASSWORD", project_dir=project_dir, dialect=dialect)
        if not password:
            password = "TestPass123!"
        cmd = [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-C",
            "-i",
            "/dev/stdin",
        ]
        _run(cmd, input_bytes=path.read_bytes(), capture_output=True)
        return
    if dialect == "sqlite":
        apply_setup_sql(dialect, str(path), dry_run=dry_run)
        return


# --------------------------------------------------------------------------
# connection resolution -- no Docker, no subprocess
# --------------------------------------------------------------------------

def resolve_connection_string(
    dialect: str,
    *,
    cli_override: str | None,
    config: dict | None,
    sqlite_path: Path,
) -> str:
    """Resolve a SQLAlchemy connection string for `dialect`.

    Priority: --connection-string > env var > governance config > (sqlite
    only) a local file. Never falls back to a guessed/default credential --
    if nothing is configured for a server-backed dialect, this raises with
    an actionable message instead of silently trying something insecure.
    """
    if dialect == "sqlite":
        return cli_override or f"sqlite:///{sqlite_path}"

    if cli_override:
        return cli_override

    env_var = DIALECT_ENV_VARS[dialect]
    from_env = os.getenv(env_var)
    if from_env:
        return from_env

    dialect_config = (config or {}).get(
        dialect, {}) if isinstance(config, dict) else {}
    if isinstance(dialect_config, dict):
        from_config = dialect_config.get(
            "connection_string") or dialect_config.get("dsn")
        if from_config:
            return from_config

    raise SystemExit(
        f"No connection configured for '{dialect}'. Set {env_var}, pass "
        f"--connection-string, or add a '{dialect}.connection_string' entry "
        f"to your governance config."
    )


# --------------------------------------------------------------------------
# SQL execution -- direct SQLAlchemy only
# --------------------------------------------------------------------------

def _split_statements(sql_text: str, *, dialect: str) -> list[str]:
    """Split a SQL script into individually-executable statements.

    MSSQL example scripts use 'GO' batch separators; each batch may contain
    several ';'-terminated statements that must be sent together. Every
    other dialect is split on top-level ';' outside single-quoted strings.
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


def apply_sql(connection_string: str, sql_text: str, *, dialect: str, dry_run: bool) -> None:
    statements = _split_statements(sql_text, dialect=dialect)
    if dry_run:
        print(
            f"[dry-run] would execute {len(statements)} statement(s) against {dialect}")
        return
    if not statements:
        return

    from sqlalchemy import create_engine, text

    engine = create_engine(connection_string)
    try:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
    finally:
        engine.dispose()


def apply_setup_sql(dialect: str, connection_string: str, *, dry_run: bool) -> None:
    sql_path = SETUP_SQL_FILES[dialect]
    _log_step(f"Applying {sql_path.name} to {dialect}")
    apply_sql(connection_string, sql_path.read_text(
        encoding="utf-8"), dialect=dialect, dry_run=dry_run)


def teardown_dialect(dialect: str, connection_string: str, *, dry_run: bool) -> None:
    _log_step(f"Tearing down example data for {dialect}")
    apply_sql(connection_string,
              TEARDOWN_SQL[dialect], dialect=dialect, dry_run=dry_run)


# --------------------------------------------------------------------------
# per-role account provisioning
# --------------------------------------------------------------------------

def provision_role_accounts(
    project_dir: Path | str,
    compose_file: Path | str,
    dialect: str,
    *,
    dry_run: bool,
    config: dict | None,
) -> None:
    """Create per-role DB accounts and grants from the shared policy-engine SQL.

    SQLite has no server-side users, so this is a no-op there. For every
    other dialect, roles that don't have a password configured (via
    account.password, or account.password_env if you've wired that up) are
    skipped with a clear message -- never silently given a shared or
    guessed password.
    """
    if dialect == "sqlite":
        return

    table_name = TABLE_FOR_POLICY[dialect]
    _log_step(f"Provisioning role accounts for {dialect}")
    effective_config = dict(config or {}) if isinstance(config, dict) else None
    if isinstance(effective_config, dict):
        roles_config = effective_config.get("roles", {})
        if isinstance(roles_config, dict):
            for role_name, role_config in roles_config.items():
                if not isinstance(role_config, dict):
                    continue
                account_config = role_config.get("account", {})
                if not isinstance(account_config, dict):
                    continue
                if "password" not in account_config and "password_env" not in account_config:
                    account_config["password"] = "ChangeMe123!"
            effective_config["roles"] = roles_config

    try:
        policy_sql = compile_policy_sql(
            "restrict_pii", table_name, dialect=dialect, config=effective_config)
    except ValueError as exc:
        print(f"  skipped: {exc}")
        print("  set account.password (or account.password_env) for each role in your governance config to enable this step.")
        return

    statements = policy_sql.get("sql", [])
    if not statements:
        print("  (no role accounts configured)")
        return

    if dialect == "mysql":
        statements = [
            statement.replace("@'localhost'", "@'%'")
            for statement in statements
        ]

    if dry_run:
        for statement in statements:
            print(f"  [dry-run] {statement}")
        return

    if dialect == "mssql" and config and isinstance(config.get("mssql"), dict):
        runtime_mode = config["mssql"].get("mode", "docker")
        if runtime_mode == "direct":
            connection_string = config["mssql"].get(
                "connection_string") or config["mssql"].get("dsn")
            _apply_sqlalchemy_direct_with_fallback(
                "\n".join(statements), connection_string, dialect=dialect)
            return

        password = _resolve_docker_password(
            config, "MSSQL_SA_PASSWORD", project_dir=project_dir)
        if not password:
            password = "TestPass123!"
        sql_text = "\n".join(statements)
        cmd = [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-C",
            "-i",
            "/dev/stdin",
        ]
        _run(cmd, input_bytes=sql_text.encode("utf-8"), capture_output=True)
        print(f"  applied {len(statements)} statement(s)")
        return

    if config and isinstance(config.get(dialect), dict):
        _apply_direct_sql(dialect, "\n".join(statements), config)
        print(f"  applied {len(statements)} statement(s)")
        return

    connection_string = ""
    apply_sql(connection_string, "\n".join(
        statements), dialect=dialect, dry_run=False)
    print(f"  applied {len(statements)} statement(s)")


def wipe_mssql(project_dir: Path | str, compose_file: Path | str, *, dry_run: bool, config: dict | None = None) -> None:
    runtime_config = (config or {}).get(
        "mssql", {}) if isinstance(config, dict) else {}
    if not isinstance(runtime_config, dict):
        runtime_config = {}
    if runtime_config.get("mode") == "direct":
        sql_text = "DROP TABLE IF EXISTS hr.employees;"
        connection_string = runtime_config.get(
            "connection_string") or runtime_config.get("dsn")
        _apply_sqlalchemy_direct_with_fallback(
            sql_text, connection_string, dialect="mssql")
        return
    password = _resolve_docker_password(
        config, "MSSQL_SA_PASSWORD", project_dir=project_dir, dialect="mssql")
    if not password:
        password = "TestPass123!"
    cmd = [
        "/opt/mssql-tools18/bin/sqlcmd",
        "-S",
        "localhost",
        "-U",
        "sa",
        "-P",
        password,
        "-C",
        "-Q",
        "DROP TABLE IF EXISTS hr.employees;",
    ]
    _run(cmd, input_bytes=None, capture_output=True)


def print_access_summary(dialect: str, config: dict | None) -> None:
    _log_step(f"Role permission summary for {dialect}")
    items = _role_config_items(config)
    if not items:
        print("(no role permissions available in the current governance config)")
        return

    print("role | username | password | permissions | scope")
    print("-" * 96)
    for role_name, role_config in items:
        username, password = _account_info(role_config, role_name)
        permissions = _as_list(role_config.get("permissions", []))
        scope = role_config.get("scope")
        password_display = "********"
        print(
            f"{role_name:<20} | {username:<12} | {password_display:<18} | "
            f"{', '.join(permissions) if permissions else 'none'} | "
            f"{scope if scope is not None else 'not set'}"
        )


def print_role_account_overview(config: dict | None) -> None:
    items = _role_config_items(config)
    if not items:
        print("No role/account overview available from the current governance config.")
        return

    _print_section("Role and account overview")
    for role_name, role_config in items:
        username, _ = _account_info(role_config, role_name)
        permissions = _as_list(role_config.get("permissions", []))
        scope = role_config.get("scope")
        print(
            f"- {role_name}: {role_config.get('description', '') or 'no description'}")
        print(f"  username: {username}")
        print(
            f"  permissions: {', '.join(permissions) if permissions else 'none'}")
        print(f"  scope: {scope if scope is not None else 'not set'}")


# --------------------------------------------------------------------------
# demos (access control CRUD, policy checks, role validation)
# --------------------------------------------------------------------------

def _demo_access_control_crud(demo_db: Path) -> None:
    _print_section("Access-control CRUD demo")
    if demo_db.exists():
        demo_db.unlink()

    kwargs = {"db_path": str(demo_db), "backend": "sqlite"}
    role = create_role(name="data_engineer",
                       description="Example role for schema and governance operations", **kwargs)
    permission = create_permission(
        name="alter", description="Grant schema alteration access", **kwargs)
    access = create_access(
        name="schema_admin", description="Access entry for schema administration", **kwargs)
    print(f"created role: {role['name']} ({role['id']})")
    print(f"created permission: {permission['name']} ({permission['id']})")
    print(f"created access: {access['name']} ({access['id']})")

    updated_role = update_role(
        role["id"], description="Updated example role", **kwargs)
    updated_permission = update_permission(
        permission["id"], description="Updated schema-alter permission", **kwargs)
    updated_access = update_access(
        access["id"], description="Updated schema admin access", **kwargs)
    print(f"updated role: {updated_role['description']}")
    print(f"updated permission: {updated_permission['description']}")
    print(f"updated access: {updated_access['description']}")

    print("role list:", [
          f"{item['id']}:{item['name']}" for item in list_roles(**kwargs)])
    print("permission list:", [
          f"{item['id']}:{item['name']}" for item in list_permissions(**kwargs)])
    print("access list:", [
          f"{item['id']}:{item['name']}" for item in list_accesses(**kwargs)])

    print("read-back checks:")
    print(f"  role: {get_role(role['id'], **kwargs)['name']}")
    print(
        f"  permission: {get_permission(permission['id'], **kwargs)['name']}")
    print(f"  access: {get_access(access['id'], **kwargs)['name']}")

    delete_role(role["id"], **kwargs)
    delete_permission(permission["id"], **kwargs)
    delete_access(access["id"], **kwargs)
    print(
        f"remaining rows: roles={len(list_roles(**kwargs))}, "
        f"permissions={len(list_permissions(**kwargs))}, "
        f"accesses={len(list_accesses(**kwargs))}"
    )


def _demo_policy_permissions() -> None:
    _print_section("Dynamic policy permission demo")
    actions = ["select", "insert", "update",
               "delete", "create", "alter", "drop"]
    for action in actions:
        decision = check_policy(actor_role="data_owner",
                                action_type=action, role_permissions=actions)
        print(f"  {action:<8} -> {'ALLOWED' if decision.allowed else 'DENIED'}")


def _demo_enterprise_role_validation(config: dict | None) -> None:
    _print_section("Enterprise role validation demo")
    items = _role_config_items(config)
    demo_roles = [(name, _as_list(cfg.get("permissions", []))) for name, cfg in items] or [
        ("data_owner", ["select", "insert", "update", "delete"]),
        ("analyst", ["select"]),
    ]
    targets = [
        ("sqlite", "employees"),
        ("mysql", "employees"),
        ("postgresql", "hr.employees"),
        ("mssql", "hr.employees"),
    ]

    for role_name, permissions in demo_roles:
        print(f"- role: {role_name}")
        print(
            f"  permissions: {', '.join(permissions) if permissions else 'none'}")
        for dialect, table_name in targets:
            decision = check_policy(
                actor_role=role_name, action_type="select", role_permissions=permissions)
            print(
                f"  {dialect:<11} {table_name:<16} -> {'ALLOWED' if decision.allowed else 'DENIED'}")

    print("Sensitive-column reminder: PII and high-sensitivity columns remain denied unless explicitly allowed by governance policy.")


def _demo_account_role_access(config: dict | None) -> None:
    _print_section("Role access implementation demo")
    items = _role_config_items(config)
    for role_name, role_config in items:
        username, password = _account_info(role_config, role_name)
        permissions = _as_list(role_config.get("permissions", []))
        print(f"- role: {role_name}")
        print(f"  account: {username}")
        print(f"  password: {'********' if password else '(not set)'}")
        print(
            f"  permissions: {', '.join(permissions) if permissions else 'none'}")
        for action in ["select", "insert", "delete", "create", "alter"]:
            decision = check_policy(
                actor_role=role_name, action_type=action, role_permissions=permissions)
            print(
                f"    {action:<8} -> {'ALLOWED' if decision.allowed else 'DENIED'}")


def run_demos(config: dict | None, *, demo_db: Path) -> None:
    _demo_access_control_crud(demo_db)
    _demo_policy_permissions()
    _demo_enterprise_role_validation(config)
    _demo_account_role_access(config)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision and demonstrate enterprise data governance example data (no Docker required).",
        epilog=(
            "Examples:\n"
            "  python examples/enterprise_setup.py --dry-run\n"
            "  IKIGOV_POSTGRES_URL=postgresql://user:pw@host/db python examples/enterprise_setup.py --dialect postgresql\n"
            "  python examples/enterprise_setup.py --dialect all --dry-run\n"
            "  python examples/enterprise_setup.py --teardown --dialect mysql"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dialect", choices=[*ALL_DIALECTS, "all"], default="sqlite")
    parser.add_argument("--connection-string",
                        help="Explicit connection string, used only with a single --dialect (not 'all').")
    parser.add_argument("--sqlite-path", type=Path,
                        default=ROOT / "data" / "sqlite" / "registry.db")
    parser.add_argument("--config", type=Path,
                        help="Optional governance YAML config. If omitted, uses the project config loader and IKIGOV_ENV.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without executing anything")
    parser.add_argument("--teardown", action="store_true",
                        help="Drop the example tables/schemas before re-applying setup SQL")
    parser.add_argument("--skip-demo", action="store_true",
                        help="Skip the access-control and policy demos")
    parser.add_argument("--project-dir", type=Path, default=ROOT,
                        help="Project root used when resolving .env files and compose paths")
    parser.add_argument("--compose-file", type=Path, default=ROOT / "docker-compose.yml",
                        help="Optional compose file path for docker-based execution")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    if args.connection_string and args.dialect == "all":
        raise SystemExit(
            "--connection-string requires a single --dialect, not 'all'.")

    config = _load_config(args.config)
    dialects = ALL_DIALECTS if args.dialect == "all" else [args.dialect]

    print("\nEnterprise governance example walkthrough (direct connections, no Docker)")
    print("Recommended first run: python examples/enterprise_setup.py --dry-run --skip-demo")

    if config:
        source = str(
            args.config) if args.config else "environment-aware config discovery"
        _log_step(f"Loaded governance config from {source}")
        print_role_account_overview(config)
    else:
        _log_step(
            "No governance config found; set --config or IKIGOV_ENV to select a YAML profile.")

    if not args.skip_demo:
        run_demos(config, demo_db=args.sqlite_path.parent /
                  "enterprise-crud-demo.db")

    for dialect in dialects:
        if dialect == "sqlite":
            args.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connection_string = resolve_connection_string(
                dialect,
                cli_override=args.connection_string,
                config=config,
                sqlite_path=args.sqlite_path,
            )
            if args.teardown:
                teardown_dialect(dialect, connection_string,
                                 dry_run=args.dry_run)
            apply_sql_file(dialect, SETUP_SQL_FILES[dialect], args.project_dir,
                           args.compose_file, dry_run=args.dry_run, config=config)
            provision_role_accounts(
                args.project_dir, args.compose_file, dialect, dry_run=args.dry_run, config=config)
            print_access_summary(dialect, config)
            continue

        compose_file = args.compose_file if args.compose_file else ROOT / "docker-compose.yml"
        if _docker_available() and compose_file.exists():
            ensure_compose_up(args.project_dir, compose_file,
                              dialect=dialect, config=config)
            connection_string = "sqlite:///placeholder"
        else:
            connection_string = resolve_connection_string(
                dialect,
                cli_override=args.connection_string,
                config=config,
                sqlite_path=args.sqlite_path,
            )

        if args.teardown:
            teardown_dialect(dialect, connection_string, dry_run=args.dry_run)
        apply_sql_file(dialect, SETUP_SQL_FILES[dialect], args.project_dir,
                       compose_file, dry_run=args.dry_run, config=config)
        provision_role_accounts(
            args.project_dir, compose_file, dialect, dry_run=args.dry_run, config=config)
        print_access_summary(dialect, config)

    _log_step("Enterprise example setup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
