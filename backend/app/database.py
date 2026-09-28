import sqlite3
from pathlib import Path

from .config import db_path

SCHEMA_VERSION = "0002_foundation"


def connect(path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(path or db_path(), timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def database_ready() -> bool:
    path = db_path()
    if not path.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1) as connection:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            return bool(row and row[0] == SCHEMA_VERSION)
    except sqlite3.Error:
        return False
