import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("CAREER_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "career.db"
SCHEMA = Path(__file__).with_name("schema.sql")

DEFAULT_TERMS = [
    "Modern Workplace", "TechOps", "IT Operations Manager", "IT Service Manager",
    "Infrastructure Engineer", "Platform Engineer", "IAM Engineer", "Identity Engineer",
    "EUC Lead", "Endpoint Engineer", "IT Manager", "Head of IT",
]
DEFAULT_FILTERS = {
    "salary_floor": 74000,
    "locations": ["Remote", "Brighton", "Eastbourne", "Lewes", "Crawley", "Gatwick", "London"],
    "exclude_terms": ["service desk analyst", "1st line", "first line", "DV cleared", "SC cleared"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init() -> None:
    con = connect()
    with con:
        con.executescript(SCHEMA.read_text())
        _migrate(con)
        con.execute(
            "INSERT OR IGNORE INTO profile (id, markdown, search_terms, filters, threshold, updated_at) "
            "VALUES (1, '', ?, ?, 75, ?)",
            (json.dumps(DEFAULT_TERMS), json.dumps(DEFAULT_FILTERS), now()),
        )
    con.close()


def _migrate(con: sqlite3.Connection) -> None:
    """Additive migrations: add columns schema.sql has that the live DB lacks.
    New columns go in BOTH schema.sql and this dict."""
    wanted = {
        "roles": {"salary_text": "TEXT", "remote_flag": "INTEGER NOT NULL DEFAULT 0",
                  "filtered": "INTEGER NOT NULL DEFAULT 0", "filter_reason": "TEXT",
                  "desc_quality": "TEXT", "desc_reason": "TEXT", "watch": "INTEGER NOT NULL DEFAULT 0", "cluster_id": "INTEGER"},
        "sources": {"last_error": "TEXT"},
        "scores": {"track": "TEXT"},
        "status": {"reason": "TEXT"},
        "profile": {"cv_engineer": "TEXT NOT NULL DEFAULT ''", "cv_management": "TEXT NOT NULL DEFAULT ''",
                    "watchlist": "TEXT NOT NULL DEFAULT '[]'"},
    }
    for table, cols in wanted.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
