def create_role(name: str, description: str | None = None, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="create_role", name=name, description=description, backend=backend)


def get_role(item_id: int, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="get_role", item_id=item_id, backend=backend)


def list_roles(db_path: str | None = None, backend: str = "sqlite") -> list[dict]:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="list_roles", backend=backend)


def update_role(item_id: int, name: str | None = None, description: str | None = None, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="update_role", item_id=item_id, name=name, description=description, backend=backend)


def delete_role(item_id: int, db_path: str | None = None, backend: str = "sqlite") -> bool:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="delete_role", item_id=item_id, backend=backend)


def create_access(name: str, description: str | None = None, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="create_access", name=name, description=description, backend=backend)


def get_access(item_id: int, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="get_access", item_id=item_id, backend=backend)


def list_accesses(db_path: str | None = None, backend: str = "sqlite") -> list[dict]:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="list_accesses", backend=backend)


def update_access(item_id: int, name: str | None = None, description: str | None = None, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="update_access", item_id=item_id, name=name, description=description, backend=backend)


def delete_access(item_id: int, db_path: str | None = None, backend: str = "sqlite") -> bool:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="delete_access", item_id=item_id, backend=backend)


def create_permission(name: str, description: str | None = None, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="create_permission", name=name, description=description, backend=backend)


def get_permission(item_id: int, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="get_permission", item_id=item_id, backend=backend)


def list_permissions(db_path: str | None = None, backend: str = "sqlite") -> list[dict]:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="list_permissions", backend=backend)


def update_permission(item_id: int, name: str | None = None, description: str | None = None, db_path: str | None = None, backend: str = "sqlite") -> dict:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="update_permission", item_id=item_id, name=name, description=description, backend=backend)


def delete_permission(item_id: int, db_path: str | None = None, backend: str = "sqlite") -> bool:
    from .impl import AccessControlModule

    return AccessControlModule(db_path=db_path, backend=backend).run(action="delete_permission", item_id=item_id, backend=backend)
