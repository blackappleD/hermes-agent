"""Profile-scoped queue storage for autonomous os_runtime wake processing."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.autonomous_state import AutonomousRuntimeState, AutonomousWakeRecord
from hermes_constants import get_hermes_home
from hermes_state import apply_wal_with_fallback


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS os_runtime_autonomous_state (
    session_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL DEFAULT '',
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS os_runtime_autonomous_wakes (
    wake_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    profile_id TEXT NOT NULL DEFAULT '',
    wake_reason TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_os_runtime_autonomous_wakes_session
    ON os_runtime_autonomous_wakes(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS os_runtime_autonomous_inbox (
    item_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT '',
    profile_id TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    sequence_key TEXT NOT NULL DEFAULT '',
    wake_reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    payload_json TEXT NOT NULL DEFAULT '{}',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_os_runtime_autonomous_inbox_event
    ON os_runtime_autonomous_inbox(session_id, event_id)
    WHERE event_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_os_runtime_autonomous_inbox_sequence
    ON os_runtime_autonomous_inbox(session_id, sequence_key)
    WHERE sequence_key <> '';
CREATE INDEX IF NOT EXISTS idx_os_runtime_autonomous_inbox_pending
    ON os_runtime_autonomous_inbox(session_id, status, created_at);
"""


@dataclass
class AutonomousInboxRecord:
    item_id: str
    session_id: str = ""
    profile_id: str = ""
    event_id: str = ""
    sequence_key: str = ""
    wake_reason: str = ""
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "event_id": self.event_id,
            "sequence_key": self.sequence_key,
            "wake_reason": self.wake_reason,
            "status": self.status,
            "payload": self.payload,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RuntimeQueueRepository:
    """SQLite adapter for autonomous state, wakes, and inbox records."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        db_path: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.root = Path(root) if root is not None else get_hermes_home()
        self.db_path = Path(db_path) if db_path is not None else self.root / "state.db"
        self.enabled = enabled
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=1.0,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        apply_wal_with_fallback(self._conn, db_label=str(self.db_path))
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def load_state(self, session_id: str) -> AutonomousRuntimeState | None:
        if not self.enabled or not session_id:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT state_json FROM os_runtime_autonomous_state WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return AutonomousRuntimeState.from_json(row["state_json"])

    def save_state(self, state: AutonomousRuntimeState) -> AutonomousRuntimeState:
        state.updated_at = utc_now_iso()
        if not self.enabled:
            return state
        session_id = state.session_id or state.loop_id
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO os_runtime_autonomous_state (
                    session_id, profile_id, state_json, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    state.profile_id,
                    state.to_json(),
                    state.updated_at,
                ),
            )
        return state

    def append_wake(self, record: AutonomousWakeRecord) -> AutonomousWakeRecord:
        if not self.enabled:
            return record
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR REPLACE INTO os_runtime_autonomous_wakes (
                    wake_id, session_id, profile_id, wake_reason, event_id,
                    status, record_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.wake_id,
                    record.session_id,
                    record.profile_id,
                    record.wake_reason,
                    record.event_id,
                    record.status,
                    json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True),
                    record.started_at or utc_now_iso(),
                ),
            )
        return record

    def list_wakes(self, session_id: str = "", *, limit: int = 20) -> list[AutonomousWakeRecord]:
        sql = "SELECT record_json FROM os_runtime_autonomous_wakes"
        params: list[Any] = []
        if session_id:
            sql += " WHERE session_id = ?"
            params.append(session_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(_limit(limit))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        records: list[AutonomousWakeRecord] = []
        for row in rows:
            try:
                records.append(AutonomousWakeRecord.from_dict(json.loads(row["record_json"])))
            except Exception:
                continue
        return records

    def enqueue_inbox(
        self,
        *,
        session_id: str,
        profile_id: str = "",
        event_id: str = "",
        sequence_key: str = "",
        wake_reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> tuple[AutonomousInboxRecord, bool]:
        record = AutonomousInboxRecord(
            item_id=f"ainbox-{uuid.uuid4().hex}",
            session_id=session_id,
            profile_id=profile_id,
            event_id=event_id,
            sequence_key=sequence_key,
            wake_reason=wake_reason,
            payload=dict(payload or {}),
        )
        if not self.enabled:
            return record, True
        now = utc_now_iso()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO os_runtime_autonomous_inbox (
                    item_id, session_id, profile_id, event_id, sequence_key,
                    wake_reason, status, payload_json, attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.item_id,
                    session_id,
                    profile_id,
                    event_id,
                    sequence_key,
                    wake_reason,
                    record.status,
                    json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                    record.attempts,
                    now,
                    now,
                ),
            )
            inserted = cursor.rowcount > 0
            row = None
            if event_id:
                row = self._conn.execute(
                    """
                    SELECT * FROM os_runtime_autonomous_inbox
                    WHERE session_id = ? AND event_id = ?
                    """,
                    (session_id, event_id),
                ).fetchone()
            if row is None and sequence_key:
                row = self._conn.execute(
                    """
                    SELECT * FROM os_runtime_autonomous_inbox
                    WHERE session_id = ? AND sequence_key = ?
                    """,
                    (session_id, sequence_key),
                ).fetchone()
            if row is None:
                row = self._conn.execute(
                    "SELECT * FROM os_runtime_autonomous_inbox WHERE item_id = ?",
                    (record.item_id,),
                ).fetchone()
        return _inbox_from_row(row) if row else record, inserted

    def claim_next(self, session_id: str) -> AutonomousInboxRecord | None:
        if not self.enabled:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM os_runtime_autonomous_inbox
                WHERE session_id = ? AND status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            now = utc_now_iso()
            self._conn.execute(
                """
                UPDATE os_runtime_autonomous_inbox
                SET status = 'claimed', attempts = attempts + 1, updated_at = ?
                WHERE item_id = ?
                """,
                (now, row["item_id"]),
            )
            claimed = self._conn.execute(
                "SELECT * FROM os_runtime_autonomous_inbox WHERE item_id = ?",
                (row["item_id"],),
            ).fetchone()
        return _inbox_from_row(claimed) if claimed else None

    def update_inbox_status(
        self,
        item_id: str,
        status: str,
        *,
        error: str = "",
    ) -> AutonomousInboxRecord | None:
        if not self.enabled or not item_id:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM os_runtime_autonomous_inbox WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            payload = _json_dict(row["payload_json"]) if row else {}
            if error:
                payload["error"] = error
            self._conn.execute(
                """
                UPDATE os_runtime_autonomous_inbox
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE item_id = ?
                """,
                (
                    status,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    utc_now_iso(),
                    item_id,
                ),
            )
            next_row = self._conn.execute(
                "SELECT * FROM os_runtime_autonomous_inbox WHERE item_id = ?",
                (item_id,),
            ).fetchone()
        return _inbox_from_row(next_row) if next_row else None

    def list_inbox(
        self,
        session_id: str = "",
        *,
        status: str = "",
        limit: int = 20,
    ) -> list[AutonomousInboxRecord]:
        sql = "SELECT * FROM os_runtime_autonomous_inbox"
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(_limit(limit))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [_inbox_from_row(row) for row in rows]


def _inbox_from_row(row: sqlite3.Row) -> AutonomousInboxRecord:
    return AutonomousInboxRecord(
        item_id=row["item_id"],
        session_id=row["session_id"],
        profile_id=row["profile_id"],
        event_id=row["event_id"],
        sequence_key=row["sequence_key"],
        wake_reason=row["wake_reason"],
        status=row["status"],
        payload=_json_dict(row["payload_json"]),
        attempts=int(row["attempts"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _json_dict(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_decode_error": True}
    return data if isinstance(data, dict) else {"value": data}


def _limit(value: int) -> int:
    return max(1, min(int(value), 500))


__all__ = [
    "AutonomousInboxRecord",
    "RuntimeQueueRepository",
]
