"""SQLite-backed response cache and credit ledger.

Every paid Sectors call is written to the ledger with its credit cost, so the
remaining budget is always known locally, even if the API doesn't report it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key         TEXT PRIMARY KEY,
    path        TEXT NOT NULL,
    params      TEXT NOT NULL,
    status      INTEGER NOT NULL,
    body        TEXT NOT NULL,
    fetched_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_prefs (
    chat_key    TEXT PRIMARY KEY,
    lang        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_events (
    chat_key    TEXT NOT NULL,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS bot_events_chat_ts ON bot_events (chat_key, ts);
CREATE TABLE IF NOT EXISTS bot_seen (
    key         TEXT PRIMARY KEY,
    ts          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    path        TEXT NOT NULL,
    params      TEXT NOT NULL,
    status      INTEGER NOT NULL,
    credits     INTEGER NOT NULL
);
"""


def cache_key(path: str, params: dict[str, Any] | None) -> str:
    canon = json.dumps({"p": path, "q": params or {}}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # The API serves requests from a thread pool; one connection guarded by a lock.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.RLock()
        self.conn.executescript(SCHEMA)

    # --- cache -------------------------------------------------------------
    def get(self, path: str, params: dict | None, max_age_s: float) -> tuple[int, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT status, body, fetched_at FROM responses WHERE key = ?",
                (cache_key(path, params),),
            ).fetchone()
            if row is None:
                return None
            status, body, fetched_at = row
            if time.time() - fetched_at > max_age_s:
                return None
            return status, json.loads(body)

    def put(self, path: str, params: dict | None, status: int, body: Any) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?, ?)",
                (
                    cache_key(path, params),
                    path,
                    json.dumps(params or {}, sort_keys=True),
                    status,
                    json.dumps(body),
                    time.time(),
                ),
            )
            self.conn.commit()

    # --- ledger ------------------------------------------------------------
    def record_spend(self, path: str, params: dict | None, status: int, credits: int) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO ledger (ts, path, params, status, credits) VALUES (?, ?, ?, ?, ?)",
                (time.time(), path, json.dumps(params or {}, sort_keys=True), status, credits),
            )
            self.conn.commit()

    def credits_spent(self) -> int:
        with self.lock:
            (total,) = self.conn.execute("SELECT COALESCE(SUM(credits), 0) FROM ledger").fetchone()
            return int(total)

    def spend_by_path(self) -> list[tuple[str, int, int]]:
        """(path, calls, credits) grouped by endpoint path."""
        with self.lock:
            return self.conn.execute(
                "SELECT path, COUNT(*), SUM(credits) FROM ledger GROUP BY path ORDER BY 3 DESC"
            ).fetchall()

    # --- chat bots -----------------------------------------------------------
    def bot_lang(self, chat_key: str) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT lang FROM bot_prefs WHERE chat_key = ?", (chat_key,)).fetchone()
            return row[0] if row else None

    def set_bot_lang(self, chat_key: str, lang: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO bot_prefs VALUES (?, ?)", (chat_key, lang))
            self.conn.commit()

    def bot_checks_since(self, chat_key: str, since: float) -> int:
        with self.lock:
            (n,) = self.conn.execute(
                "SELECT COUNT(*) FROM bot_events WHERE chat_key = ? AND ts >= ?", (chat_key, since)
            ).fetchone()
            return int(n)

    def record_bot_check(self, chat_key: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO bot_events VALUES (?, ?)", (chat_key, time.time()))
            self.conn.commit()

    def first_time_seen(self, key: str) -> bool:
        """True once per key: de-duplicates webhook retries and re-delivered updates."""
        with self.lock:
            cur = self.conn.execute("INSERT OR IGNORE INTO bot_seen VALUES (?, ?)", (key, time.time()))
            self.conn.commit()
            return cur.rowcount == 1
