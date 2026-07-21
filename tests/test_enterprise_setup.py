import importlib.util
import sqlite3
import subprocess
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


def test_main_uses_compose_for_sql_backends_when_docker_is_available(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3'\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(module, "_load_config", lambda path: None)
    monkeypatch.setattr(module, "_docker_available", lambda: True)
    monkeypatch.setattr(module, "ensure_compose_up",
                        lambda *args, **kwargs: calls.append("compose"))
    monkeypatch.setattr(module, "_demo_access_control_crud", lambda: None)
    monkeypatch.setattr(module, "_demo_policy_permissions", lambda: None)
    monkeypatch.setattr(
        module, "_demo_enterprise_role_validation", lambda config=None: None)
    monkeypatch.setattr(module, "_demo_account_role_access",
                        lambda config=None: None)
    monkeypatch.setattr(module, "apply_sql_file",
                        lambda *args, **kwargs: calls.append("apply"))
    monkeypatch.setattr(module, "provision_role_accounts",
                        lambda *args, **kwargs: calls.append("provision"))
    monkeypatch.setattr(module, "print_access_summary",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "teardown_dialects",
                        lambda *args, **kwargs: None)

    result = module.main([
        "--dialect",
        "mssql",
        "--skip-demo",
        "--project-dir",
        str(tmp_path),
        "--compose-file",
        str(compose_file),
    ])

    assert result == 0
    assert "compose" in calls
    assert "apply" in calls
    assert "provision" in calls


def test_main_defaults_to_direct_sql_connections_without_compose(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3'\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(module, "_load_config", lambda path: None)
    monkeypatch.setattr(module, "ensure_compose_up",
                        lambda *args, **kwargs: calls.append("compose"))
    monkeypatch.setattr(module, "_demo_access_control_crud", lambda: None)
    monkeypatch.setattr(module, "_demo_policy_permissions", lambda: None)
    monkeypatch.setattr(
        module, "_demo_enterprise_role_validation", lambda config=None: None)
    monkeypatch.setattr(module, "_demo_account_role_access",
                        lambda config=None: None)
    monkeypatch.setattr(module, "apply_sql_file",
                        lambda *args, **kwargs: calls.append("apply"))
    monkeypatch.setattr(module, "provision_role_accounts",
                        lambda *args, **kwargs: calls.append("provision"))
    monkeypatch.setattr(module, "print_access_summary",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "teardown_dialects",
                        lambda *args, **kwargs: None)

    result = module.main([
        "--dialect",
        "sqlite",
        "--skip-demo",
        "--project-dir",
        str(tmp_path),
        "--compose-file",
        str(compose_file),
    ])

    assert result == 0
    assert "compose" not in calls
    assert "apply" in calls
    assert "provision" in calls


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


def test_resolve_docker_password_falls_back_to_dotenv_file(tmp_path, monkeypatch):
    module = _load_enterprise_setup_module()
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    password = module._resolve_docker_password(
        {}, "PGPASSWORD", project_dir=tmp_path)

    assert password == "from-dotenv"


def test_resolve_docker_password_uses_mysql_root_password_from_dotenv(tmp_path, monkeypatch):
    module = _load_enterprise_setup_module()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MYSQL_ROOT_PASSWORD=from-root-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("MYSQL_PWD", raising=False)
    monkeypatch.delenv("MYSQL_ROOT_PASSWORD", raising=False)

    password = module._resolve_docker_password(
        {}, "MYSQL_PWD", project_dir=tmp_path)

    assert password == "from-root-dotenv"


def test_provision_role_accounts_uses_demo_passwords_for_missing_account_passwords(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    captured: list[dict] = []

    def fake_apply_direct_sql(dialect, sql_text, config):
        captured.append(
            {"dialect": dialect, "sql_text": sql_text, "config": config})

    monkeypatch.setattr(module, "_apply_direct_sql", fake_apply_direct_sql)

    module.provision_role_accounts(
        tmp_path,
        tmp_path / "docker-compose.yml",
        "postgresql",
        dry_run=False,
        config={
            "postgresql": {"password": "TestPass123!"},
            "roles": {
                "admin": {"account": {"username": "admin"}},
                "analyst": {},
            },
        },
    )

    assert captured
    sql_payload = captured[0]["sql_text"]
    assert "ChangeMe123!" in sql_payload


def test_provision_role_accounts_uses_schema_qualified_table_for_mssql(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    captured: list[tuple[list[str], dict]] = []

    def fake_run(cmd, **kwargs):
        captured.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(module, "_run", fake_run)

    module.provision_role_accounts(
        tmp_path,
        tmp_path / "docker-compose.yml",
        "mssql",
        dry_run=False,
        config={
            "mssql": {"password": "TestPass123!"},
            "roles": {
                "admin": {
                    "account": {"username": "admin", "password": "StrongPw!23"}
                },
                "data_owner": {
                    "account": {"username": "data_owner", "password": "DataOwnerPw!23"}
                },
            }
        },
    )

    assert captured
    sql_payload = captured[0][1]["input_bytes"].decode("utf-8")
    assert "[hr].[employees]" in sql_payload


def test_provision_role_accounts_uses_sqlalchemy_fallback_for_mssql_direct_connection(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    captured: list[tuple[str, str, str]] = []

    def fake_apply(sql_text, connection_string, *, dialect):
        captured.append((sql_text, connection_string, dialect))

    monkeypatch.setattr(
        module,
        "_apply_sqlalchemy_direct_with_fallback",
        fake_apply,
    )

    module.provision_role_accounts(
        tmp_path,
        tmp_path / "docker-compose.yml",
        "mssql",
        dry_run=False,
        config={
            "mssql": {"connection_string": "mssql+pyodbc://", "mode": "direct"},
            "roles": {
                "admin": {
                    "account": {"username": "admin", "password": "StrongPw!23"}
                },
            },
        },
    )

    assert captured
    assert captured[0][2] == "mssql"
    assert "CREATE LOGIN" in captured[0][0] or "CREATE ROLE" in captured[0][0]


def test_wipe_mssql_uses_sqlalchemy_fallback_for_direct_mode(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    captured: list[tuple[str, str, str]] = []

    def fake_apply(sql_text, connection_string, *, dialect):
        captured.append((sql_text, connection_string, dialect))

    monkeypatch.setattr(
        module,
        "_apply_sqlalchemy_direct_with_fallback",
        fake_apply,
    )

    module.wipe_mssql(
        tmp_path,
        tmp_path / "docker-compose.yml",
        dry_run=False,
        config={"mssql": {"connection_string": "mssql+pyodbc://", "mode": "direct"}},
    )

    assert captured
    assert captured[0][2] == "mssql"
    assert "DROP TABLE" in captured[0][0]


def test_validate_runtime_config_requires_connection_string_for_direct_mode(tmp_path):
    module = _load_enterprise_setup_module()

    with pytest.raises(ValueError, match="connection_string"):
        module.validate_runtime_config(
            "postgresql",
            config={"postgresql": {"mode": "direct"}},
            project_dir=tmp_path,
        )


def test_validate_runtime_config_requires_password_for_docker_mode(tmp_path, monkeypatch):
    module = _load_enterprise_setup_module()
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="password"):
        module.validate_runtime_config(
            "postgresql",
            config={"postgresql": {"mode": "docker"}},
            project_dir=tmp_path,
        )


def test_mssql_sqlcmd_uses_dev_stdin_for_input(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    sql_path = tmp_path / "mssql_setup.sql"
    sql_path.write_text("SELECT 1;", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(module, "_run", fake_run)

    module.apply_sql_file(
        "mssql",
        sql_path,
        tmp_path,
        tmp_path / "docker-compose.yml",
        dry_run=False,
        config={"mssql": {"password": "TestPass123!", "mode": "docker"}},
    )

    assert captured
    assert any("/dev/stdin" in part for part in captured[0])
    assert "bash" not in captured[0]
    assert "-lc" not in captured[0]
    assert "bash" not in captured[0]
    assert "-lc" not in captured[0]


def test_provision_role_accounts_uses_mssql_stdin(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(module, "_run", fake_run)

    module.provision_role_accounts(
        tmp_path,
        tmp_path / "docker-compose.yml",
        "mssql",
        dry_run=False,
        config={
            "mssql": {"password": "TestPass123!"},
            "roles": {
                "admin": {
                    "account": {"username": "admin", "password": "StrongPw!23"}
                },
                "data_owner": {
                    "account": {"username": "data_owner", "password": "DataOwnerPw!23"}
                },
            }
        },
    )

    assert captured
    assert any("/dev/stdin" in part for part in captured[0])


def test_provision_role_accounts_uses_configured_roles_and_accounts(monkeypatch, tmp_path):
    module = _load_enterprise_setup_module()
    captured: list[dict] = []

    def fake_apply_direct_sql(dialect, sql_text, config):
        captured.append(
            {"dialect": dialect, "sql_text": sql_text, "config": config})

    monkeypatch.setattr(module, "_apply_direct_sql", fake_apply_direct_sql)

    module.provision_role_accounts(
        tmp_path,
        tmp_path / "docker-compose.yml",
        "mysql",
        dry_run=False,
        config={
            "mysql": {"password": "TestPass123!"},
            "roles": {
                "admin": {
                    "account": {"username": "finance_user", "password": "StrongPw!23"}
                },
                "data_owner": {
                    "account": {"username": "data_owner", "password": "DataOwnerPw!23"}
                },
                "analyst": {},
            }
        },
    )

    assert captured
    sql_payload = captured[0]["sql_text"]
    assert "CREATE USER IF NOT EXISTS `finance_user`@'%' IDENTIFIED BY 'StrongPw!23';" in sql_payload
