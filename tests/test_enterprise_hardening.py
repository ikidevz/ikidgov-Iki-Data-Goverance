import pytest

from ikidgov.connectors.sql_connector import SQLConnector
from ikidgov.modules.access_control.impl import AccessControlModule
from ikidgov.modules.policy_engine.impl import PolicyEngine


def test_policy_engine_supports_policy_versioning_and_approval(tmp_path):
    module = PolicyEngine()
    policy_path = tmp_path / "restrict_pii.yaml"
    policy_path.write_text(
        """
policy: restrict_pii
version: 2
status: pending_approval
approval_required: true
approved_by: []
change_summary: Add review gate for sensitive columns
""".strip(),
        encoding="utf-8",
    )

    metadata = module.load_policy_definition(policy_path)

    assert metadata["version"] == 2
    assert metadata["approval_required"] is True
    assert metadata["status"] == "pending_approval"


def test_policy_engine_requires_approval_for_pending_policy():
    module = PolicyEngine()
    policy = {
        "policy": "restrict_pii",
        "version": 2,
        "status": "pending_approval",
        "approval_required": True,
        "approved_by": [],
    }

    result = module.validate_policy_deployment(policy, approver_role="auditor")

    assert result["allowed"] is False
    assert "approval" in result["reason"].lower()


def test_access_control_module_rejects_conflicting_roles_for_same_scope():
    module = AccessControlModule()

    with pytest.raises(ValueError, match="separation"):
        module.validate_access_request(
            role_name="admin",
            scope="global",
            assigned_roles=["auditor"],
            requested_permissions=["all"],
        )


def test_sql_connector_health_check_uses_retry_for_transient_failure(monkeypatch):
    connector = SQLConnector(path="/tmp/registry.db", backend="sqlite")

    attempts = {"count": 0}

    def flaky_connect():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient failure")
        return True

    monkeypatch.setattr(connector, "_probe_connection", flaky_connect)

    result = connector.check_health(retries=2, initial_delay=0)

    assert result["healthy"] is True
    assert attempts["count"] == 2
