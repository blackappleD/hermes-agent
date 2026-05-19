"""SQLite-backed dynamic state for Linz World runtime records."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import DispatchStatus, EventDispatchRecord, to_plain, utc_now_iso


_SCHEMA_LOCK = threading.RLock()
_SCHEMA_READY: set[str] = set()

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS linz_world_runtime_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS linz_world_event_dispatch (
    event_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_summary TEXT NOT NULL DEFAULT '',
    audit_ref TEXT NOT NULL DEFAULT '',
    os_id TEXT NOT NULL DEFAULT '',
    soul_id TEXT NOT NULL DEFAULT '',
    nats_sequence TEXT NOT NULL DEFAULT '',
    sequence_key TEXT UNIQUE,
    source_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL,
    dispatch_status TEXT NOT NULL DEFAULT 'persisted',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    last_delivery_at TEXT NOT NULL DEFAULT '',
    requires_manual_handling INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_linz_world_event_dispatch_recent
    ON linz_world_event_dispatch(last_delivery_at DESC, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_linz_world_event_dispatch_status
    ON linz_world_event_dispatch(dispatch_status);
CREATE INDEX IF NOT EXISTS idx_linz_world_event_dispatch_sequence
    ON linz_world_event_dispatch(sequence_key);

CREATE TABLE IF NOT EXISTS linz_world_runtime_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    migration_key TEXT,
    UNIQUE(bucket, migration_key)
);

CREATE INDEX IF NOT EXISTS idx_linz_world_runtime_items_bucket
    ON linz_world_runtime_items(bucket, id);
"""


def _json_dumps(value: Any) -> str:
    return json.dumps(to_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _enable_wal(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE")


class LinzRuntimeStore:
    """Profile-scoped SQLite store for Linz World dynamic state."""

    def __init__(self, profile_root: Path):
        self.profile_root = Path(profile_root)
        self.db_path = self.profile_root / "state.db"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        key = str(self.db_path.resolve())
        with _SCHEMA_LOCK:
            if key not in _SCHEMA_READY:
                _enable_wal(conn)
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
                _SCHEMA_READY.add(key)
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def get_state(self, key: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM linz_world_runtime_state WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return {}
        data = _json_loads(row["value_json"], {})
        return data if isinstance(data, dict) else {}

    def set_state(self, key: str, value: Any) -> None:
        payload = _json_dumps(value)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO linz_world_runtime_state(key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, payload, utc_now_iso()),
                )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def persist_event(self, record: EventDispatchRecord) -> tuple[EventDispatchRecord, bool]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._select_event_row(conn, event_id=record.event_id)
                if existing is None and record.sequence_key:
                    existing = self._select_event_row(conn, sequence_key=record.sequence_key)
                if existing is not None:
                    conn.commit()
                    return self._record_from_row(existing), False
                self._insert_event(conn, record)
                conn.commit()
                return record, True
            except sqlite3.IntegrityError:
                conn.rollback()
                with self._connection() as read_conn:
                    existing = self._select_event_row(read_conn, event_id=record.event_id)
                    if existing is None and record.sequence_key:
                        existing = self._select_event_row(read_conn, sequence_key=record.sequence_key)
                    if existing is not None:
                        return self._record_from_row(existing), False
                raise
            except BaseException:
                conn.rollback()
                raise

    def upsert_legacy_event(self, record: EventDispatchRecord) -> None:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._select_event_row(conn, event_id=record.event_id)
                if existing is None:
                    self._insert_event(conn, record)
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
            except BaseException:
                conn.rollback()
                raise

    def mark_processing(self, event_id: str) -> EventDispatchRecord | None:
        return self._update_event_status(
            event_id,
            DispatchStatus.PROCESSING,
            last_delivery_at=utc_now_iso(),
        )

    def mark_processing_failure(
        self,
        event_id: str,
        error: str,
        *,
        retry_limit: int = 3,
    ) -> EventDispatchRecord | None:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_event_row(conn, event_id=event_id)
                if row is None:
                    conn.rollback()
                    return None
                record = self._record_from_row(row)
                record.attempt_count += 1
                record.last_error = error
                record.last_delivery_at = utc_now_iso()
                if record.attempt_count >= retry_limit:
                    record.dispatch_status = DispatchStatus.FAILED
                    record.requires_manual_handling = True
                else:
                    record.dispatch_status = DispatchStatus.QUEUED
                self._replace_event(conn, record)
                conn.commit()
                return record
            except BaseException:
                conn.rollback()
                raise

    def mark_handled(self, event_id: str) -> EventDispatchRecord | None:
        return self._update_event_status(
            event_id,
            DispatchStatus.HANDLED,
            last_error="",
            last_delivery_at=utc_now_iso(),
        )

    def recent_events(self, *, limit: int = 20, status: str | None = None) -> list[EventDispatchRecord]:
        limit = max(1, min(int(limit or 20), 100))
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE dispatch_status = ?"
            params.append(status)
        params.append(limit)
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM linz_world_event_dispatch
                {where}
                ORDER BY COALESCE(NULLIF(last_delivery_at, ''), occurred_at) DESC, event_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def append_item(self, bucket: str, value: Any, *, migration_key: str | None = None) -> None:
        payload = _json_dumps(value)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if migration_key:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO linz_world_runtime_items(
                            bucket, payload_json, created_at, migration_key
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (bucket, payload, utc_now_iso(), migration_key),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO linz_world_runtime_items(bucket, payload_json, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (bucket, payload, utc_now_iso()),
                    )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def list_items(self, bucket: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT payload_json FROM linz_world_runtime_items
            WHERE bucket = ?
            ORDER BY id ASC
        """
        params: list[Any] = [bucket]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            data = _json_loads(row["payload_json"], {})
            if isinstance(data, dict):
                items.append(data)
        return items

    def _update_event_status(
        self,
        event_id: str,
        status: DispatchStatus,
        *,
        last_error: str | None = None,
        last_delivery_at: str | None = None,
    ) -> EventDispatchRecord | None:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_event_row(conn, event_id=event_id)
                if row is None:
                    conn.rollback()
                    return None
                record = self._record_from_row(row)
                record.dispatch_status = status
                if last_error is not None:
                    record.last_error = last_error
                if last_delivery_at is not None:
                    record.last_delivery_at = last_delivery_at
                self._replace_event(conn, record)
                conn.commit()
                return record
            except BaseException:
                conn.rollback()
                raise

    def _select_event_row(
        self,
        conn: sqlite3.Connection,
        *,
        event_id: str | None = None,
        sequence_key: str | None = None,
    ) -> sqlite3.Row | None:
        if event_id:
            row = conn.execute(
                "SELECT * FROM linz_world_event_dispatch WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is not None:
                return row
        if sequence_key:
            return conn.execute(
                "SELECT * FROM linz_world_event_dispatch WHERE sequence_key = ?",
                (sequence_key,),
            ).fetchone()
        return None

    def _insert_event(self, conn: sqlite3.Connection, record: EventDispatchRecord) -> None:
        conn.execute(
            """
            INSERT INTO linz_world_event_dispatch (
                event_id, subject, event_type, payload_summary, audit_ref,
                os_id, soul_id, nats_sequence, sequence_key, source_json,
                occurred_at, dispatch_status, attempt_count, last_error,
                last_delivery_at, requires_manual_handling
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._event_params(record),
        )

    def _replace_event(self, conn: sqlite3.Connection, record: EventDispatchRecord) -> None:
        conn.execute(
            """
            UPDATE linz_world_event_dispatch SET
                subject = ?,
                event_type = ?,
                payload_summary = ?,
                audit_ref = ?,
                os_id = ?,
                soul_id = ?,
                nats_sequence = ?,
                sequence_key = ?,
                source_json = ?,
                occurred_at = ?,
                dispatch_status = ?,
                attempt_count = ?,
                last_error = ?,
                last_delivery_at = ?,
                requires_manual_handling = ?
            WHERE event_id = ?
            """,
            (
                record.subject,
                record.event_type,
                record.payload_summary,
                record.audit_ref,
                record.os_id,
                record.soul_id,
                record.nats_sequence,
                record.sequence_key or None,
                _json_dumps(record.source or {}),
                record.occurred_at,
                record.dispatch_status.value,
                int(record.attempt_count or 0),
                record.last_error,
                record.last_delivery_at,
                int(bool(record.requires_manual_handling)),
                record.event_id,
            ),
        )

    def _event_params(self, record: EventDispatchRecord) -> tuple[Any, ...]:
        return (
            record.event_id,
            record.subject,
            record.event_type,
            record.payload_summary,
            record.audit_ref,
            record.os_id,
            record.soul_id,
            record.nats_sequence,
            record.sequence_key or None,
            _json_dumps(record.source or {}),
            record.occurred_at,
            record.dispatch_status.value,
            int(record.attempt_count or 0),
            record.last_error,
            record.last_delivery_at,
            int(bool(record.requires_manual_handling)),
        )

    def _record_from_row(self, row: sqlite3.Row) -> EventDispatchRecord:
        source = _json_loads(row["source_json"], {})
        return EventDispatchRecord(
            event_id=str(row["event_id"] or ""),
            subject=str(row["subject"] or ""),
            event_type=str(row["event_type"] or ""),
            payload_summary=str(row["payload_summary"] or ""),
            audit_ref=str(row["audit_ref"] or ""),
            os_id=str(row["os_id"] or ""),
            soul_id=str(row["soul_id"] or ""),
            nats_sequence=str(row["nats_sequence"] or ""),
            dispatch_status=DispatchStatus(row["dispatch_status"] or DispatchStatus.PERSISTED.value),
            attempt_count=int(row["attempt_count"] or 0),
            last_error=str(row["last_error"] or ""),
            last_delivery_at=str(row["last_delivery_at"] or ""),
            requires_manual_handling=bool(row["requires_manual_handling"]),
            sequence_key=str(row["sequence_key"] or ""),
            source=source if isinstance(source, dict) else {},
            occurred_at=str(row["occurred_at"] or utc_now_iso()),
        )
