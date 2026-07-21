import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from ikidgov.config_loader import load_config
from ikidgov.connectors.sql_connector import SQLConnector


ROOT = Path(__file__).resolve().parent.parent


def test_scan_cli_accepts_backend_argument_for_sqlite():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "registry.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT, email TEXT)"
        )
        conn.commit()
        conn.close()

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["IKIGOV_DB_PATH"] = str(db_path)

        scan = subprocess.run(
            [sys.executable, "-m", "ikidgov.cli.main", "scan", "--type", "sql",
                "--path", str(db_path), "--table", "customers", "--owner", "jdoe",
                "--backend", "sqlite"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        assert scan.returncode == 0, scan.stderr
        assert '"source": "sql"' in scan.stdout


def test_sqlite_scan_classify_and_policy_check_work_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "registry.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT, email TEXT, ssn TEXT)"
        )
        conn.execute(
            "INSERT INTO customers (full_name, email, ssn) VALUES (?, ?, ?)",
            ("Jane Doe", "jane@example.com", "123-45-6789"),
        )
        conn.commit()
        conn.close()

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["IKIGOV_DB_PATH"] = str(db_path)

        scan = subprocess.run(
            [sys.executable, "-m", "ikidgov.cli.main", "scan", "--type", "sql",
                "--path", str(db_path), "--table", "customers", "--owner", "jdoe"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        assert scan.returncode == 0, scan.stderr

        classify = subprocess.run(
            [sys.executable, "-m", "ikidgov.cli.main", "classify",
                "--dataset-id", "1", "--detector", "builtin"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        assert classify.returncode == 0, classify.stderr

        policy = subprocess.run(
            [sys.executable, "-m", "ikidgov.cli.main", "policy-check", "--actor-role",
                "analyst", "--action-type", "read", "--dataset-id", "1", "--column", "ssn"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        assert policy.returncode == 0, policy.stderr
        payload = policy.stdout
        assert "allowed" in payload.lower()


def test_sql_connector_can_use_backend_config_for_sqlalchemy_discovery(tmp_path, monkeypatch):
    db_path = tmp_path / "registry.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT, email TEXT)"
    )
    conn.execute(
        "INSERT INTO customers (full_name, email) VALUES (?, ?)",
        ("Jane Doe", "jane@example.com"),
    )
    conn.commit()
    conn.close()

    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
sqlite:
  mode: direct
  connection_string: sqlite:///{} 
""".format(db_path).strip() + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IKIGOV_CONFIG", str(config_path))

    config = load_config(str(config_path))
    connector = SQLConnector(str(db_path), "customers",
                             backend="sqlite", config=config)
    discovered = connector.discover()

    assert discovered["name"] == "customers"
    assert any(column["name"] ==
               "full_name" for column in discovered["columns"])
