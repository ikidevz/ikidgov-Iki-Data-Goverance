from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATHS = [
    Path(__file__).resolve().parent.parent / "config" / "governance.yaml",
    Path(__file__).resolve().parent.parent.parent /
    "config" / "governance.yaml",
]


def _normalize_role(role_name: str, role_config: Any, *, path: str = "roles") -> dict[str, Any]:
    if not isinstance(role_config, dict):
        raise ValueError(f"{path}.{role_name} must be a mapping")

    normalized: dict[str, Any] = {}
    description = role_config.get("description")
    if description is not None:
        normalized["description"] = description

    account_config = role_config.get("account", {})
    if not isinstance(account_config, dict):
        raise ValueError(f"{path}.{role_name}.account must be a mapping")

    account: dict[str, Any] = {}
    username = account_config.get("username")
    if username is not None:
        account["username"] = username
    password_env = account_config.get("password_env")
    if password_env is not None:
        account["password_env"] = password_env
    password = account_config.get("password")
    if password is not None:
        account["password"] = password
    elif password_env is not None:
        resolved_password = os.getenv(password_env)
        if resolved_password is not None:
            account["password"] = resolved_password
    if account:
        normalized["account"] = account

    permissions = role_config.get("permissions", [])
    if permissions is None:
        permissions = []
    if not isinstance(permissions, list):
        raise ValueError(f"{path}.{role_name}.permissions must be a list")
    normalized["permissions"] = permissions

    scope = role_config.get("scope")
    if scope is not None:
        normalized["scope"] = scope

    return normalized


def _normalize_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("governance config must be a mapping")

    normalized: dict[str, Any] = {}

    roles = data.get("roles", {})
    if roles is None:
        roles = {}
    if not isinstance(roles, dict):
        raise ValueError("roles must be a mapping")

    normalized_roles: dict[str, Any] = {}
    for role_name, role_config in roles.items():
        normalized_roles[role_name] = _normalize_role(
            role_name, role_config, path="roles")
    normalized["roles"] = normalized_roles

    connectors = data.get("connectors", {})
    if connectors is None:
        connectors = {}
    if not isinstance(connectors, dict):
        raise ValueError("connectors must be a mapping")

    normalized_connectors: dict[str, Any] = {}
    for connector_name, connector_config in connectors.items():
        if not isinstance(connector_config, dict):
            raise ValueError(f"connectors.{connector_name} must be a mapping")
        normalized_connectors[connector_name] = deepcopy(connector_config)
    normalized["connectors"] = normalized_connectors

    for top_level_key in ("sqlite", "postgresql", "mysql", "mssql"):
        if top_level_key in data:
            backend_config = data[top_level_key]
            if backend_config is None:
                backend_config = {}
            if not isinstance(backend_config, dict):
                raise ValueError(f"{top_level_key} must be a mapping")
            normalized[top_level_key] = deepcopy(backend_config)

    return normalized


def _candidate_paths() -> list[Path]:
    env_path = os.getenv("IKIGOV_CONFIG")
    environment = os.getenv("IKIGOV_ENV") or os.getenv("APP_ENV")
    paths: list[Path] = []

    if env_path:
        paths.append(Path(env_path).expanduser())

    if environment:
        env_file = Path.cwd() / f"governance.{environment}.yaml"
        if env_file.exists():
            paths.append(env_file)

    cwd_config = Path.cwd() / "governance.yaml"
    if cwd_config.exists():
        paths.append(cwd_config)

    if environment:
        repo_config = Path.cwd() / "config" / f"governance.{environment}.yaml"
        if repo_config.exists():
            paths.append(repo_config)

    paths.extend(DEFAULT_CONFIG_PATHS)
    return paths


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    if path is not None:
        candidates = [Path(path).expanduser()]
    else:
        candidates = _candidate_paths()

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else (Path.cwd() / candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            with resolved.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            if isinstance(data, dict):
                return _normalize_config(data)
    return {}


def get_roles_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    config = load_config(path)
    return config.get("roles", {})


def get_connectors_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    config = load_config(path)
    return config.get("connectors", {})


def get_accounts_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    config = load_config(path)
    roles = config.get("roles", {})
    account_config: dict[str, Any] = {}
    for role_name, role_config in roles.items():
        if isinstance(role_config, dict):
            account_block = role_config.get("account", {})
            if isinstance(account_block, dict) and account_block:
                account_config[role_name] = account_block
    return account_config
