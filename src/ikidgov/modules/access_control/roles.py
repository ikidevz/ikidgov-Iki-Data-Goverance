from ikidgov.config_loader import get_roles_config

_DEFAULT_ROLE_DEFINITIONS = {
    "admin": {
        "description": "Full control over registry, policies, and roles",
        "account": {
            "username": "admin_user",
        },
        "permissions": ["all"],
        "scope": None,
    },
    "data_owner": {
        "description": "Accountable for a dataset's classification and access grants",
        "account": {
            "username": "data_owner_user",
        },
        "permissions": [
            "select",
            "insert",
            "update",
            "delete",
            "create",
            "alter",
            "drop",
            "grant_access",
            "approve_classification",
        ],
        "scope": "owned_datasets_only",
    },
    "data_steward": {
        "description": "Classifies data and proposes policy changes within a domain",
        "account": {
            "username": "data_steward_user",
        },
        "permissions": [
            "select",
            "insert",
            "update",
            "delete",
            "create",
            "alter",
            "drop",
            "classify",
            "propose_policy",
        ],
        "scope": "domain_restricted",
    },
    "analyst": {
        "description": "Consumes data within policy limits",
        "account": {
            "username": "analyst_user",
        },
        "permissions": ["select"],
        "scope": "policy_restricted",
    },
    "auditor": {
        "description": "Reviews governance decisions, cannot alter state",
        "account": {
            "username": "auditor_user",
        },
        "permissions": ["read_audit_log"],
        "scope": "read_only",
    },
    "service_account": {
        "description": "Programmatic access via scoped API tokens",
        "account": {
            "username": "service_account_user",
        },
        "permissions": ["select"],
        "scope": "token_restricted",
    },
}


def _merge_role_definition(role_name: str, defaults: dict[str, object], config_roles: dict[str, object]) -> dict[str, object]:
    if role_name not in config_roles:
        return defaults

    role_config = config_roles[role_name]
    if not isinstance(role_config, dict):
        return defaults

    merged = dict(defaults)
    merged["account"] = dict(defaults.get("account", {}))
    if isinstance(role_config.get("account"), dict):
        merged["account"].update(role_config.get("account", {}))
    if "description" in role_config:
        merged["description"] = role_config["description"]
    if "permissions" in role_config:
        merged["permissions"] = list(role_config["permissions"])
    if "scope" in role_config:
        merged["scope"] = role_config["scope"]
    return merged


ROLE_DEFINITIONS = {}
config_roles = get_roles_config()
for role_name, defaults in _DEFAULT_ROLE_DEFINITIONS.items():
    ROLE_DEFINITIONS[role_name] = _merge_role_definition(
        role_name, defaults, config_roles)
