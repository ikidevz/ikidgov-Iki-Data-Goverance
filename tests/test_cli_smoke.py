import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_cli_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ),
             "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "iki-datagov" in result.stdout.lower()


def test_cli_loads_environment_flag():
    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main", "--env",
            "dev", "show-config", "--format", "json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ),
             "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode == 0
    assert '"environment": "dev"' in result.stdout


def test_policy_compile_fails_without_configured_password():
    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main", "policy-compile", "--policy",
            "restrict_pii", "--table", "employees", "--dialect", "mysql"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ),
             "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode != 0
    assert "password" in result.stderr.lower(
    ) or "missing password" in result.stderr.lower()


def test_policy_compile_generates_sql_with_explicit_password(tmp_path):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """roles:
  admin:
    account:
      username: admin
      password: StrongPw!23
  data_owner:
    account:
      username: data_owner
      password: DataOwnerPw!23
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main", "policy-compile", "--policy",
            "restrict_pii", "--table", "employees", "--dialect", "mysql"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(ROOT /
                                                                 "src"), "IKIGOV_CONFIG": str(config_path)},
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE USER IF NOT EXISTS `admin`@'localhost' IDENTIFIED BY '********';" in result.stdout
    assert "GRANT SELECT ON `employees` TO `data_owner`;" in result.stdout
    assert "StrongPw!23" not in result.stdout


def test_policy_compile_reveal_secrets_flag_prints_real_password(tmp_path):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """roles:
  admin:
    account:
      username: admin
      password: StrongPw!23
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main", "policy-compile", "--policy",
            "restrict_pii", "--table", "employees", "--dialect", "mysql", "--reveal-secrets"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(ROOT /
                                                                 "src"), "IKIGOV_CONFIG": str(config_path)},
    )
    assert result.returncode == 0, result.stderr
    assert "StrongPw!23" in result.stdout
    assert "IDENTIFIED BY 'StrongPw!23'" in result.stdout


def test_register_dataset_requires_actor_role():
    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main", "register-dataset",
            "--source", "demo", "--name", "demo", "--owner", "tester"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ),
             "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode != 0
    assert "actor-role" in result.stderr.lower()
