import argparse
import os

from ikidgov.cli.base_command import BaseCommand
from ikidgov.config_loader import load_config
from ikidgov.connectors.csv_connector import CSVConnector
from ikidgov.connectors.json_connector import JSONConnector
from ikidgov.connectors.sql_connector import SQLConnector
from ikidgov.modules.metadata_registry import interface as registry


class ScanCommand(BaseCommand):
    name = "scan"

    def _handle(self, args: argparse.Namespace) -> dict:
        connector = self._get_connector(args)
        discovered = connector.discover()
        dataset = registry.register_dataset(
            source=discovered["source"], name=discovered["name"], owner=args.owner)
        for column in discovered["columns"]:
            registry.register_column(
                dataset_id=dataset["id"], name=column["name"], dtype=column.get("dtype"))
        return {"dataset": dataset, "columns": discovered["columns"]}

    def _get_connector(self, args: argparse.Namespace):
        if args.type == "csv":
            return CSVConnector(args.path)
        if args.type == "json":
            return JSONConnector(args.path)
        if args.type == "sql":
            config_path = getattr(args, "config", None)
            config = load_config(config_path)
            backend = getattr(args, "backend", None) or os.getenv(
                "IKIGOV_SQL_BACKEND") or "sqlite"
            return SQLConnector(args.path, args.table, backend=backend, config=config)
        raise ValueError(args.type)
