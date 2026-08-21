"""SQLite connection layer (Demo stand-in for ClickHouse + Postgres, see plan.md §1)."""
import os
import sqlite3
import threading
from pathlib import Path

_SCHEMA = Path(__file__).parent / "schema.sql"
_local = threading.local()


def db_path() -> str:
    return os.environ.get("XUNJI_DB", str(Path("data") / "xunji.db"))


def connect(path: str | None = None) -> sqlite3.Connection:
    """New connection with dict rows and FK/check enforcement."""
    target = path or db_path()
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def get_conn() -> sqlite3.Connection:
    """Per-thread singleton for app runtime; tests use connect() directly."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        init_db(conn)
        _local.conn = conn
    return conn


def reset_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
