from ikidgov.modules.access_control.roles import ROLE_DEFINITIONS
import yaml
import re
from pathlib import Path

from ikidgov.config_loader import get_accounts_config
from ikidgov.core.audit import emit_audit_event
from ikidgov.core.decision import Decision
from ikidgov.core.module_base import Module
from ikidgov.core.validation import validate_identifier, validate_table_name


class PolicyLifecycleError(ValueError):
    pass


_POLICY_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

DEFAULT_ROLE_CAPABILITIES = {
    "admin": {"all"},
    "data_owner": {
        "select",
        "insert",
        "update",
        "delete",
        "create",
        "alter",
        "drop",
        "grant_access",
        "approve_classification",
    },
    "data_steward": {
        "select",
        "insert",
        "update",
        "delete",
        "create",
        "alter",
        "drop",
        "classify",
        "propose_policy",
    },
    "analyst": {"select"},
    "auditor": {"read_audit_log"},
    "service_account": {"select"},
}


class PolicyEngine(Module):
    name = "policy_engine"

    def describe(self) -> dict:
        return {"name": self.name, "policies": ["restrict_pii"]}

    def run(self, **kwargs) -> dict:
        actor_role = kwargs.get("actor_role", "analyst")
        action_type = kwargs.get("action_type", "read")
        dataset_id = kwargs.get("dataset_id")
        column = kwargs.get("column")
        decision = self.check(
            actor_role=actor_role, action_type=action_type, dataset_id=dataset_id, column=column)
        return {"allowed": decision.allowed, "reason": decision.reason, "rule_id": decision.rule_id}

    ACTION_ALIASES = {
        "read": "select",
        "select": "select",
        "write": "insert",
        "insert": "insert",
        "update": "update",
        "delete": "delete",
        "drop": "delete",
        "alter": "alter",
        "create": "create",
        "truncate": "truncate",
    }

    def check(self, actor_role: str, action_type: str, dataset_id: int | None = None, column: str | None = None, role_permissions: set[str] | list[str] | None = None) -> Decision:
        policy_path = self._resolve_policy_path("restrict_pii")
        if not policy_path.exists():
            return Decision(False, reason="policy file not found", rule_id=None)
        with policy_path.open(encoding="utf-8") as handle:
            policy = yaml.safe_load(handle) or {}

        required_roles = {r.lower() for r in policy.get(
            "rule", {}).get("requires_role", [])}
        normalized_role = (actor_role or "").lower()
        normalized_action = self.ACTION_ALIASES.get(
            (action_type or "read").lower())
        if normalized_action is None:
            return Decision(False, reason=f"Unknown action_type '{action_type}'", rule_id=policy.get("policy"))

        capabilities = set(role_permissions or [])
        if not capabilities:
            capabilities = DEFAULT_ROLE_CAPABILITIES.get(
                normalized_role, set())

        should_apply_sensitivity_gate = dataset_id is not None and column is not None
        if should_apply_sensitivity_gate and self._column_matches_policy(policy, dataset_id, column):
            if normalized_role not in required_roles and "all" not in capabilities:
                return Decision(False, reason=f"Role '{actor_role}' lacks required access", rule_id=policy.get("policy"))

        if "all" in capabilities or normalized_action in capabilities or (normalized_action in {"insert", "update", "delete", "alter", "create", "truncate"} and "write" in capabilities):
            emit_audit_event(
                "policy_evaluated",
                actor_role=actor_role,
                action_type=action_type,
                dataset_id=dataset_id,
                column=column,
                allowed=True,
                reason="Role is permitted by policy",
            )
            return Decision(True, reason="Role is permitted by policy", rule_id=policy.get("policy"))

        emit_audit_event(
            "policy_evaluated",
            actor_role=actor_role,
            action_type=action_type,
            dataset_id=dataset_id,
            column=column,
            allowed=False,
            reason=f"Role '{actor_role}' lacks required access",
        )
        return Decision(False, reason=f"Role '{actor_role}' lacks required access", rule_id=policy.get("policy"))

    def load_policy_definition(self, policy_path: str | Path | None = None) -> dict:
        if policy_path is None:
            policy_path = self._resolve_policy_path("restrict_pii")
        policy_path = Path(policy_path)
        if not policy_path.exists():
            raise FileNotFoundError(policy_path)
        with policy_path.open(encoding="utf-8") as handle:
            policy = yaml.safe_load(handle) or {}
        if not isinstance(policy, dict):
            raise PolicyLifecycleError("Policy definition must be a mapping")
        policy.setdefault("version", 1)
        policy.setdefault("status", "active")
        policy.setdefault("approval_required", False)
        policy.setdefault("approved_by", [])
        return policy

    def validate_policy_deployment(self, policy: dict | None, *, approver_role: str | None = None) -> dict:
        if not isinstance(policy, dict):
            raise PolicyLifecycleError("Policy definition must be provided")
        if policy.get("approval_required") and policy.get("status") == "pending_approval":
            if not approver_role or approver_role not in {"admin", "data_owner", "auditor"}:
                return {"allowed": False, "reason": "Policy approval requires an authorized approver role"}
            if not policy.get("approved_by"):
                return {"allowed": False, "reason": "Policy approval requires at least one approver"}
        return {"allowed": True, "reason": "Policy deployment is approved"}

    def _resolve_policy_path(self, policy_name: str) -> Path:
        if not _POLICY_NAME_RE.match(policy_name):
            raise ValueError(f"Invalid policy name: {policy_name!r}")

        policies_dir = Path(__file__).resolve(
        ).parent.parent.parent / "policies"
        policy_path = (policies_dir / f"{policy_name}.yaml").resolve()
        if policies_dir not in policy_path.parents and policy_path != policies_dir:
            raise ValueError(
                f"Policy path escapes policies directory: {policy_name!r}")
        return policy_path

    def _column_matches_policy(self, policy: dict, dataset_id: int | None, column: str | None) -> bool:
        if dataset_id is None or column is None:
            return False
        try:
            from ikidgov.modules.metadata_registry.interface import get_dataset
            dataset = get_dataset(dataset_id)
        except Exception:
            return True
        if not dataset:
            return True

        column_name = column.lower()
        for column_item in dataset.get("columns", []):
            if not isinstance(column_item, dict):
                continue
            if column_item.get("name", "").lower() != column_name:
                continue
            sensitivity = (column_item.get("sensitivity_level") or "").lower()
            return sensitivity in {"high", "critical"}

        return False

    def compile(self, policy_name: str, table: str, dialect: str = "generic", config_path: str | None = None, config: dict | None = None) -> dict:
        policy_path = self._resolve_policy_path(policy_name)
        if not policy_path.exists():
            raise FileNotFoundError(policy_path)

        with policy_path.open(encoding="utf-8") as handle:
            policy = yaml.safe_load(handle) or {}

        required_roles = policy.get("rule", {}).get("requires_role", [])
        action = policy.get("rule", {}).get("action", "read")
        validate_table_name(table)
        quoted_table = self._format_table(table, dialect)
        sql = []
        created_roles = set()

        for role in required_roles:
            if role not in created_roles:
                if dialect in {"mysql", "postgres", "postgresql", "mssql"}:
                    account_statement = self._create_account_statement(
                        role, dialect, config=config, config_path=config_path)
                    if account_statement:
                        sql.append(account_statement)
                sql.append(self._create_role_statement(role, dialect))
                created_roles.add(role)
            sql.append(self._grant_statement(
                action, quoted_table, role, dialect))

        return {
            "policy": policy_name,
            "table": table,
            "dialect": dialect,
            "sql": sql,
        }

    def _quote(self, identifier: str, dialect: str) -> str:
        validate_identifier(identifier, kind="identifier")
        if dialect == "mysql":
            return f"`{identifier}`"
        if dialect == "mssql":
            return f"[{identifier}]"
        if dialect == "postgres":
            return f'"{identifier}"'
        return f'"{identifier}"'

    def _create_role_statement(self, role: str, dialect: str) -> str:
        validate_identifier(role, kind="role")
        quoted = self._quote(role, dialect)
        if dialect == "mssql":
            literal = self._string_literal(role)
            return f"IF DATABASE_PRINCIPAL_ID({literal}) IS NULL CREATE ROLE {quoted};"
        if dialect in {"postgres", "postgresql"}:
            return f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {self._string_literal(role)}) THEN CREATE ROLE {quoted} LOGIN; END IF; END $$;"
        return f"CREATE ROLE IF NOT EXISTS {quoted};"

    def _create_account_statement(self, role: str, dialect: str, config: dict | None = None, config_path: str | None = None) -> str:
        validate_identifier(role, kind="role")
        username = role
        password = None

        fallback_account = ROLE_DEFINITIONS.get(role, {}).get("account", {})
        role_config_present = False
        if isinstance(config, dict):
            roles_config = config.get("roles", {})
            if isinstance(roles_config, dict) and role in roles_config:
                role_config_present = True
                role_config = roles_config.get(role, {})
                if isinstance(role_config, dict):
                    account_config = role_config.get("account", {})
                    if isinstance(account_config, dict):
                        username = account_config.get("username", role)
                        password = account_config.get("password")
        else:
            roles_config = get_accounts_config(config_path)
            role_account_config = roles_config.get(
                role, {}) if isinstance(roles_config, dict) else {}
            if role in roles_config and isinstance(role_account_config, dict):
                role_config_present = True
                username = role_account_config.get("username", role)
                password = role_account_config.get("password")
            else:
                username = role
                password = None

        if not isinstance(password, str) or not password:
            password = fallback_account.get("password")
            username = username or fallback_account.get("username", role)

        if not isinstance(username, str) or not username:
            raise ValueError(f"Invalid username for role {role!r}")
        validate_identifier(username, kind="username")
        if not isinstance(password, str) or not password:
            if role_config_present:
                raise ValueError(
                    f"Missing password for role {role!r}. Set account.password explicitly in governance config.")
            return ""

        quoted_username = self._quote(username, dialect)
        password_literal = self._string_literal(password)

        if dialect == "mysql":
            return f"CREATE USER IF NOT EXISTS {quoted_username}@'%' IDENTIFIED BY {password_literal};"
        if dialect in {"postgres", "postgresql"}:
            return f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {self._string_literal(username)}) THEN CREATE ROLE {quoted_username} LOGIN PASSWORD {password_literal}; END IF; END $$;"
        if dialect == "mssql":
            return f"IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = {self._string_literal(username)}) BEGIN CREATE LOGIN {quoted_username} WITH PASSWORD = {password_literal}; END;"
        return ""

    def _grant_statement(self, action: str, quoted_table: str, role: str, dialect: str) -> str:
        quoted_role = self._quote(role, dialect)
        privilege = self._privilege_for_action(action)
        return f"GRANT {privilege} ON {quoted_table} TO {quoted_role};"

    def _privilege_for_action(self, action: str) -> str:
        action = (action or "").lower()
        if action in {"select", "read"}:
            return "SELECT"
        if action in {"insert", "write", "create"}:
            return "INSERT"
        if action in {"update"}:
            return "UPDATE"
        if action in {"delete", "drop"}:
            return "DELETE"
        if action in {"alter"}:
            return "ALTER"
        if action in {"truncate"}:
            return "TRUNCATE"
        return action.upper()

    def _format_table(self, table: str, dialect: str) -> str:
        parts = table.split(".")
        return ".".join(self._quote(part, dialect) for part in parts)

    def _string_literal(self, value: str) -> str:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
