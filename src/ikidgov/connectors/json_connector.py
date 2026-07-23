import json
from pathlib import Path

from ikidgov.config_loader import get_connectors_config
from ikidgov.core.connector_base import Connector


class JSONConnector(Connector):
    source = "json"

    def discover(self) -> dict:
        path = Path(self.path)
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            rows = payload
        else:
            rows = [payload]
        if not rows:
            return {"source": self.source, "name": path.stem, "columns": []}
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError(
                "JSON payload must be an object or a list of objects")
        connector_config = get_connectors_config().get("json", {})
        default_type = connector_config.get("default_type", "string")
        if not isinstance(rows[0], dict):
            raise ValueError(
                "JSON payload must be an object or a list of objects")
        columns = [{"name": name, "dtype": default_type}
                   for name in rows[0].keys()]
        return {"source": self.source, "name": path.stem, "columns": columns}
