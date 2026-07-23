from abc import ABC, abstractmethod


class Connector(ABC):
    """Base contract for schema-discovery connectors.

    Only SQL connectors may accept a table name, which is required for SQL discovery.
    CSV and JSON connectors should not receive a `table` argument.
    """

    source: str = ""

    def __init__(self, path: str, table: str | None = None):
        self.path = path
        self.table = table
        self._validate_table_arg(table)

    def _validate_table_arg(self, table: str | None) -> None:
        if table is not None and not isinstance(table, str):
            raise ValueError("table must be a string when provided")
        if table is None:
            return
        # Only SQLConnector supports a table name; CSV/JSON ignore table.
        from ikidgov.connectors.sql_connector import SQLConnector

        if not isinstance(self, SQLConnector):
            raise ValueError(
                "Table argument is only supported by SQLConnector")

    @abstractmethod
    def discover(self) -> dict:
        raise NotImplementedError
