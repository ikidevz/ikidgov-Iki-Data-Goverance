from ikidgov.core.decision import Decision


def check(actor_role: str, action_type: str, dataset_id: int | None = None, column: str | None = None, role_permissions: set[str] | list[str] | None = None) -> Decision:
    from .impl import PolicyEngine

    return PolicyEngine().check(actor_role=actor_role, action_type=action_type, dataset_id=dataset_id, column=column, role_permissions=role_permissions)


def compile(policy_name: str, table: str, dialect: str = "generic", config_path: str | None = None, config: dict | None = None) -> dict:
    from .impl import PolicyEngine

    return PolicyEngine().compile(policy_name=policy_name, table=table, dialect=dialect, config_path=config_path, config=config)
