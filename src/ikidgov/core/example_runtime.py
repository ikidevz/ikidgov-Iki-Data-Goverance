from __future__ import annotations

import os
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from ikidgov.config_loader import load_config

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = ROOT / "examples"


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    print("+", " ".join(shlex.quote(str(part)) for part in cmd))
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    return result


def _load_config(path: Path | None) -> dict | None:
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
        loaded = load_config(path)
        return loaded or None
    loaded = load_config(None)
    return loaded or None


def _get_dialect_config(config: dict | None, dialect: str) -> dict:
    if not config:
        return {}
    if dialect in {"postgres", "postgresql"}:
        return dict(config.get("postgresql", {}))
    return dict(config.get(dialect, {}))


def _default_dialect_mode(config: dict | None, dialect: str) -> str:
    if not isinstance(config, dict):
        return "direct"
    dialect_config = config.get(dialect, {})
    if not isinstance(dialect_config, dict):
        return "direct"
    requested_mode = dialect_config.get("mode")
    if requested_mode in {"docker", "direct"}:
        return requested_mode
    return "direct"


def _resolve_docker_password(dialect_config: dict, env_name: str, *, project_dir: Path | None = None) -> str:
    password = dialect_config.get("password")
    if password:
        return password
    env_password = os.getenv(env_name)
    if env_password:
        return env_password
    if project_dir is None:
        project_dir = ROOT
    env_file = project_dir / ".env"
    if env_file.exists():
        values = {}
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        if env_name == "PGPASSWORD":
            env_password = values.get(
                "POSTGRES_PASSWORD") or values.get("PGPASSWORD")
        elif env_name == "MYSQL_PWD":
            env_password = (
                values.get("MYSQL_ROOT_PASSWORD")
                or values.get("MYSQL_ROOT_PWD")
                or values.get("MYSQL_PASSWORD")
                or values.get("MYSQL_PWD")
            )
        elif env_name == "SQLCMDPASSWORD":
            env_password = values.get(
                "MSSQL_SA_PASSWORD") or values.get("SQLCMDPASSWORD")
        if env_password:
            return env_password
    raise ValueError(
        f"Missing Docker auth password for env var {env_name}. "
        "Set the dialect password in the example config, export the env var, or place it in the project .env file before running."
    )


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "compose", "version"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def validate_runtime_config(dialect: str, *, config: dict | None = None, project_dir: Path | None = None) -> None:
    dialect_config = _get_dialect_config(config, dialect)
    mode = _default_dialect_mode(config, dialect)
    if mode == "direct" and _should_use_compose_for_dialect(config, dialect):
        mode = "docker"
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    if dialect in {"sqlite"}:
        return
    if dialect_config.get("mode") == "direct":
        connection_string = dialect_config.get(
            "connection_string") or dialect_config.get("dsn")
        if not connection_string:
            raise ValueError(
                f"Direct mode for {dialect} requires a connection_string or dsn in the config.")
        return
    if dialect_config.get("mode") == "docker":
        password = dialect_config.get("password")
        if not password:
            try:
                password = _resolve_docker_password(
                    dialect_config,
                    {"postgresql": "PGPASSWORD", "mysql": "MYSQL_PWD",
                        "mssql": "SQLCMDPASSWORD"}.get(dialect, "SQLCMDPASSWORD"),
                    project_dir=project_dir,
                )
            except ValueError:
                password = None
        explicit_dialect_config = False
        if isinstance(config, dict):
            raw_config = config.get(dialect, {})
            if isinstance(raw_config, dict):
                explicit_dialect_config = bool(raw_config)
        if not password and explicit_dialect_config:
            raise ValueError(
                f"Docker mode for {dialect} requires a password in the config or environment.")
        return


def ensure_compose_up(project_dir: Path, compose_file: Path, dry_run: bool) -> None:
    print(f"\n=== Starting Docker Compose services ===")
    if dry_run:
        print(f"[dry-run] docker compose -f {compose_file.name} up -d --wait")
        return
    _run(["docker", "compose", "-f", str(compose_file),
         "up", "-d", "--wait"], cwd=project_dir)


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


def _ensure_sqlite_schema_migration(db_path: Path) -> None:
    if not db_path.exists():
        return
    migration_plan = {
        "employees": [("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
        "campaign_contacts": [("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
        "transactions": [("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
        "customers": [("region", "TEXT"), ("sensitivity_level", "TEXT DEFAULT 'unclassified'")],
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
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
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
        next_two = sql_text[i:i + 2]
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
    except Exception as exc:  # pragma: no cover - exercised via runtime fallback
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
    print(f"\n=== Applying {sql_path.name} for {dialect} ({mode} mode) ===")
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
        _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", service, "python",
             "-c", python_code], cwd=project_dir, input_bytes=sql_text.encode("utf-8"))
        return
    if dialect in {"postgres", "postgresql"}:
        env = os.environ.copy()
        env["PGPASSWORD"] = _resolve_docker_password(
            dialect_config, "PGPASSWORD", project_dir=project_dir)
        service = dialect_config.get("service", "postgres")
        _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"PGPASSWORD={env['PGPASSWORD']}", service, "psql", "-U", dialect_config.get(
            "user", "ikigov"), "-d", dialect_config.get("database", "ikigov_test"), "-v", "ON_ERROR_STOP=1"], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)
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
        _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"MYSQL_PWD={env['MYSQL_PWD']}", service, "mysql", "-u", dialect_config.get(
            "user", "root"), dialect_config.get("database", "ikigov_test")], cwd=project_dir, input_bytes=combined_sql.encode("utf-8"), env=env)
        return
    if dialect == "mssql":
        env = os.environ.copy()
        env["SQLCMDPASSWORD"] = _resolve_docker_password(
            dialect_config, "SQLCMDPASSWORD", project_dir=project_dir)
        service = dialect_config.get("service", "mssql")
        _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"SQLCMDPASSWORD={env['SQLCMDPASSWORD']}", service, "/opt/mssql-tools18/bin/sqlcmd", "-S", dialect_config.get(
            "server", "localhost"), "-U", dialect_config.get("user", "sa"), "-C", "-i", "/dev/stdin"], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)
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
    print(f"\n=== Wiping SQLite example data ===")
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
    print(f"\n=== Wiping PostgreSQL example data ===")
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
    _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"PGPASSWORD={env['PGPASSWORD']}", service, "psql", "-U", dialect_config.get(
        "user", "ikigov"), "-d", dialect_config.get("database", "ikigov_test"), "-v", "ON_ERROR_STOP=1"], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)


def wipe_mysql(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    dialect_config = _get_dialect_config(config, "mysql")
    mode = _default_dialect_mode(config, "mysql")
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    print(f"\n=== Wiping MySQL example data ===")
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
    _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"MYSQL_PWD={env['MYSQL_PWD']}", service, "mysql", "-u", dialect_config.get(
        "user", "root"), dialect_config.get("database", "ikigov_test")], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)


def wipe_mssql(project_dir: Path, compose_file: Path, dry_run: bool, config: dict | None = None) -> None:
    dialect_config = _get_dialect_config(config, "mssql")
    mode = _default_dialect_mode(config, "mssql")
    dialect_config = dict(dialect_config)
    dialect_config.setdefault("mode", mode)
    print(f"\n=== Wiping MSSQL example data ===")
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
    _run(["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"SQLCMDPASSWORD={env['SQLCMDPASSWORD']}", service, "/opt/mssql-tools18/bin/sqlcmd", "-S", dialect_config.get(
        "server", "localhost"), "-U", dialect_config.get("user", "sa"), "-C", "-i", "/dev/stdin"], cwd=project_dir, input_bytes=sql_text.encode("utf-8"), env=env)


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
