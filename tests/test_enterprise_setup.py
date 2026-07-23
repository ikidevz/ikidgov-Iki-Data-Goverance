import importlib.util
import sqlite3
from pathlib import Path

import pytest

from ikidgov.modules.policy_engine.impl import PolicyEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_enterprise_setup_module():
    spec = importlib.util.spec_from_file_location(
        "enterprise_setup",
        ROOT / "examples" / "enterprise_setup.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_postgres_role_statement_uses_valid_sql():
    engine = PolicyEngine()
    statement = engine._create_role_statement("admin", "postgres")

    assert "CREATE ROLE IF NOT EXISTS" not in statement
    assert "pg_roles" in statement
    assert 'CREATE ROLE "admin"' in statement


def test_sqlite_schema_migration_adds_missing_region_column(tmp_path):
    module = _load_enterprise_setup_module()
    db_path = tmp_path / "registry.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL, sensitivity_level TEXT DEFAULT 'unclassified')"
        )
        connection.commit()
    finally:
        connection.close()

    module._ensure_sqlite_schema_migration(db_path)

    connection = sqlite3.connect(db_path)
    try:
        columns = [row[1]
                   for row in connection.execute("PRAGMA table_info(customers)")]
    finally:
        connection.close()

    assert "region" in columns


def test_sqlite_schema_migration_is_a_noop_for_missing_database(tmp_path):
    module = _load_enterprise_setup_module()
    # Should not raise even though the file doesn't exist yet.
    module._ensure_sqlite_schema_migration(tmp_path / "does-not-exist.db")


def test_collects_role_account_overview_from_config():
    module = _load_enterprise_setup_module()
    config = {
        "roles": {
            "admin": {
                "description": "Platform administrator",
                "account": {"username": "admin_user", "password": "Secret123!"},
                "permissions": ["all"],
                "scope": "global",
            },
            "analyst": {
                "description": "Read-only consumer",
                "account": {"username": "analyst_user"},
                "permissions": ["select"],
                "scope": "policy_restricted",
            },
        }
    }

    overview = module._collect_role_account_overview(config)

    assert overview[0]["role"] == "admin"
    assert overview[0]["username"] == "admin_user"
    assert overview[0]["permissions"] == ["all"]
    assert overview[1]["username"] == "analyst_user"


def test_print_access_summary_uses_configured_permissions(capsys):
    module = _load_enterprise_setup_module()
    config = {
        "roles": {
            "data_owner": {
                "permissions": ["select", "insert", "delete", "create", "alter"],
                "scope": "owned_datasets_only",
            },
            "analyst": {
                "permissions": ["select"],
                "scope": "policy_restricted",
            },
        }
    }

    module.print_access_summary("sqlite", config=config)

    output = capsys.readouterr().out
    assert "role | username | password | permissions | scope" in output
    assert "data_owner" in output
    assert "select, insert, delete, create, alter" in output
    assert "owned_datasets_only" in output
    assert "********" in output
    assert "Secret123!" not in output


def test_print_role_account_overview_includes_description(capsys):
    module = _load_enterprise_setup_module()
    config = {
        "roles": {
            "admin": {
                "description": "Platform administrator",
                "account": {"username": "admin_user"},
                "permissions": ["all"],
                "scope": None,
            },
        }
    }

    module.print_role_account_overview(config)

    output = capsys.readouterr().out
    assert "Platform administrator" in output
    assert "admin_user" in output
    assert "not set" in output


def test_resolve_connection_string_prefers_cli_override():
    module = _load_enterprise_setup_module()

    result = module.resolve_connection_string(
        "postgresql",
        cli_override="postgresql://cli-wins",
        config={"postgresql": {"connection_string": "postgresql://config-loses"}},
        sqlite_path=Path("/tmp/registry.db"),
    )

    assert result == "postgresql://cli-wins"


def test_resolve_connection_string_falls_back_to_env(monkeypatch):
    module = _load_enterprise_setup_module()
    monkeypatch.setenv("IKIGOV_POSTGRES_URL", "postgresql://from-env")

    result = module.resolve_connection_string(
        "postgresql",
        cli_override=None,
        config=None,
        sqlite_path=Path("/tmp/registry.db"),
    )

    assert result == "postgresql://from-env"


def test_resolve_connection_string_falls_back_to_config(monkeypatch):
    module = _load_enterprise_setup_module()
    monkeypatch.delenv("IKIGOV_MYSQL_URL", raising=False)

    result = module.resolve_connection_string(
        "mysql",
        cli_override=None,
        config={"mysql": {"dsn": "mysql+pymysql://from-config"}},
        sqlite_path=Path("/tmp/registry.db"),
    )

    assert result == "mysql+pymysql://from-config"


def test_resolve_connection_string_sqlite_defaults_to_local_file():
    module = _load_enterprise_setup_module()
    sqlite_path = Path("/tmp/example-registry.db")

    result = module.resolve_connection_string(
        "sqlite",
        cli_override=None,
        config=None,
        sqlite_path=sqlite_path,
    )

    assert result == f"sqlite:///{sqlite_path}"


def test_resolve_connection_string_raises_actionable_error_when_unconfigured(monkeypatch):
    module = _load_enterprise_setup_module()
    monkeypatch.delenv("IKIGOV_MSSQL_URL", raising=False)

    with pytest.raises(SystemExit, match="IKIGOV_MSSQL_URL"):
        module.resolve_connection_string(
            "mssql",
            cli_override=None,
            config=None,
            sqlite_path=Path("/tmp/registry.db"),
        )


def test_apply_sql_dry_run_does_not_touch_sqlalchemy():
    module = _load_enterprise_setup_module()

    count = module.apply_sql(
        "sqlite:///:memory:",
        "CREATE TABLE t (id INTEGER); INSERT INTO t VALUES (1);",
        dialect="sqlite",
        dry_run=True,
    )

    assert count == 2


def test_apply_sql_executes_statements_against_sqlite(tmp_path):
    module = _load_enterprise_setup_module()
    db_path = tmp_path / "apply.db"

    count = module.apply_sql(
        f"sqlite:///{db_path}",
        "CREATE TABLE t (id INTEGER); INSERT INTO t VALUES (1);",
        dialect="sqlite",
        dry_run=False,
    )

    assert count == 2
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT id FROM t").fetchall() == [(1,)]
    finally:
        connection.close()


def test_split_statements_handles_mssql_go_batches():
    module = _load_enterprise_setup_module()
    sql_text = "SELECT 1;\nGO\nSELECT 2; SELECT 3;\nGO\n"

    statements = module._split_statements(sql_text, dialect="mssql")

    assert statements == ["SELECT 1;", "SELECT 2; SELECT 3;"]


def test_provision_role_accounts_skips_roles_without_passwords(monkeypatch):
    module = _load_enterprise_setup_module()
    captured: list[dict] = []

    def fake_apply_sql(connection_string, sql_text, *, dialect, dry_run):
        captured.append({"connection_string": connection_string,
                        "sql_text": sql_text, "dialect": dialect})
        return 1

    monkeypatch.setattr(module, "apply_sql", fake_apply_sql)

    module.provision_role_accounts(
        "postgresql",
        "postgresql://example",
        dry_run=False,
        config={
            "roles": {
                "admin": {"account": {"username": "admin", "password": "StrongPw!23"}},
                "analyst": {},
            },
        },
    )

    assert captured
    assert "StrongPw!23" in captured[0]["sql_text"]


def test_provision_role_accounts_uses_configured_roles_and_accounts(monkeypatch):
    module = _load_enterprise_setup_module()
    captured: list[dict] = []

    def fake_apply_sql(connection_string, sql_text, *, dialect, dry_run):
        captured.append(
            {"connection_string": connection_string, "sql_text": sql_text})
        return 1

    monkeypatch.setattr(module, "apply_sql", fake_apply_sql)

    module.provision_role_accounts(
        "mysql",
        "mysql+pymysql://example",
        dry_run=False,
        config={
            "roles": {
                "admin": {"account": {"username": "finance_user", "password": "StrongPw!23"}},
                "data_owner": {"account": {"username": "data_owner", "password": "DataOwnerPw!23"}},
                "analyst": {},
            }
        },
    )

    assert captured
    sql_payload = captured[0]["sql_text"]
    assert "CREATE USER IF NOT EXISTS `finance_user`@'%' IDENTIFIED BY 'StrongPw!23';" in sql_payload


def test_provision_role_accounts_is_noop_for_sqlite(monkeypatch):
    module = _load_enterprise_setup_module()
    calls = []
    monkeypatch.setattr(module, "apply_sql", lambda *a, **k: calls.append(1))

    module.provision_role_accounts(
        "sqlite", "sqlite:///ignored.db", dry_run=False, config={})

    assert calls == []


def test_main_resolves_direct_connection_strings_for_sql_backends(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    calls: list[str] = []

    monkeypatch.setattr(module, "_load_config", lambda path: None)
    monkeypatch.setattr(module, "run_demos", lambda *a, **k: None)
    monkeypatch.setattr(module, "apply_example_data",
                        lambda *args, **kwargs: calls.append("apply"))
    monkeypatch.setattr(module, "provision_role_accounts",
                        lambda *args, **kwargs: calls.append("provision"))
    monkeypatch.setattr(module, "print_access_summary",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(
        module,
        "resolve_connection_string",
        lambda *args, **kwargs: calls.append(
            "resolved") or "mssql+pyodbc://example",
    )

    result = module.main([
        "--dialect", "mssql",
        "--skip-demo",
        "--sqlite-path", str(tmp_path / "registry.db"),
    ])

    assert result == 0
    assert calls == ["resolved", "apply", "provision"]


def test_main_defaults_to_direct_sql_connections(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    calls: list[str] = []

    monkeypatch.setattr(module, "_load_config", lambda path: None)
    monkeypatch.setattr(module, "run_demos", lambda *a, **k: None)
    monkeypatch.setattr(module, "apply_example_data",
                        lambda *args, **kwargs: calls.append("apply"))
    monkeypatch.setattr(module, "provision_role_accounts",
                        lambda *args, **kwargs: calls.append("provision"))
    monkeypatch.setattr(module, "print_access_summary",
                        lambda *args, **kwargs: None)

    result = module.main([
        "--dialect", "sqlite",
        "--skip-demo",
        "--sqlite-path", str(tmp_path / "registry.db"),
    ])

    assert result == 0
    assert "apply" in calls
    assert "provision" in calls


def test_main_rejects_connection_string_with_all_dialects(tmp_path):
    module = _load_enterprise_setup_module()

    with pytest.raises(SystemExit, match="single --dialect"):
        module.main([
            "--dialect", "all",
            "--connection-string", "postgresql://example",
            "--skip-demo",
            "--sqlite-path", str(tmp_path / "registry.db"),
        ])


def test_demo_account_role_access_uses_configured_accounts(capsys):
    module = _load_enterprise_setup_module()
    config = {
        "roles": {
            "admin": {
                "account": {"username": "admin_user", "password": "Secret123!"},
                "permissions": ["all"],
                "scope": None,
            },
            "analyst": {
                "account": {"username": "analyst_user"},
                "permissions": ["select"],
                "scope": "policy_restricted",
            },
        }
    }

    module._demo_account_role_access(config)

    output = capsys.readouterr().out
    assert "admin_user" in output
    assert "analyst_user" in output
    assert "Role access implementation" in output
    assert "select" in output


def test_demo_enterprise_role_validation_prints_multi_role_matrix(capsys):
    module = _load_enterprise_setup_module()
    config = {
        "roles": {
            "data_owner": {
                "permissions": ["select", "insert", "update", "delete"],
                "scope": "owned_datasets_only",
            },
            "analyst": {
                "permissions": ["select"],
                "scope": "policy_restricted",
            },
        }
    }

    module._demo_enterprise_role_validation(config)

    output = capsys.readouterr().out
    assert "Enterprise role validation demo" in output
    assert "data_owner" in output
    assert "analyst" in output
    assert "hr.employees" in output
    assert "sqlite" in output
    assert "mysql" in output
    assert "postgresql" in output
    assert "mssql" in output
