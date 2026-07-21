import json

from ikidgov.core.audit import emit_audit_event
from ikidgov.modules.access_control.impl import AccessControlModule
from ikidgov.modules.policy_engine.impl import PolicyEngine


def test_emit_audit_event_writes_jsonl(tmp_path, monkeypatch):
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("IKIGOV_AUDIT_LOG", str(log_path))

    payload = emit_audit_event(
        "policy_evaluated",
        actor_role="analyst",
        action_type="select",
    )

    assert payload["event"] == "policy_evaluated"
    assert payload["actor_role"] == "analyst"
    assert log_path.exists()

    encoded = log_path.read_text(encoding="utf-8").strip()
    parsed = json.loads(encoded)
    assert parsed["event"] == "policy_evaluated"
    assert parsed["action_type"] == "select"


def test_policy_engine_emits_audit_event_on_check(tmp_path, monkeypatch):
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("IKIGOV_AUDIT_LOG", str(log_path))

    engine = PolicyEngine()
    decision = engine.check(actor_role="analyst", action_type="select")

    assert decision is not None
    encoded = log_path.read_text(encoding="utf-8").strip().splitlines()
    parsed = json.loads(encoded[-1])
    assert parsed["event"] == "policy_evaluated"
    assert parsed["actor_role"] == "analyst"
    assert parsed["action_type"] == "select"


def test_access_control_module_emits_audit_event_on_create_role(tmp_path, monkeypatch):
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("IKIGOV_AUDIT_LOG", str(log_path))

    module = AccessControlModule(db_path=str(tmp_path / "access.db"))
    module.run(action="create_role", name="auditor", description="Audit role")

    encoded = log_path.read_text(encoding="utf-8").strip().splitlines()
    parsed = json.loads(encoded[-1])
    assert parsed["event"] == "access_control_action"
    assert parsed["action"] == "create_role"
    assert parsed["entity"] == "role"
