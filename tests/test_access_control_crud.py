import tempfile
from pathlib import Path

import pytest

from ikidgov.modules.access_control.impl import AccessControlPolicyError
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
from ikidgov.modules.access_control.roles import ROLE_DEFINITIONS
from ikidgov.modules.policy_engine.impl import PolicyEngine


def test_access_control_crud_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "access_control.db")

        role = create_role(
            name="admin", description="Administrator", db_path=db_path)
        assert role["name"] == "admin"
        assert role["description"] == "Administrator"

        roles = list_roles(db_path=db_path)
        assert len(roles) == 1

        updated_role = update_role(
            role["id"], description="System administrator", db_path=db_path)
        assert updated_role["description"] == "System administrator"
        assert get_role(role["id"], db_path=db_path)["name"] == "admin"
        assert delete_role(role["id"], db_path=db_path) is True
        assert list_roles(db_path=db_path) == []

        access = create_access(
            name="read", description="Read access", db_path=db_path)
        assert access["name"] == "read"
        assert list_accesses(db_path=db_path)[0]["name"] == "read"
        assert get_access(access["id"], db_path=db_path)["name"] == "read"
        assert update_access(access["id"], description="Allow read operations", db_path=db_path)[
            "description"] == "Allow read operations"
        assert delete_access(access["id"], db_path=db_path) is True
        assert list_accesses(db_path=db_path) == []

        permission = create_permission(
            name="view_reports", description="View reports", db_path=db_path)
        assert permission["name"] == "view_reports"
        assert list_permissions(db_path=db_path)[0]["name"] == "view_reports"
        assert get_permission(permission["id"], db_path=db_path)[
            "name"] == "view_reports"
        assert update_permission(permission["id"], description="View report dashboards", db_path=db_path)[
            "description"] == "View report dashboards"
        assert delete_permission(permission["id"], db_path=db_path) is True
        assert list_permissions(db_path=db_path) == []


def test_backend_argument_is_accepted_for_sqlite():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "access_control_backend.db")
        role = create_role(name="auditor", description="Auditor",
                           db_path=db_path, backend="sqlite")
        assert role["name"] == "auditor"
        assert list_roles(db_path=db_path, backend="sqlite")[
            0]["name"] == "auditor"


def test_role_permissions_are_distinct_for_schema_operations():
    permissions = ROLE_DEFINITIONS["data_owner"]["permissions"]
    assert "select" in permissions
    assert "insert" in permissions
    assert "update" in permissions
    assert "delete" in permissions
    assert "create" in permissions
    assert "drop" in permissions


def test_policy_engine_accepts_dynamic_role_permissions():
    engine = PolicyEngine()
    decision = engine.check(
        actor_role="custom_role",
        action_type="alter",
        role_permissions=["create", "alter", "drop"],
    )
    assert decision.allowed is True


def test_policy_engine_high_sensitivity_explicit_permissions_denied(monkeypatch):
    engine = PolicyEngine()

    monkeypatch.setattr(
        "ikidgov.modules.metadata_registry.interface.get_dataset",
        lambda dataset_id: {
            "columns": [
                {"name": "ssn", "sensitivity_level": "high"}
            ]
        },
    )

    decision = engine.check(
        actor_role="analyst",
        action_type="select",
        dataset_id=1,
        column="ssn",
        role_permissions=["select"],
    )
    assert decision.allowed is False
    assert "lacks required access" in decision.reason.lower()

    decision = engine.check(
        actor_role="analyst",
        action_type="select",
        dataset_id=1,
        column="ssn",
        role_permissions=["select"],
    )
    assert decision.allowed is False
    assert "lacks required access" in decision.reason.lower()


def test_access_control_run_enforces_sod_for_conflicting_roles(tmp_path):
    db_path = str(tmp_path / "sod.db")

    with pytest.raises(AccessControlPolicyError, match="separation-of-duty"):
        create_role(
            name="admin",
            description="Administrator",
            db_path=db_path,
            role_name="admin",
            scope="global",
            assigned_roles=["analyst"],
            requested_permissions=["select"],
        )


def test_access_control_update_emits_audit_event(monkeypatch, tmp_path):
    db_path = str(tmp_path / "audit.db")
    events = []

    monkeypatch.setattr(
        "ikidgov.modules.access_control.impl.emit_audit_event",
        lambda *args, **kwargs: events.append(kwargs),
    )

    role = create_role(name="analyst", description="Analyst", db_path=db_path)
    update_role(role["id"], description="Updated analyst", db_path=db_path)

    assert any(event.get("action") == "update_role" for event in events)
