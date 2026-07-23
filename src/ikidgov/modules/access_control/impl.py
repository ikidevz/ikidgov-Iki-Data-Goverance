import logging
from typing import Any

from ikidgov.core.audit import emit_audit_event
from ikidgov.core.module_base import Module
from ikidgov.core.crud_base import SqliteCrudBase

logger = logging.getLogger("ikidgov.access_control")


class AccessControlPolicyError(ValueError):
    pass


class AccessControlModule(Module, SqliteCrudBase):
    name = "access_control"
    _MUTATING_ACTIONS = {
        "create_role": ("role", "created"),
        "update_role": ("role", "updated"),
        "delete_role": ("role", "deleted"),
        "create_access": ("access", "created"),
        "update_access": ("access", "updated"),
        "delete_access": ("access", "deleted"),
        "create_permission": ("permission", "created"),
        "update_permission": ("permission", "updated"),
        "delete_permission": ("permission", "deleted"),
    }

    def __init__(self, db_path: str | None = None, backend: str = "sqlite"):
        entity_map = {
            "role": {"table": "roles"},
            "access": {"table": "accesses"},
            "permission": {"table": "permissions"},
        }
        SqliteCrudBase.__init__(self, db_path=db_path,
                                entities=entity_map, backend=backend)

    def validate_access_request(self, *, role_name: str, scope: str | None, assigned_roles: list[str] | None = None, requested_permissions: list[str] | None = None) -> dict[str, Any]:
        assigned_roles = assigned_roles or []
        requested_permissions = requested_permissions or []
        if role_name == "admin" and any(existing_role in {"auditor", "analyst"} for existing_role in assigned_roles):
            raise AccessControlPolicyError(
                "separation-of-duty policy prevents admin from being paired with read-only roles")
        if scope == "global" and any(existing_role in {"auditor"} for existing_role in assigned_roles):
            raise AccessControlPolicyError(
                "separation-of-duty policy prevents global access for auditor roles")
        if "all" in requested_permissions and any(permission in {"read_audit_log"} for permission in requested_permissions):
            raise AccessControlPolicyError(
                "conflicting permissions requested for the same access request")
        return {"allowed": True, "reason": "Access request satisfies policy"}

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "actions": ["create_role", "get_role", "list_roles", "update_role", "delete_role", "create_access", "get_access", "list_accesses", "update_access", "delete_access", "create_permission", "get_permission", "list_permissions", "update_permission", "delete_permission"],
        }

    def run(self, **kwargs: Any) -> dict[str, Any] | list[dict[str, Any]]:
        action = kwargs.get("action")
        backend = kwargs.get("backend") or "sqlite"
        self.backend = backend.lower()
        self._engine = None
        if action in self._MUTATING_ACTIONS:
            self._validate_sod(**kwargs)

        if action == "create_role":
            result = self.create("role", kwargs.get(
                "name"), kwargs.get("description"))
            self._emit_mutation_audit(
                action, "role", kwargs, result, "created")
            return result
        if action == "get_role":
            return self.get("role", kwargs.get("item_id"))
        if action == "list_roles":
            return self.list("role")
        if action == "update_role":
            result = self.update("role", kwargs.get(
                "item_id"), **{k: v for k, v in kwargs.items() if k in {"name", "description"}})
            self._emit_mutation_audit(
                action, "role", kwargs, result, "updated")
            return result
        if action == "delete_role":
            result = self.delete("role", kwargs.get("item_id"))
            self._emit_mutation_audit(
                action, "role", kwargs, result, "deleted")
            return result
        if action == "create_access":
            result = self.create("access", kwargs.get(
                "name"), kwargs.get("description"))
            self._emit_mutation_audit(
                action, "access", kwargs, result, "created")
            return result
        if action == "get_access":
            return self.get("access", kwargs.get("item_id"))
        if action == "list_accesses":
            return self.list("access")
        if action == "update_access":
            result = self.update("access", kwargs.get(
                "item_id"), **{k: v for k, v in kwargs.items() if k in {"name", "description"}})
            self._emit_mutation_audit(
                action, "access", kwargs, result, "updated")
            return result
        if action == "delete_access":
            result = self.delete("access", kwargs.get("item_id"))
            self._emit_mutation_audit(
                action, "access", kwargs, result, "deleted")
            return result
        if action == "create_permission":
            result = self.create("permission", kwargs.get(
                "name"), kwargs.get("description"))
            self._emit_mutation_audit(
                action, "permission", kwargs, result, "created")
            return result
        if action == "get_permission":
            return self.get("permission", kwargs.get("item_id"))
        if action == "list_permissions":
            return self.list("permission")
        if action == "update_permission":
            result = self.update("permission", kwargs.get(
                "item_id"), **{k: v for k, v in kwargs.items() if k in {"name", "description"}})
            self._emit_mutation_audit(
                action, "permission", kwargs, result, "updated")
            return result
        if action == "delete_permission":
            result = self.delete("permission", kwargs.get("item_id"))
            self._emit_mutation_audit(
                action, "permission", kwargs, result, "deleted")
            return result
        raise ValueError(action)

    def _emit_mutation_audit(self, action: str, entity: str, kwargs: dict[str, Any], result: Any, outcome: str) -> None:
        try:
            emit_audit_event(
                "access_control_action",
                action=action,
                entity=entity,
                name=kwargs.get("name"),
                item_id=kwargs.get("item_id"),
                result=outcome,
                success=bool(result),
            )
        except Exception:
            logger.exception(
                "Failed to emit access-control audit event for %s", action)

    def _validate_sod(self, **kwargs: Any) -> None:
        role_name = kwargs.get("role_name") or kwargs.get("name")
        scope = kwargs.get("scope")
        assigned_roles = kwargs.get("assigned_roles") or []
        requested_permissions = kwargs.get("requested_permissions") or []
        if role_name is None:
            return
        self.validate_access_request(
            role_name=str(role_name),
            scope=scope,
            assigned_roles=list(assigned_roles),
            requested_permissions=list(requested_permissions),
        )
