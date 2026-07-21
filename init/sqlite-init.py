"""Generates a seeded SQLite file for testing the SQLite dialect of the
multi-dialect SQL connector. SQLite is serverless, so there's no long-running
container for it -- this script just runs once and exits (see the
`sqlite-init` service in docker-compose.yml), leaving the .db file behind on
a shared volume for the toolbox container (and your host, via ./data/sqlite)
to use directly with `ikigov scan --dialect sqlite`.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("/data/registry.db")

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
try:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name   TEXT NOT NULL,
            email       TEXT NOT NULL,
            ssn         TEXT,
            signup_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    existing = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT INTO customers (full_name, email, ssn) VALUES (?, ?, ?)",
            [
                ("Jane Doe", "jane.doe@example.com", "123-45-6789"),
                ("John Smith", "john.smith@example.com", "987-65-4321"),
                ("Maria Cruz", "maria.cruz@example.com", "456-78-9123"),
            ],
        )
    conn.commit()
finally:
    conn.close()

print(f"SQLite test database ready at {DB_PATH}")
