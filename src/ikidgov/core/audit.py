from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None


def _audit_log_path() -> Path:
    configured = os.getenv("IKIGOV_AUDIT_LOG")
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "audit.log"


def emit_audit_event(event: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    payload.update(details)

    log_path = _audit_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _rotate_if_needed(log_path)
        if fcntl is not None:
            with log_path.open("a", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    handle.seek(0, os.SEEK_END)
                    handle.write(json.dumps(payload, sort_keys=True))
                    handle.write("\n")
                    handle.flush()
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        else:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
                handle.write("\n")
    except Exception:
        pass

    return payload


def _rotate_if_needed(path: Path, *, max_bytes: int = 10_485_760) -> None:
    if not path.exists():
        return
    try:
        if path.stat().st_size < max_bytes:
            return
    except OSError:
        return

    rotated = path.with_suffix(path.suffix + ".1")
    if rotated.exists():
        rotated.unlink()
    path.rename(rotated)
