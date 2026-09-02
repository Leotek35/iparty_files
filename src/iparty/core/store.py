"""Durable store for Living Passes (saved plans + their guest lists).

SQLite from the standard library — zero new dependencies, survives restarts,
and sits behind one small class so it can be swapped for Postgres without
touching the API. Every operation opens a short-lived connection under a
process lock, which is plenty for the first-100-users single instance and
keeps writes from interleaving under the threadpool FastAPI uses for sync
handlers.

Schema (created on first use):
  plans  : one row per saved, verified plan — request/plan/verification JSON
  guests : one row per guest response, keyed by an unguessable guest_key
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  plan_id            TEXT PRIMARY KEY,
  host_token         TEXT NOT NULL,
  created_at         TEXT NOT NULL,
  backend            TEXT NOT NULL,
  request_json       TEXT NOT NULL,
  plan_json          TEXT NOT NULL,
  verification_json  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guests (
  guest_key   TEXT PRIMARY KEY,
  plan_id     TEXT NOT NULL,
  name        TEXT NOT NULL,
  attending   INTEGER NOT NULL,
  party_size  INTEGER NOT NULL,
  dietary     TEXT NOT NULL DEFAULT '',
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS guests_by_plan ON guests(plan_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PlanStore:
    """Thin, lock-guarded SQLite gateway. The path is read lazily from
    settings so tests (and deploys) can point it anywhere after import."""

    def __init__(self, path: str | None = None) -> None:
        self._path_override = path
        self._initialised: set[str] = set()

    @property
    def path(self) -> Path:
        return Path(self._path_override or settings.PLANS_DB_PATH)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """One locked, auto-committed, always-closed transaction."""
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            conn = sqlite3.connect(str(p), timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                key = str(p.resolve())
                if key not in self._initialised:
                    conn.executescript(_SCHEMA)
                    conn.execute("PRAGMA journal_mode=WAL")
                    self._initialised.add(key)
                yield conn
                conn.commit()
            finally:
                conn.close()

    # ---------------------------------------------------------------- plans
    def save_plan(self, plan_id: str, host_token: str, backend: str,
                  request: dict, plan: dict, verification: dict) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO plans VALUES (?,?,?,?,?,?,?)",
                (plan_id, host_token, _now(), backend,
                 json.dumps(request, default=str), json.dumps(plan), json.dumps(verification)),
            )

    def get_plan(self, plan_id: str) -> dict | None:
        with self._tx() as c:
            row = c.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            return None
        return {
            "plan_id": row["plan_id"], "host_token": row["host_token"],
            "created_at": row["created_at"], "backend": row["backend"],
            "request": json.loads(row["request_json"]),
            "plan": json.loads(row["plan_json"]),
            "verification": json.loads(row["verification_json"]),
        }

    # --------------------------------------------------------------- guests
    def upsert_guest(self, guest_key: str, plan_id: str, name: str, attending: bool,
                     party_size: int, dietary: str) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO guests VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(guest_key) DO UPDATE SET name=excluded.name, "
                "attending=excluded.attending, party_size=excluded.party_size, "
                "dietary=excluded.dietary, updated_at=excluded.updated_at",
                (guest_key, plan_id, name, int(attending), party_size, dietary, _now()),
            )

    def get_guest(self, plan_id: str, guest_key: str) -> dict | None:
        with self._tx() as c:
            row = c.execute("SELECT * FROM guests WHERE plan_id=? AND guest_key=?",
                            (plan_id, guest_key)).fetchone()
        return dict(row) if row else None

    def guests_for(self, plan_id: str) -> list[dict]:
        with self._tx() as c:
            rows = c.execute("SELECT * FROM guests WHERE plan_id=? ORDER BY updated_at, guest_key",
                             (plan_id,)).fetchall()
        return [dict(r) for r in rows]

    def count_guests(self, plan_id: str) -> int:
        with self._tx() as c:
            return int(c.execute("SELECT COUNT(*) FROM guests WHERE plan_id=?",
                                 (plan_id,)).fetchone()[0])

    # ---------------------------------------------------------------- tests
    def reset(self) -> None:
        if not self.path.exists():
            return
        with self._tx() as c:
            c.execute("DELETE FROM guests")
            c.execute("DELETE FROM plans")


store = PlanStore()
