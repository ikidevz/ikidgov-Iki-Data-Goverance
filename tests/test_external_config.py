import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_role_definitions_can_be_overridden_by_external_config(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
roles:
  analyst:
    description: custom analyst
    account:
      username: analyst_user
      password: analyst_pw
    permissions:
      - select
      - update
    scope: custom_scope
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IKIGOV_CONFIG", str(config_path))

    import ikidgov.modules.access_control.roles as roles_module

    importlib.reload(roles_module)

    assert roles_module.ROLE_DEFINITIONS["analyst"]["description"] == "custom analyst"
    assert roles_module.ROLE_DEFINITIONS["analyst"]["permissions"] == [
        "select", "update"]
    assert roles_module.ROLE_DEFINITIONS["analyst"]["scope"] == "custom_scope"
    assert roles_module.ROLE_DEFINITIONS["analyst"]["account"]["username"] == "analyst_user"
    assert roles_module.ROLE_DEFINITIONS["analyst"]["account"]["password"] == "analyst_pw"


def test_connector_default_types_can_be_overridden_by_external_config(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
connectors:
  csv:
    default_type: integer
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IKIGOV_CONFIG", str(config_path))

    import ikidgov.config_loader as config_loader
    import ikidgov.connectors.csv_connector as csv_connector_module

    importlib.reload(config_loader)
    importlib.reload(csv_connector_module)

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("name\nada\n", encoding="utf-8")

    discovery = csv_connector_module.CSVConnector(str(csv_path)).discover()

    assert discovery["columns"][0]["dtype"] == "integer"


def test_policy_compile_uses_account_credentials_from_external_config(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
roles:
  data_owner:
    account:
      username: finance_user
      password: StrongPw!23
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IKIGOV_CONFIG", str(config_path))

    import ikidgov.config_loader as config_loader
    import ikidgov.modules.policy_engine.impl as policy_impl

    importlib.reload(config_loader)
    importlib.reload(policy_impl)

    result = policy_impl.PolicyEngine().compile(
        "restrict_pii", "employees", dialect="mysql")

    assert "CREATE USER IF NOT EXISTS `finance_user`@'%' IDENTIFIED BY 'StrongPw!23';" in result["sql"]


def test_config_loader_falls_back_to_current_working_directory(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
roles:
  analyst:
    description: cwd override
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    import ikidgov.config_loader as config_loader

    importlib.reload(config_loader)

    assert config_loader.get_roles_config(
    )["analyst"]["description"] == "cwd override"


def test_config_loader_prefers_environment_specific_config(tmp_path, monkeypatch):
    env_config_path = tmp_path / "governance.dev.yaml"
    env_config_path.write_text(
        """
roles:
  analyst:
    description: dev override
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IKIGOV_ENV", "dev")

    import ikidgov.config_loader as config_loader

    importlib.reload(config_loader)

    assert config_loader.get_roles_config(
    )["analyst"]["description"] == "dev override"


def test_show_config_reports_environment_and_roles(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.dev.yaml"
    config_path.write_text(
        """
roles:
  analyst:
    account:
      username: analyst_dev
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IKIGOV_ENV", "dev")

    result = subprocess.run(
        [sys.executable, "-m", "ikidgov.cli.main",
            "show-config", "--format", "json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={**os.environ,
             "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert result.returncode == 0, result.stderr
    assert '"environment": "dev"' in result.stdout
    assert '"analyst"' in result.stdout


def test_canonical_config_is_normalized_and_preserved(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
roles:
  analyst:
    description: canonical analyst
    account:
      username: analyst_user
      password: "StrongPw!23"
    permissions:
      - select
    scope: policy_restricted
connectors:
  csv:
    default_type: string
sqlite:
  mode: direct
  path: ./data/sqlite/registry.db
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IKIGOV_CONFIG", str(config_path))

    import ikidgov.config_loader as config_loader

    importlib.reload(config_loader)

    normalized = config_loader.load_config(str(config_path))

    assert normalized["roles"]["analyst"]["account"]["password"] == "StrongPw!23"
    assert normalized["sqlite"]["mode"] == "direct"
    assert normalized["connectors"]["csv"]["default_type"] == "string"


def test_config_loader_rejects_malformed_role_account_shape(tmp_path, monkeypatch):
    config_path = tmp_path / "governance.yaml"
    config_path.write_text(
        """
roles:
  analyst:
    account: not-a-dict
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IKIGOV_CONFIG", str(config_path))

    import ikidgov.config_loader as config_loader

    importlib.reload(config_loader)

    with pytest.raises(ValueError, match="roles.analyst.account"):
        config_loader.load_config(str(config_path))
