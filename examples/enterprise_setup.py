#!/usr/bin/env python3
"""Provision the enterprise governance example databases.

The script is idempotent: re-running it will reuse existing tables and only
insert rows that are not already present. By default it uses the Docker
Compose stack in this repository, but it can also read an optional config
file to target a direct database connection.
"""
from __future__ import annotations
from ikidgov.modules.policy_engine.interface import check as check_policy
from ikidgov.modules.access_control.interface import (
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
from ikidgov.core import example_runtime as runtime

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


EXAMPLES_DIR = ROOT / "examples"


def _log_step(message: str) -> None:
    print(f"\n=== {message} ===")


def _run(*args, **kwargs):
    return runtime._run(*args, **kwargs)


def _load_config(path: Path | None) -> dict | None:
    return runtime._load_config(path)


def _get_dialect_config(config: dict | None, dialect: str) -> dict:
    return runtime._get_dialect_config(config, dialect)


def validate_runtime_config(dialect: str, *, config: dict | None = None, project_dir: Path | None = None) -> None:
    return runtime.validate_runtime_config(dialect, config=config, project_dir=project_dir)


def _resolve_docker_password(dialect_config: dict, env_name: str, *, project_dir: Path | None = None) -> str:
    return runtime._resolve_docker_password(dialect_config, env_name, project_dir=project_dir)


def _docker_available() -> bool:
    return runtime._docker_available()


def ensure_compose_up(project_dir: Path, compose_file: Path, dry_run: bool) -> None:
    return runtime.ensure_compose_up(project_dir, compose_file, dry_run)


def _default_dialect_mode(config: dict | None, dialect: str) -> str:
    return runtime._default_dialect_mode(config, dialect)


def _ensure_sqlite_schema_migration(db_path: Path) -> None:
    return runtime._ensure_sqlite_schema_migration(db_path)


def _apply_sqlite_direct(sql_text: str, config: dict) -> None:
    return runtime._apply_sqlite_direct(sql_text, config)


def _build_sqlite_docker_migration_code(db_path: str = "/data/sqlite/registry.db") -> str:
    return runtime._build_sqlite_docker_migration_code(db_path)


def _split_sql_statements(sql_text: str) -> list[str]:
    return runtime._split_sql_statements(sql_text)


def _apply_sqlalchemy_direct(sql_text: str, connection_string: str) -> None:
    return runtime._apply_sqlalchemy_direct(sql_text, connection_string)


def _apply_sqlalchemy_direct_with_fallback(sql_text: str, connection_string: str, *, dialect: str) -> None:
    return runtime._apply_sqlalchemy_direct_with_fallback(sql_text, connection_string, dialect=dialect)


def _apply_direct_sql(dialect: str, sql_text: str, config: dict) -> None:
    return runtime._apply_direct_sql(dialect, sql_text, config)


def apply_sql_file(
    dialect: str,
    sql_path: Path,
    project_dir: Path,
    compose_file: Path,
    dry_run: bool,
    config: dict | None = None,
) -> None:
    return runtime.apply_sql_file(dialect, sql_path, project_dir, compose_file, dry_run, config=config)


def resolve_sql_path(dialect: str) -> Path:
    return runtime.resolve_sql_path(dialect)


def wipe_sqlite(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    return runtime.wipe_sqlite(project_dir, compose_file, dry_run, config=config)


def wipe_postgres(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    return runtime.wipe_postgres(project_dir, compose_file, dry_run, config=config)


def wipe_mysql(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    return runtime.wipe_mysql(project_dir, compose_file, dry_run, config=config)


def wipe_mssql(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    return runtime.wipe_mssql(project_dir, compose_file, dry_run, config=config)


def _should_start_compose(config: dict | None, dialect: str) -> bool:
    return runtime._should_start_compose(config, dialect)


def _should_use_compose_for_dialect(config: dict | None, dialect: str) -> bool:
    return runtime._should_use_compose_for_dialect(config, dialect)


def _print_section(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(title)
    print('=' * 72)


def _collect_role_account_overview(config: dict | None) -> list[dict[str, object]]:
    if not config:
        return []

    roles_config = config.get("roles", {})
    if not isinstance(roles_config, dict):
        return []

    overview: list[dict[str, object]] = []
    for role_name, role_config in sorted(roles_config.items()):
        if not isinstance(role_config, dict):
            continue

        account_config = role_config.get("account", {})
        if not isinstance(account_config, dict):
            account_config = {}

        overview.append({
            "role": role_name,
            "description": role_config.get("description", ""),
            "username": account_config.get("username", role_name),
            "permissions": role_config.get("permissions", []),
            "scope": role_config.get("scope", None),
        })

    return overview


def _print_role_account_overview(config: dict | None) -> None:
    overview = _collect_role_account_overview(config)
    if not overview:
        print("No role/account overview available from the current governance config.")
        return

    _print_section("Role and account overview")
    for item in overview:
        print(f"- {item['role']}: {item['description'] or 'no description'}")
        print(f"  username: {item['username']}")
        print(
            f"  permissions: {', '.join(str(p) for p in item['permissions']) if item['permissions'] else 'none'}")
        print(
            f"  scope: {item['scope'] if item['scope'] is not None else 'not set'}")


def _build_demo_role_config(config: dict | None = None) -> dict | None:
    if not isinstance(config, dict):
        return None

    roles_config = config.get("roles", {})
    if not isinstance(roles_config, dict):
        return config

    demo_roles = {}
    for role_name, role_config in roles_config.items():
        if not isinstance(role_config, dict):
            continue
        account_config = role_config.get("account", {})
        if not isinstance(account_config, dict):
            account_config = {}
        if not account_config.get("password"):
            account_config = dict(account_config)
            account_config["password"] = "ChangeMe123!"
        demo_roles[role_name] = dict(role_config)
        demo_roles[role_name]["account"] = account_config

    updated_config = dict(config)
    updated_config["roles"] = demo_roles
    return updated_config


def provision_role_accounts(project_dir: Path, compose_file: Path, dialect: str, *, dry_run: bool, config: dict | None = None) -> None:
    """Create per-role accounts and grants using the shared policy-engine SQL output."""
    from ikidgov.modules.policy_engine.interface import compile as compile_policy_sql

    dialect_config = _get_dialect_config(config, dialect)
    mode = _default_dialect_mode(config, dialect)
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    table_name = "employees"
    if dialect in {"postgres", "postgresql", "mssql"}:
        table_name = "hr.employees"
    elif dialect == "mysql":
        table_name = "employees"

    effective_config = _build_demo_role_config(config)
    if dialect == "sqlite":
        statements = []
    else:
        policy_sql = compile_policy_sql(
            "restrict_pii", table_name, dialect=dialect, config=effective_config)
        statements = policy_sql.get("sql", [])

    _log_step(f"Provisioning role accounts for {dialect}")
    if dry_run:
        print(
            f"[dry-run] would provision accounts for {len(statements)} SQL statements against {dialect}")
        return

    if mode == "direct":
        if dialect in {"sqlite", "postgres", "postgresql", "mysql"}:
            _apply_direct_sql(dialect, "\n".join(statements), dialect_config)
            return
        if dialect == "mssql":
            if not dialect_config.get("connection_string") and not dialect_config.get("dsn"):
                _run([
                    "docker", "compose", "-f", str(
                        compose_file), "exec", "-T", "-e",
                    f"SQLCMDPASSWORD={_resolve_docker_password(dialect_config, 'SQLCMDPASSWORD', project_dir=project_dir)}",
                    dialect_config.get("service", "mssql"),
                    "/opt/mssql-tools18/bin/sqlcmd",
                    "-S", dialect_config.get("server", "localhost"),
                    "-U", dialect_config.get("user", "sa"),
                    "-C", "-i", "/dev/stdin",
                ], cwd=project_dir, input_bytes="\n".join(statements).encode("utf-8"), env={**os.environ, "SQLCMDPASSWORD": _resolve_docker_password(dialect_config, 'SQLCMDPASSWORD', project_dir=project_dir)})
                return
            _apply_sqlalchemy_direct_with_fallback(
                "\n".join(statements),
                dialect_config.get(
                    "connection_string") or dialect_config.get("dsn"),
                dialect=dialect,
            )
            return
        raise ValueError(f"unsupported dialect for direct mode: {dialect}")

    if dialect in {"postgres", "postgresql"}:
        env = os.environ.copy()
        env["PGPASSWORD"] = _resolve_docker_password(
            dialect_config, "PGPASSWORD", project_dir=project_dir)
        service = dialect_config.get("service", "postgres")
        _run([
            "docker", "compose", "-f", str(
                compose_file), "exec", "-T", "-e", f"PGPASSWORD={env['PGPASSWORD']}", service, "psql", "-U",
            dialect_config.get("user", "ikigov"), "-d", dialect_config.get(
                "database", "ikigov_test"), "-v", "ON_ERROR_STOP=1"
        ], cwd=project_dir, input_bytes="\n".join(statements).encode("utf-8"), env=env)
        return

    if dialect == "mysql":
        env = os.environ.copy()
        env["MYSQL_PWD"] = _resolve_docker_password(
            dialect_config, "MYSQL_PWD", project_dir=project_dir)
        service = dialect_config.get("service", "mysql")
        _run([
            "docker", "compose", "-f", str(
                compose_file), "exec", "-T", "-e", f"MYSQL_PWD={env['MYSQL_PWD']}", service,
            "mysql", "-u", dialect_config.get(
                "user", "root"), dialect_config.get("database", "ikigov_test")
        ], cwd=project_dir, input_bytes="\n".join(statements).encode("utf-8"), env=env)
        return

    if dialect == "mssql":
        env = os.environ.copy()
        env["SQLCMDPASSWORD"] = _resolve_docker_password(
            dialect_config, "SQLCMDPASSWORD", project_dir=project_dir)
        service = dialect_config.get("service", "mssql")
        _run([
            "docker", "compose", "-f", str(compose_file),
            "exec", "-T", "-e", f"SQLCMDPASSWORD={env['SQLCMDPASSWORD']}", service,
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S", dialect_config.get("server", "localhost"),
            "-U", dialect_config.get("user", "sa"),
            "-C", "-i", "/dev/stdin",
        ], cwd=project_dir, input_bytes="\n".join(statements).encode("utf-8"), env=env)


def _demo_access_control_crud() -> None:
    _print_section("Access-control CRUD demo")
    demo_db = Path(tempfile.gettempdir()) / "ikigov-enterprise-crud-demo.db"
    if demo_db.exists():
        demo_db.unlink()

    role = create_role(
        name="data_engineer",
        description="Example role for schema and governance operations",
        db_path=str(demo_db),
        backend="sqlite",
    )
    permission = create_permission(
        name="alter",
        description="Grant schema alteration access",
        db_path=str(demo_db),
        backend="sqlite",
    )
    access = create_access(
        name="schema_admin",
        description="Access entry for schema administration",
        db_path=str(demo_db),
        backend="sqlite",
    )

    print(f"created role: {role['name']} ({role['id']})")
    print(f"created permission: {permission['name']} ({permission['id']})")
    print(f"created access: {access['name']} ({access['id']})")

    updated_role = update_role(
        role["id"],
        description="Updated example role",
        db_path=str(demo_db),
        backend="sqlite",
    )
    updated_permission = update_permission(
        permission["id"],
        description="Updated schema-alter permission",
        db_path=str(demo_db),
        backend="sqlite",
    )
    updated_access = update_access(
        access["id"],
        description="Updated schema admin access",
        db_path=str(demo_db),
        backend="sqlite",
    )

    print(f"updated role: {updated_role['description']}")
    print(f"updated permission: {updated_permission['description']}")
    print(f"updated access: {updated_access['description']}")

    print("role list:")
    for item in list_roles(db_path=str(demo_db), backend="sqlite"):
        print(f"  - {item['id']}: {item['name']}")

    print("permission list:")
    for item in list_permissions(db_path=str(demo_db), backend="sqlite"):
        print(f"  - {item['id']}: {item['name']}")

    print("access list:")
    for item in list_accesses(db_path=str(demo_db), backend="sqlite"):
        print(f"  - {item['id']}: {item['name']}")

    print("read-back checks:")
    print(
        f"  role: {get_role(role['id'], db_path=str(demo_db), backend='sqlite')['name']}")
    print(
        f"  permission: {get_permission(permission['id'], db_path=str(demo_db), backend='sqlite')['name']}")
    print(
        f"  access: {get_access(access['id'], db_path=str(demo_db), backend='sqlite')['name']}")

    delete_role(role["id"], db_path=str(demo_db), backend="sqlite")
    delete_permission(permission["id"], db_path=str(demo_db), backend="sqlite")
    delete_access(access["id"], db_path=str(demo_db), backend="sqlite")

    print(f"remaining rows: roles={len(list_roles(db_path=str(demo_db), backend='sqlite'))}, permissions={len(list_permissions(db_path=str(demo_db), backend='sqlite'))}, accesses={len(list_accesses(db_path=str(demo_db), backend='sqlite'))}")


def _demo_policy_permissions() -> None:
    _print_section("Dynamic policy permission demo")
    runtime_permissions = ["select", "insert",
                           "update", "delete", "create", "alter", "drop"]
    for action in ["select", "insert", "update", "delete", "create", "alter", "drop"]:
        decision = check_policy(
            actor_role="data_owner",
            action_type=action,
            role_permissions=runtime_permissions,
        )
        status = "ALLOWED" if decision.allowed else "DENIED"
        print(f"  {action:<8} -> {status}")


def _demo_enterprise_role_validation(config: dict | None = None) -> None:
    _print_section("Enterprise role validation demo")
    if not isinstance(config, dict):
        config = {}

    roles_config = config.get("roles", {})
    if not isinstance(roles_config, dict):
        roles_config = {}

    demo_roles: list[tuple[str, list[str]]] = []
    for role_name, role_config in sorted(roles_config.items()):
        if not isinstance(role_config, dict):
            continue
        permissions = role_config.get("permissions", [])
        if isinstance(permissions, str):
            permissions = [permissions]
        elif not isinstance(permissions, list):
            permissions = []
        demo_roles.append((role_name, permissions))

    if not demo_roles:
        demo_roles = [
            ("data_owner", ["select", "insert", "update", "delete"]),
            ("analyst", ["select"]),
        ]

    targets = [
        ("sqlite", "employees"),
        ("mysql", "employees"),
        ("postgresql", "hr.employees"),
        ("mssql", "hr.employees"),
    ]

    print("Enterprise role validation example")
    for role_name, permissions in demo_roles:
        print(f"- role: {role_name}")
        print(
            f"  permissions: {', '.join(permissions) if permissions else 'none'}")
        for dialect, table_name in targets:
            decision = check_policy(
                actor_role=role_name,
                action_type="select",
                role_permissions=permissions,
            )
            status = "ALLOWED" if decision.allowed else "DENIED"
            print(f"  {dialect:<11} {table_name:<16} -> {status}")

    print("Sensitive-column reminder: PII and high-sensitivity columns remain denied unless explicitly allowed by governance policy.")


def _demo_account_role_access(config: dict | None = None) -> None:
    _print_section("Role access implementation demo")
    if not isinstance(config, dict):
        config = {}

    roles_config = config.get("roles", {})
    if not isinstance(roles_config, dict):
        roles_config = {}

    print("Account-based role access implementation")
    for role_name, role_config in sorted(roles_config.items()):
        if not isinstance(role_config, dict):
            continue
        account_config = role_config.get("account", {})
        if not isinstance(account_config, dict):
            account_config = {}
        username = account_config.get("username", role_name)
        password = account_config.get("password", "")
        permissions = role_config.get("permissions", [])
        if isinstance(permissions, str):
            permissions = [permissions]
        elif not isinstance(permissions, list):
            permissions = []

        print(f"- role: {role_name}")
        print(f"  account: {username}")
        print(f"  password: {'********' if password else '(not set)'}")
        print(
            f"  permissions: {', '.join(str(item) for item in permissions) if permissions else 'none'}")

        for action in ["select", "insert", "delete", "create", "alter"]:
            decision = check_policy(
                actor_role=role_name,
                action_type=action,
                role_permissions=permissions,
            )
            status = "ALLOWED" if decision.allowed else "DENIED"
            print(f"  {action:<8} -> {status}")


def _ensure_sqlite_schema_migration(db_path: Path) -> None:
    if not db_path.exists():
        return

    migration_plan = {
        "employees": [("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
        "campaign_contacts": [("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
        "transactions": [("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
        "customers": [
            ("region", "TEXT"),
            ("sensitivity_level", "TEXT DEFAULT 'unclassified'"),
        ],
    }

    connection = sqlite3.connect(db_path)
    try:
        for table_name, columns in migration_plan.items():
            try:
                existing_columns = [row[1] for row in connection.execute(
                    f"PRAGMA table_info({table_name})")]
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    continue
                raise

            for column_name, column_definition in columns:
                if column_name not in existing_columns:
                    try:
                        connection.execute(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                        )
                    except sqlite3.OperationalError as exc:
                        if "no such table" in str(exc).lower():
                            continue
                        raise
        connection.commit()
    finally:
        connection.close()


def _apply_sqlite_direct(sql_text: str, config: dict) -> None:
    db_path = config.get("path") or config.get(
        "database_path") or "/data/sqlite/registry.db"
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        _ensure_sqlite_schema_migration(path)
        connection.executescript(sql_text)
        connection.commit()
    finally:
        connection.close()


def _build_sqlite_docker_migration_code(db_path: str = "/data/sqlite/registry.db") -> str:
    return f"""
import pathlib
import sqlite3
import sys

path = pathlib.Path({db_path!r})
path.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(path)
try:
    migration_plan = {{
        'employees': [('sensitivity_level', \"TEXT DEFAULT 'unclassified'\")],
        'campaign_contacts': [('sensitivity_level', \"TEXT DEFAULT 'unclassified'\")],
        'transactions': [('sensitivity_level', \"TEXT DEFAULT 'unclassified'\")],
        'customers': [('region', 'TEXT'), ('sensitivity_level', \"TEXT DEFAULT 'unclassified'\")],
    }}
    for table_name, columns in migration_plan.items():
        try:
            existing_columns = [row[1] for row in conn.execute(f'PRAGMA table_info({{table_name}})')]
        except sqlite3.OperationalError:
            continue
        for column_name, column_definition in columns:
            if column_name not in existing_columns:
                try:
                    conn.execute(f'ALTER TABLE {{table_name}} ADD COLUMN {{column_name}} {{column_definition}}')
                except sqlite3.OperationalError:
                    continue
    conn.commit()
    conn.executescript(sys.stdin.read())
    conn.commit()
finally:
    conn.close()
"""


def _split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_dollar_quote = False
    dollar_quote_tag: str | None = None
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql_text):
        ch = sql_text[i]
        next_two = sql_text[i:i+2]

        if in_line_comment:
            buffer.append(ch)
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if next_two == "*/":
                buffer.append(next_two)
                in_block_comment = False
                i += 1
            else:
                buffer.append(ch)
        elif in_dollar_quote:
            if dollar_quote_tag and sql_text.startswith(dollar_quote_tag, i):
                buffer.append(dollar_quote_tag)
                i += len(dollar_quote_tag) - 1
                in_dollar_quote = False
                dollar_quote_tag = None
            else:
                buffer.append(ch)
        elif next_two == "--":
            buffer.append(next_two)
            in_line_comment = True
            i += 1
        elif next_two == "/*":
            buffer.append(next_two)
            in_block_comment = True
            i += 1
        elif ch == "'" and not in_double_quote:
            buffer.append(ch)
            in_single_quote = not in_single_quote
        elif ch == '"' and not in_single_quote:
            buffer.append(ch)
            in_double_quote = not in_double_quote
        elif ch == "$" and not in_single_quote and not in_double_quote:
            import re as _re

            match = _re.match(r"\$[A-Za-z0-9_]*\$", sql_text[i:])
            if match:
                dollar_quote_tag = match.group(0)
                in_dollar_quote = True
                buffer.append(dollar_quote_tag)
                i += len(dollar_quote_tag) - 1
            else:
                buffer.append(ch)
        elif ch == ";" and not in_single_quote and not in_double_quote and not in_dollar_quote and not in_line_comment and not in_block_comment:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(ch)
        i += 1

    remaining = "".join(buffer).strip()
    if remaining:
        statements.append(remaining)
    return statements


def _apply_sqlalchemy_direct(sql_text: str, connection_string: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(connection_string)
    with engine.begin() as connection:
        for statement in _split_sql_statements(sql_text):
            connection.execute(text(statement))


def _apply_sqlalchemy_direct_with_fallback(sql_text: str, connection_string: str, *, dialect: str) -> None:
    try:
        _apply_sqlalchemy_direct(sql_text, connection_string)
    except Exception as exc:  # pragma: no cover - exercized via runtime fallback
        print(f"[skip] could not apply {dialect} SQL directly: {exc}")


def _apply_direct_sql(dialect: str, sql_text: str, config: dict) -> None:
    if dialect == "sqlite":
        _apply_sqlite_direct(sql_text, config)
        return

    if dialect in {"postgres", "postgresql"}:
        connection_string = config.get(
            "connection_string") or config.get("dsn")
        if not connection_string:
            raise ValueError(
                "direct postgres config requires 'connection_string' or 'dsn'")
        _apply_sqlalchemy_direct_with_fallback(
            sql_text, connection_string, dialect=dialect)
        return

    if dialect == "mysql":
        connection_string = config.get(
            "connection_string") or config.get("dsn")
        if not connection_string:
            raise ValueError(
                "direct mysql config requires 'connection_string' or 'dsn'")
        _apply_sqlalchemy_direct_with_fallback(
            sql_text, connection_string, dialect=dialect)
        return

    if dialect == "mssql":
        connection_string = config.get(
            "connection_string") or config.get("dsn")
        if not connection_string:
            raise ValueError(
                "direct mssql config requires 'connection_string' or 'dsn'")
        _apply_sqlalchemy_direct_with_fallback(
            sql_text, connection_string, dialect=dialect)
        return

    raise ValueError(f"unsupported dialect: {dialect}")


def apply_sql_file(
    dialect: str,
    sql_path: Path,
    project_dir: Path,
    compose_file: Path,
    dry_run: bool,
    config: dict | None = None,
) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    dialect_config = _get_dialect_config(config, dialect)
    mode = _default_dialect_mode(config, dialect)
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    _log_step(f"Applying {sql_path.name} for {dialect} ({mode} mode)")
    if dry_run:
        print(
            f"[dry-run] would execute {sql_path.name} against {dialect} using {mode} mode")
        return

    if mode == "direct":
        _apply_direct_sql(dialect, sql_text, dialect_config)
        return

    if dialect == "sqlite":
        python_code = _build_sqlite_docker_migration_code()
        service = dialect_config.get("service", "toolbox")
        _run(
            ["docker", "compose", "-f",
                str(compose_file), "exec", "-T", service, "python", "-c", python_code],
            cwd=project_dir,
            input_bytes=sql_text.encode("utf-8"),
        )
        return

    if dialect in {"postgres", "postgresql"}:
        env = os.environ.copy()
        env["PGPASSWORD"] = _resolve_docker_password(
            dialect_config, "PGPASSWORD", project_dir=project_dir)
        service = dialect_config.get("service", "postgres")
        _run(
            ["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"PGPASSWORD={env['PGPASSWORD']}", service, "psql", "-U", dialect_config.get(
                "user", "ikigov"), "-d", dialect_config.get("database", "ikigov_test"), "-v", "ON_ERROR_STOP=1"],
            cwd=project_dir,
            input_bytes=sql_text.encode("utf-8"),
            env=env,
        )
        return

    if dialect == "mysql":
        env = os.environ.copy()
        env["MYSQL_PWD"] = _resolve_docker_password(
            dialect_config, "MYSQL_PWD", project_dir=project_dir)
        service = dialect_config.get("service", "mysql")
        migration_sql = """
SET @sql = IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'employees') = 0,
  'SELECT 1',
  IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'employees' AND COLUMN_NAME = 'sensitivity_level') = 0,
    'ALTER TABLE employees ADD COLUMN sensitivity_level TEXT;',
    'SELECT 1'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'campaign_contacts') = 0,
  'SELECT 1',
  IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'campaign_contacts' AND COLUMN_NAME = 'sensitivity_level') = 0,
    'ALTER TABLE campaign_contacts ADD COLUMN sensitivity_level TEXT;',
    'SELECT 1'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'transactions') = 0,
  'SELECT 1',
  IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'transactions' AND COLUMN_NAME = 'sensitivity_level') = 0,
    'ALTER TABLE transactions ADD COLUMN sensitivity_level TEXT;',
    'SELECT 1'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customers') = 0,
  'SELECT 1',
  IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customers' AND COLUMN_NAME = 'region') = 0,
    'ALTER TABLE customers ADD COLUMN region TEXT;',
    'SELECT 1'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customers') = 0,
  'SELECT 1',
  IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customers' AND COLUMN_NAME = 'sensitivity_level') = 0,
    'ALTER TABLE customers ADD COLUMN sensitivity_level TEXT;',
    'SELECT 1'
  )
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
"""
        combined_sql = migration_sql + sql_text
        _run(
            ["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"MYSQL_PWD={env['MYSQL_PWD']}", service, "mysql", "-u", dialect_config.get(
                "user", "root"), dialect_config.get("database", "ikigov_test")],
            cwd=project_dir,
            input_bytes=combined_sql.encode("utf-8"),
            env=env,
        )
        return

    if dialect == "mssql":
        env = os.environ.copy()
        env["SQLCMDPASSWORD"] = _resolve_docker_password(
            dialect_config, "SQLCMDPASSWORD", project_dir=project_dir)
        service = dialect_config.get("service", "mssql")
        _run(
            [
                "docker",
                "compose", "-f",
                str(compose_file),
                "exec",
                "-T",
                "-e", f"SQLCMDPASSWORD={env['SQLCMDPASSWORD']}",
                service,
                "/opt/mssql-tools18/bin/sqlcmd",
                "-S", dialect_config.get("server", "localhost"),
                "-U", dialect_config.get("user", "sa"),
                "-C", "-i", "/dev/stdin",
            ],
            cwd=project_dir,
            input_bytes=sql_text.encode("utf-8"),
            env=env,
        )
        return

    raise ValueError(f"unsupported dialect: {dialect}")


def resolve_sql_path(dialect: str) -> Path:
    mapping = {
        "sqlite": EXAMPLES_DIR / "sqlite_setup.sql",
        "postgres": EXAMPLES_DIR / "postgresql_setup.sql",
        "postgresql": EXAMPLES_DIR / "postgresql_setup.sql",
        "mysql": EXAMPLES_DIR / "mysql_setup.sql",
        "mssql": EXAMPLES_DIR / "mssql_setup.sql",
    }
    try:
        return mapping[dialect]
    except KeyError as exc:
        raise ValueError(f"unsupported dialect: {dialect}") from exc


def wipe_sqlite(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    dialect_config = _get_dialect_config(config, "sqlite")
    mode = _default_dialect_mode(config, "sqlite")
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    _log_step("Wiping SQLite example data")
    if dry_run:
        print(f"[dry-run] would remove sqlite example data using {mode} mode")
        return
    if mode == "direct":
        db_path = dialect_config.get("path") or dialect_config.get(
            "database_path") or "/data/sqlite/registry.db"
        Path(db_path).unlink(missing_ok=True)
        return
    python_code = """
import pathlib
path = pathlib.Path('/data/sqlite/registry.db')
if path.exists():
    path.unlink()
"""
    _run(["docker", "compose", "-f", str(compose_file), "exec", "-T",
         dialect_config.get("service", "toolbox"), "python", "-c", python_code], cwd=project_dir)


def wipe_postgres(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    dialect_config = _get_dialect_config(config, "postgresql")
    mode = _default_dialect_mode(config, "postgresql")
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    _log_step("Wiping PostgreSQL example data")
    sql_text = """
DROP TABLE IF EXISTS hr.employees;
DROP TABLE IF EXISTS marketing.campaign_contacts;
DROP TABLE IF EXISTS finance.transactions;
DROP TABLE IF EXISTS regional.customers;
DROP SCHEMA IF EXISTS hr CASCADE;
DROP SCHEMA IF EXISTS marketing CASCADE;
DROP SCHEMA IF EXISTS finance CASCADE;
DROP SCHEMA IF EXISTS regional CASCADE;
"""
    if dry_run:
        print(f"[dry-run] would wipe postgres example data using {mode} mode")
        return
    if mode == "direct":
        _apply_direct_sql("postgresql", sql_text, dialect_config)
        return
    env = os.environ.copy()
    env["PGPASSWORD"] = _resolve_docker_password(
        dialect_config, "PGPASSWORD", project_dir=project_dir)
    service = dialect_config.get("service", "postgres")
    _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"PGPASSWORD={env['PGPASSWORD']}", service, "psql", "-U", dialect_config.get("user", "ikigov"), "-d",
         dialect_config.get("database", "ikigov_test"), "-v", "ON_ERROR_STOP=1"], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)


def wipe_mysql(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    dialect_config = _get_dialect_config(config, "mysql")
    mode = _default_dialect_mode(config, "mysql")
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    _log_step("Wiping MySQL example data")
    sql_text = """
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS campaign_contacts;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS customers;
"""
    if dry_run:
        print(f"[dry-run] would wipe mysql example data using {mode} mode")
        return
    if mode == "direct":
        _apply_direct_sql("mysql", sql_text, dialect_config)
        return
    env = os.environ.copy()
    env["MYSQL_PWD"] = _resolve_docker_password(
        dialect_config, "MYSQL_PWD", project_dir=project_dir)
    service = dialect_config.get("service", "mysql")
    _run(
        ["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"MYSQL_PWD={env['MYSQL_PWD']}", service,
         "mysql", "-u", dialect_config.get("user", "root"), dialect_config.get("database", "ikigov_test")],
        cwd=project_dir,
        input_bytes=sql_text.encode("utf-8"),
        env=env,
    )


def wipe_mssql(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    dialect_config = _get_dialect_config(config, "mssql")
    mode = _default_dialect_mode(config, "mssql")
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    _log_step("Wiping MSSQL example data")
    sql_text = """
IF OBJECT_ID('hr.employees', 'U') IS NOT NULL DROP TABLE hr.employees;
IF OBJECT_ID('marketing.campaign_contacts', 'U') IS NOT NULL DROP TABLE marketing.campaign_contacts;
IF OBJECT_ID('finance.transactions', 'U') IS NOT NULL DROP TABLE finance.transactions;
IF OBJECT_ID('regional.customers', 'U') IS NOT NULL DROP TABLE regional.customers;
IF SCHEMA_ID('hr') IS NOT NULL DROP SCHEMA hr;
IF SCHEMA_ID('marketing') IS NOT NULL DROP SCHEMA marketing;
IF SCHEMA_ID('finance') IS NOT NULL DROP SCHEMA finance;
IF SCHEMA_ID('regional') IS NOT NULL DROP SCHEMA regional;
"""
    if dry_run:
        print(f"[dry-run] would wipe mssql example data using {mode} mode")
        return
    if mode == "direct":
        connection_string = dialect_config.get(
            "connection_string") or dialect_config.get("dsn")
        if not connection_string:
            raise ValueError(
                "direct MSSQL teardown requires 'connection_string' or 'dsn' when using direct mode")
        _apply_sqlalchemy_direct_with_fallback(
            sql_text, connection_string, dialect="mssql")
        return
    env = os.environ.copy()
    env["SQLCMDPASSWORD"] = _resolve_docker_password(
        dialect_config, "SQLCMDPASSWORD", project_dir=project_dir)
    service = dialect_config.get("service", "mssql")
    _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"SQLCMDPASSWORD={env['SQLCMDPASSWORD']}", service, "/opt/mssql-tools18/bin/sqlcmd", "-S", dialect_config.get("server",
         "localhost"), "-U", dialect_config.get("user", "sa"), "-C", "-i", "/dev/stdin"], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)


def teardown_dialects(project_dir: Path, compose_file: Path, dialect: str, dry_run: bool, config: dict | None = None) -> None:
    dialects = [dialect] if dialect != "all" else [
        "sqlite", "postgresql", "mysql", "mssql"]
    for current_dialect in dialects:
        if current_dialect == "sqlite":
            wipe_sqlite(project_dir, compose_file, dry_run, config)
        elif current_dialect in {"postgres", "postgresql"}:
            wipe_postgres(project_dir, compose_file, dry_run, config)
        elif current_dialect == "mysql":
            wipe_mysql(project_dir, compose_file, dry_run, config)
        elif current_dialect == "mssql":
            wipe_mssql(project_dir, compose_file, dry_run, config)
        else:
            raise ValueError(f"unsupported dialect: {current_dialect}")


def _should_start_compose(config: dict | None, dialect: str) -> bool:
    if not config:
        return False

    dialects = [dialect] if dialect != "all" else [
        "sqlite", "postgresql", "mysql", "mssql"]
    for current_dialect in dialects:
        mode = _default_dialect_mode(config, current_dialect)
        if mode == "docker":
            return True
    return False


def _should_use_compose_for_dialect(config: dict | None, dialect: str) -> bool:
    if _should_start_compose(config, dialect):
        return True

    if not _docker_available():
        return False

    if dialect == "all":
        return True

    return dialect in {"postgresql", "mysql", "mssql"}


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision and demonstrate enterprise data governance example data.",
        epilog=(
            "Examples:\n"
            "  python examples/enterprise_setup.py --dialect sqlite --dry-run\n"
            "  IKIGOV_ENV=dev python examples/enterprise_setup.py --dialect postgres --dry-run\n"
            "  python examples/enterprise_setup.py --dialect all --teardown"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dialect", choices=["sqlite", "postgres", "postgresql", "mysql", "mssql", "all"], default="all")
    parser.add_argument("--compose-file", type=Path,
                        default=ROOT / "docker-compose.yml")
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path,
                        help="Optional YAML config file for roles, accounts, and connection details. If omitted, the script uses the project config loader and any IKIGOV_ENV selection.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the commands without executing them")
    parser.add_argument("--teardown", action="store_true",
                        help="Wipe the example database contents before applying the setup SQL")
    parser.add_argument("--skip-demo", action="store_true",
                        help="Skip the access-control and policy demos")
    return parser.parse_args(list(argv) if argv is not None else None)


def print_access_summary(dialect: str, config: dict | None = None) -> None:
    _log_step(f"Role permission summary for {dialect}")
    roles_config = config.get("roles", {}) if isinstance(config, dict) else {}
    if not isinstance(roles_config, dict) or not roles_config:
        print("(no role permissions available in the current governance config)")
        return

    print("role | username | password | permissions | scope")
    print("-" * 96)
    for role_name, role_config in sorted(roles_config.items()):
        if not isinstance(role_config, dict):
            continue
        account_config = role_config.get("account", {})
        if not isinstance(account_config, dict):
            account_config = {}
        username = account_config.get("username", role_name)
        password = account_config.get("password", "")
        permissions = role_config.get("permissions", [])
        if isinstance(permissions, str):
            permissions = [permissions]
        elif not isinstance(permissions, list):
            permissions = []
        scope = role_config.get("scope")
        password_display = "********"
        print(
            f"{role_name:<20} | {str(username):<12} | {password_display:<18} | {', '.join(str(item) for item in permissions) if permissions else 'none'} | {scope if scope is not None else 'not set'}")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    project_dir = args.project_dir.resolve()
    compose_file = args.compose_file.resolve()
    if not compose_file.exists():
        raise FileNotFoundError(f"compose file not found: {compose_file}")

    config = _load_config(args.config)
    if args.dry_run:
        _log_step("Dry run only; no changes will be made")

    print("\nEnterprise governance example walkthrough")
    print("This script provisions sample tables, example role accounts, and policy checks for a realistic governance demo.")
    print("Recommended first run: python examples/enterprise_setup.py --dialect sqlite --dry-run --skip-demo")

    if config:
        source = args.config if args.config else "environment-aware config discovery"
        _log_step(f"Loaded governance config from {source}")
        _print_role_account_overview(config)
    else:
        _log_step("No governance config was discovered; using the Docker Compose defaults. Set --config or IKIGOV_ENV to select a YAML profile.")

    for dialect in ([args.dialect] if args.dialect != "all" else ["sqlite", "postgresql", "mysql", "mssql"]):
        validate_runtime_config(dialect, config=config,
                                project_dir=project_dir)

    if _should_use_compose_for_dialect(config, args.dialect):
        ensure_compose_up(project_dir, compose_file, args.dry_run)
    else:
        _log_step(
            "Skipping Docker Compose startup; using direct database connections")

    if not args.skip_demo:
        _demo_access_control_crud()
        _demo_policy_permissions()
        _demo_enterprise_role_validation(config)
        _demo_account_role_access(config)

    if args.teardown:
        teardown_dialects(project_dir, compose_file,
                          args.dialect, args.dry_run, config)

    dialects = [args.dialect] if args.dialect != "all" else [
        "sqlite", "postgresql", "mysql", "mssql"]
    for dialect in dialects:
        apply_sql_file(dialect, resolve_sql_path(dialect),
                       project_dir, compose_file, args.dry_run, config)
        provision_role_accounts(project_dir, compose_file,
                                dialect, dry_run=args.dry_run, config=config)
        print_access_summary(dialect, config=config)

    _log_step("Enterprise example setup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
