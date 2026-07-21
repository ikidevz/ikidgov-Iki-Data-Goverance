from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")

    return payload
