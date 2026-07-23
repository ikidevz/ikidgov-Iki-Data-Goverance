#!/usr/bin/env python3
"""Enterprise data-governance example — connects directly to your databases.

No Docker required. This script provisions the example schema/tables, creates
one scoped database account per governance role (via the shared policy-engine
SQL compiler), and walks through the access-control and policy-check demos.

Everything here is a single code path: resolve a SQLAlchemy connection string,
then run SQL through it. There is no Docker Compose integration, no
docker-managed credential lookup, and no `sqlcmd` subprocess — bring your own
running database server (or use the zero-setup SQLite default) and this
script just opens a connection to it.

Connection resolution, per dialect (first match wins):
  1. --connection-string (explicit override, applies to the single --dialect given)
  2. an environment variable: IKIGOV_POSTGRES_URL / IKIGOV_MYSQL_URL / IKIGOV_MSSQL_URL
  3. <dialect>.connection_string (or .dsn) in your governance config, or
     <dialect>.connection_string_env / .dsn_env resolved against the environment
  4. the same two config keys above, resolved against a .env file
     (default ./.env, override with --env-file)
  5. sqlite only: a local file, default ./data/sqlite/registry.db

This makes every dialect's connection string flexible by design: export it,
put it in governance.yaml, put it in .env, or pass it on the command line --
whichever fits your workflow. Local `localhost` URLs are automatically
rewritten to 127.0.0.1 (some environments resolve `localhost` oddly).

Examples:
  python examples/enterprise_setup.py
      # sqlite, zero setup, creates ./data/sqlite/registry.db

  IKIGOV_POSTGRES_URL=postgresql://user:pw@host:5432/db \\
      python examples/enterprise_setup.py --dialect postgresql

  python examples/enterprise_setup.py --dialect all --dry-run

  python examples/enterprise_setup.py --dialect mysql --teardown

  python examples/enterprise_setup.py --dialect postgresql --env-file .env.staging
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
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


class MissingConnectionError(SystemExit):
    """Raised when a dialect has no resolvable connection string."""


# --------------------------------------------------------------------------
# small printing / config helpers
# --------------------------------------------------------------------------

def _log_step(message: str, *, explain: str | None = None) -> None:
    print(f"\n=== {message} ===")
    if explain:
        print(f"    -> {explain}")


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


def _load_env_file(env_file: Path | None = None) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from a .env file. Missing file -> {}."""
    path = env_file or (ROOT / ".env")
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


def _mask_connection_string(connection_string: str) -> str:
    """Redact user:password@ credentials before printing a connection string."""
    return re.sub(r"//([^/@]+)@", "//***:***@", connection_string)


def _ensure_sqlite_schema_migration(db_path: Path | str) -> None:
    """Add the `region` column to an older `customers` table, if missing.

    Safe to call against a database that doesn't exist yet, or one already
    on the current schema.
    """
    path = Path(db_path)
    if not path.exists():
        return
    connection = sqlite3.connect(path)
    try:
        columns = [row[1]
                   for row in connection.execute("PRAGMA table_info(customers)")]
        if columns and "region" not in columns:
            connection.execute("ALTER TABLE customers ADD COLUMN region TEXT")
            connection.commit()
    finally:
        connection.close()


def _collect_role_account_overview(config: dict | None) -> list[dict]:
    overview: list[dict] = []
    for role_name, role_config in _role_config_items(config):
        username, password = _account_info(role_config, role_name)
        overview.append(
            {
                "role": role_name,
                "username": username,
                "password": password,
                "permissions": _as_list(role_config.get("permissions", [])),
                "scope": role_config.get("scope"),
            }
        )
    return overview


# --------------------------------------------------------------------------
# connection resolution -- connection strings only, no Docker involved
# --------------------------------------------------------------------------

def _normalize_local_url(connection_string: str) -> str:
    """Rewrite `localhost` to 127.0.0.1 in local connection strings.

    Some environments (notably inside certain containers/WSL setups) resolve
    `localhost` inconsistently for TCP connections; 127.0.0.1 is unambiguous.
    """
    return (
        connection_string
        .replace("//localhost:", "//127.0.0.1:")
        .replace("//localhost/", "//127.0.0.1/")
    )


def resolve_connection_string(
    dialect: str,
    *,
    cli_override: str | None,
    config: dict | None,
    sqlite_path: Path,
    env_file: Path | None = None,
) -> str:
    """Resolve a SQLAlchemy connection string for `dialect`.

    Priority: --connection-string > env var > governance config
    (connection_string/dsn, or connection_string_env/dsn_env resolved against
    the environment) > the same config keys resolved against a .env file >
    (sqlite only) a local file. Never falls back to a guessed/default
    credential -- if nothing is configured for a server-backed dialect, this
    raises with an actionable message instead of silently trying something
    insecure.
    """
    if dialect == "sqlite":
        return cli_override or f"sqlite:///{sqlite_path}"

    if cli_override:
        return _normalize_local_url(cli_override)

    env_var = DIALECT_ENV_VARS[dialect]
    from_env = os.getenv(env_var)
    if from_env:
        return _normalize_local_url(from_env)

    dialect_config = (config or {}).get(
        dialect, {}) if isinstance(config, dict) else {}
    if isinstance(dialect_config, dict):
        from_config = dialect_config.get(
            "connection_string") or dialect_config.get("dsn")
        if from_config:
            return _normalize_local_url(str(from_config))
        for env_key in ("connection_string_env", "dsn_env"):
            env_name = dialect_config.get(env_key)
            if isinstance(env_name, str) and env_name:
                from_config_env = os.getenv(env_name)
                if from_config_env:
                    return _normalize_local_url(from_config_env)

    # Last resort before giving up: a .env file (never committed, see .gitignore).
    dotenv_values = _load_env_file(env_file)
    from_dotenv = dotenv_values.get(env_var)
    if from_dotenv:
        return _normalize_local_url(from_dotenv)
    if isinstance(dialect_config, dict):
        for env_key in ("connection_string_env", "dsn_env"):
            env_name = dialect_config.get(env_key)
            if isinstance(env_name, str) and env_name:
                from_dotenv_config = dotenv_values.get(env_name)
                if from_dotenv_config:
                    return _normalize_local_url(from_dotenv_config)

    raise MissingConnectionError(
        f"No connection configured for '{dialect}'. Set {env_var} (directly or in "
        f"{env_file or (ROOT / '.env')}), pass --connection-string, or add a "
        f"'{dialect}.connection_string' entry to your governance config."
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


def apply_sql(connection_string: str, sql_text: str, *, dialect: str, dry_run: bool) -> int:
    """Execute `sql_text` against `connection_string`. Returns statement count."""
    statements = _split_statements(sql_text, dialect=dialect)
    if dry_run:
        print(
            f"[dry-run] would execute {len(statements)} statement(s) against {dialect}")
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


def apply_example_data(dialect: str, connection_string: str, *, dry_run: bool) -> None:
    sql_path = SETUP_SQL_FILES[dialect]
    if not sql_path.exists():
        return
    _log_step(
        f"Applying {sql_path.name} to {dialect}",
        explain="Creates the example tables (employees, customers, etc.) and seeds a "
        "few rows tagged with sensitivity_level, so later steps have real data to govern.",
    )
    if dialect == "sqlite" and not dry_run:
        db_path = connection_string.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _ensure_sqlite_schema_migration(db_path)
    apply_sql(connection_string, sql_path.read_text(
        encoding="utf-8"), dialect=dialect, dry_run=dry_run)


def teardown_dialect(dialect: str, connection_string: str, *, dry_run: bool) -> None:
    _log_step(
        f"Tearing down example data for {dialect}",
        explain="Drops the example tables/schemas so the next apply starts from a clean slate.",
    )
    apply_sql(connection_string,
              TEARDOWN_SQL[dialect], dialect=dialect, dry_run=dry_run)


# --------------------------------------------------------------------------
# per-role account provisioning
# --------------------------------------------------------------------------

def _roles_with_configured_passwords(config: dict | None) -> dict | None:
    """Return `config` with any role missing a password/password_env dropped.

    SQLite has no server-side users so this only matters for the other three
    dialects. Roles without a password are skipped (with a clear message)
    rather than silently given a shared or guessed one.
    """
    if not isinstance(config, dict):
        return config
    roles_config = config.get("roles", {})
    if not isinstance(roles_config, dict):
        return config

    filtered_roles = {}
    for role_name, role_config in roles_config.items():
        if not isinstance(role_config, dict):
            continue
        account_config = role_config.get("account", {})
        if not isinstance(account_config, dict):
            continue
        if "password" not in account_config and "password_env" not in account_config:
            print(f"  skipped: role '{role_name}' has no configured password")
            continue
        filtered_roles[role_name] = role_config

    effective_config = dict(config)
    effective_config["roles"] = filtered_roles
    return effective_config


def provision_role_accounts(
    dialect: str,
    connection_string: str,
    *,
    dry_run: bool,
    config: dict | None,
) -> None:
    """Create per-role DB accounts and grants from the shared policy-engine SQL."""
    if dialect == "sqlite":
        return

    table_name = TABLE_FOR_POLICY[dialect]
    _log_step(
        f"Provisioning role accounts for {dialect}",
        explain="Compiles each role's permissions (from governance.yaml) into real "
        "CREATE USER / CREATE ROLE / GRANT statements, then applies them. This is the "
        "'least privilege' step: each role only gets the actions it's configured for.",
    )
    effective_config = _roles_with_configured_passwords(config)

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
        statements = [statement.replace("@'localhost'", "@'%'")
                      for statement in statements]

    count = apply_sql(connection_string, "\n".join(
        statements), dialect=dialect, dry_run=dry_run)
    if not dry_run:
        print(f"  applied {count} statement(s)")


def print_access_summary(dialect: str, config: dict | None) -> None:
    _log_step(
        f"Role permission summary for {dialect}",
        explain="A recap of who can do what, so you can eyeball the effective access model at a glance.",
    )
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
    overview = _collect_role_account_overview(config)
    if not overview:
        print("No role/account overview available from the current governance config.")
        return

    _print_section("Role and account overview")
    items = dict(_role_config_items(config))
    for entry in overview:
        role_config = items.get(entry["role"], {})
        print(
            f"- {entry['role']}: {role_config.get('description', '') or 'no description'}")
        print(f"  username: {entry['username']}")
        print(
            f"  permissions: {', '.join(entry['permissions']) if entry['permissions'] else 'none'}")
        print(
            f"  scope: {entry['scope'] if entry['scope'] is not None else 'not set'}")


# --------------------------------------------------------------------------
# demos (access control CRUD, policy checks, role validation)
# --------------------------------------------------------------------------

def _demo_access_control_crud(demo_db: Path) -> None:
    _print_section("Access-control CRUD demo")
    print("Roles, permissions, and access entries are just governed records themselves --")
    print("this walks through creating, reading, updating, and deleting them via the same")
    print("access_control module the CLI and other integrations use.")
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
    print("The policy engine is fail-closed: an action is only ALLOWED if the role's")
    print("permission list explicitly includes it. Nothing is granted by default.")
    actions = ["select", "insert", "update",
               "delete", "create", "alter", "drop"]
    for action in actions:
        decision = check_policy(actor_role="data_owner",
                                action_type=action, role_permissions=actions)
        print(f"  {action:<8} -> {'ALLOWED' if decision.allowed else 'DENIED'}")


def _demo_enterprise_role_validation(config: dict | None) -> None:
    _print_section("Enterprise role validation demo")
    print("Same role, same action, checked against every dialect's target table --")
    print("showing that the decision is driven by governance config, not by database engine.")
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
    print("Ties it together: each configured role's actual DB account, next to what")
    print("actions the policy engine says that role is allowed to perform.")
    for role_name, role_config in _role_config_items(config):
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
            "  python examples/enterprise_setup.py --teardown --dialect mysql\n"
            "  python examples/enterprise_setup.py --dialect postgresql --env-file .env.staging"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dialect", choices=[*ALL_DIALECTS, "all"], default="sqlite")
    parser.add_argument(
        "--connection-string",
        help="Explicit connection string, used only with a single --dialect (not 'all').",
    )
    parser.add_argument("--sqlite-path", type=Path,
                        default=ROOT / "data" / "sqlite" / "registry.db")
    parser.add_argument(
        "--config", type=Path,
        help="Optional governance YAML config. If omitted, uses the project config loader and IKIGOV_ENV.",
    )
    parser.add_argument(
        "--env-file", type=Path, default=None,
        help="Path to a .env file used as a final fallback for connection strings (default: ./.env).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without executing anything")
    parser.add_argument("--teardown", action="store_true",
                        help="Drop the example tables/schemas before re-applying setup SQL")
    parser.add_argument("--skip-demo", action="store_true",
                        help="Skip the access-control and policy demos")
    return parser.parse_args(list(argv) if argv is not None else None)


def _run_dialect(dialect: str, args: argparse.Namespace, config: dict | None) -> None:
    if dialect == "sqlite":
        args.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    connection_string = resolve_connection_string(
        dialect,
        cli_override=args.connection_string,
        config=config,
        sqlite_path=args.sqlite_path,
        env_file=args.env_file,
    )
    _log_step(
        f"Resolved connection for {dialect}",
        explain=f"Using {_mask_connection_string(connection_string)} "
        f"(checked --connection-string, then env var, then governance config, then .env file, in that order).",
    )

    if args.teardown:
        teardown_dialect(dialect, connection_string, dry_run=args.dry_run)
    apply_example_data(dialect, connection_string, dry_run=args.dry_run)
    provision_role_accounts(dialect, connection_string,
                            dry_run=args.dry_run, config=config)
    print_access_summary(dialect, config)


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
        _run_dialect(dialect, args, config)

    _print_section("What just happened")
    print("1. Example tables were created and seeded with sensitivity-tagged data.")
    print(
        "2. Each governance role got a real, scoped database account (where a password")
    print("   was configured) via SQL compiled straight from governance.yaml.")
    print("3. The policy engine's ALLOWED/DENIED checks show that access is driven purely")
    print("   by config, not hardcoded per database or table.")
    print("Next: edit config/governance.yaml (roles/permissions) and re-run to see the")
    print("provisioning SQL and policy decisions change accordingly.")

    _log_step("Enterprise example setup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
