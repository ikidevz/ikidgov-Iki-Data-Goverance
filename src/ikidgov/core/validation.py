import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(identifier: str, kind: str = "identifier") -> None:
    if not isinstance(identifier, str) or not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Invalid {kind}: {identifier!r}")


def validate_table_name(table: str | None) -> str:
    if not isinstance(table, str) or not table:
        raise ValueError("Table name is required for SQL discovery")
    parts = table.split(".")
    if any(not part for part in parts):
        raise ValueError(f"Invalid table: {table!r}")
    for part in parts:
        validate_identifier(part, kind="table")
    return table
