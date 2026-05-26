import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.environ.get(
        "APP_DB_PATH",
        Path(__file__).parent.parent / "data" / "games.db",
    )
)


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
