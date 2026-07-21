import csv
from pathlib import Path

from ikidgov.config_loader import get_connectors_config
from ikidgov.core.connector_base import Connector


class CSVConnector(Connector):
    source = "csv"

    def discover(self) -> dict:
        path = Path(self.path)
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            return {"source": self.source, "name": path.stem, "columns": []}
        connector_config = get_connectors_config().get("csv", {})
        default_type = connector_config.get("default_type", "string")
        columns = [{"name": name, "dtype": default_type}
                   for name in rows[0].keys()]
        return {"source": self.source, "name": path.stem, "columns": columns}
