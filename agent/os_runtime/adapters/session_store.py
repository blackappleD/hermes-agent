"""SessionDB side-table repository for passive os_runtime events."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.domain import EventSource, OSRuntimeEventRef
from hermes_constants import get_hermes_home
from hermes_state import apply_wal_with_fallback


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS os_runtime_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    content_ref TEXT NOT NULL DEFAULT '',
    payload_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'recorded',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_os_runtime_events_recent
    ON os_runtime_events(timestamp DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_os_runtime_events_session
    ON os_runtime_events(session_id, timestamp DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_os_runtime_events_trace
    ON os_runtime_events(trace_id, timestamp DESC, created_at DESC);
"""


@dataclass
class OSRuntimeEvent:
    event_id: str
    event_type: str
    source: EventSource
    trace_id: str = ""
    session_id: str = ""
    timestamp: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    content_ref: str = ""
    payload_hash: str = ""
    status: str = "recorded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source.value,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "metadata": self.metadata,
            "content_ref": self.content_ref,
            "payload_hash": self.payload_hash,
            "status": self.status,
        }

    def to_ref(self) -> OSRuntimeEventRef:
        return OSRuntimeEventRef(
            event_id=self.event_id,
            source=self.source,
            trace_id=self.trace_id,
            session_id=self.session_id,
            timestamp=self.timestamp,
            summary=self.summary,
            metadata=dict(self.metadata),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OSRuntimeEvent":
        source = data.get("source", EventSource.SYSTEM.value)
        if not isinstance(source, EventSource):
            source = EventSource(str(source))
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        return cls(
            event_id=str(data.get("event_id") or f"osr_{uuid.uuid4().hex}"),
            event_type=str(data.get("event_type") or metadata.get("event_type") or "runtime_feedback"),
            source=source,
            trace_id=str(data.get("trace_id") or ""),
            session_id=str(data.get("session_id") or ""),
            timestamp=str(data.get("timestamp") or utc_now_iso()),
            summary=str(data.get("summary") or ""),
            metadata=metadata,
            content_ref=str(data.get("content_ref") or ""),
            payload_hash=str(data.get("payload_hash") or ""),
            status=str(data.get("status") or "recorded"),
        )


class OSRuntimeEventRepository:
    """Profile-scoped event store backed by the current Hermes ``state.db``."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        db_path: Path | None = None,
        enabled: bool = True,
    ):
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

    def append(self, event: OSRuntimeEvent | OSRuntimeEventRef | dict[str, Any]) -> OSRuntimeEvent | None:
        if not self.enabled:
            return None
        normalized = self._normalize(event)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO os_runtime_events (
                        event_id, event_type, source, trace_id, session_id,
                        timestamp, summary, metadata, content_ref, payload_hash,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.event_id,
                        normalized.event_type,
                        normalized.source.value,
                        normalized.trace_id,
                        normalized.session_id,
                        normalized.timestamp,
                        normalized.summary,
                        json.dumps(normalized.metadata, ensure_ascii=False, sort_keys=True),
                        normalized.content_ref,
                        normalized.payload_hash,
                        normalized.status,
                        utc_now_iso(),
                    ),
                )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        return self.get(normalized.event_id)

    def get(self, event_id: str) -> OSRuntimeEvent | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM os_runtime_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return _event_from_row(row) if row else None

    def list_recent(self, limit: int = 20) -> list[OSRuntimeEvent]:
        return self._list(
            "SELECT * FROM os_runtime_events ORDER BY timestamp DESC, created_at DESC LIMIT ?",
            (self._limit(limit),),
        )

    def list_by_session(self, session_id: str, limit: int = 20) -> list[OSRuntimeEvent]:
        return self._list(
            """
            SELECT * FROM os_runtime_events
            WHERE session_id = ?
            ORDER BY timestamp DESC, created_at DESC
            LIMIT ?
            """,
            (session_id, self._limit(limit)),
        )

    def list_by_trace(self, trace_id: str, limit: int = 20) -> list[OSRuntimeEvent]:
        return self._list(
            """
            SELECT * FROM os_runtime_events
            WHERE trace_id = ?
            ORDER BY timestamp DESC, created_at DESC
            LIMIT ?
            """,
            (trace_id, self._limit(limit)),
        )

    def _list(self, sql: str, params: tuple[Any, ...]) -> list[OSRuntimeEvent]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_event_from_row(row) for row in rows]

    def _normalize(self, event: OSRuntimeEvent | OSRuntimeEventRef | dict[str, Any]) -> OSRuntimeEvent:
        if isinstance(event, OSRuntimeEvent):
            data = event.to_dict()
        elif isinstance(event, OSRuntimeEventRef):
            data = event.to_dict()
        elif isinstance(event, dict):
            data = dict(event)
        else:
            raise TypeError("event must be OSRuntimeEvent, OSRuntimeEventRef, or dict")
        return OSRuntimeEvent.from_dict(data)

    @staticmethod
    def _limit(limit: int) -> int:
        return max(1, min(int(limit), 500))


def _event_from_row(row: sqlite3.Row) -> OSRuntimeEvent:
    try:
        metadata = json.loads(row["metadata"] or "{}")
    except json.JSONDecodeError:
        metadata = {"_decode_error": True}
    return OSRuntimeEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        source=EventSource(row["source"]),
        trace_id=row["trace_id"],
        session_id=row["session_id"],
        timestamp=row["timestamp"],
        summary=row["summary"],
        metadata=metadata if isinstance(metadata, dict) else {"value": metadata},
        content_ref=row["content_ref"],
        payload_hash=row["payload_hash"],
        status=row["status"],
    )


__all__ = ["OSRuntimeEvent", "OSRuntimeEventRepository"]
