"""Local ledger for gateway inbound events and Hermes MessageEvent projections.

The dashboard uses this profile-scoped SQLite store to inspect how an inbound
platform/world event was consumed and how it mapped to the normalized
``MessageEvent`` object that Hermes handles internally.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from hermes_constants import get_hermes_home


CONSUME_STATUSES = {
    "received",
    "queued",
    "processing",
    "handled",
    "failed",
    "duplicate",
    "ignored",
    "unauthorized",
}
PROJECTION_STATUSES = {"pending", "projected", "failed"}
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


@dataclass
class GatewayInboundEventRecord:
    record_id: str
    event_id: str | None
    source_category: str
    platform: str | None
    source_summary: str
    subject: str | None
    event_type: str | None
    occurred_at: str | None
    consumed_at: str
    updated_at: str
    sequence_key: str | None
    nats_sequence: str | None
    payload_summary: str
    raw_payload_json: str | None
    raw_payload_available: bool
    raw_payload_error: str | None
    consume_status: str
    projection_status: str
    dedupe_status: str | None
    duplicate_of_record_id: str | None
    attempt_count: int
    last_error: str | None

    def to_dict(self, *, include_raw_payload: bool = False) -> dict[str, Any]:
        data = asdict(self)
        raw_json = data.pop("raw_payload_json", None)
        data["raw_payload_available"] = bool(data["raw_payload_available"])
        if include_raw_payload and raw_json is not None:
            try:
                data["raw_payload"] = json.loads(raw_json)
            except json.JSONDecodeError:
                data["raw_payload"] = None
                data["raw_payload_available"] = False
                data["raw_payload_error"] = data.get("raw_payload_error") or "Stored payload JSON is invalid"
        return data


@dataclass
class HermesMessageEventProjection:
    record_id: str
    message_event_id: str | None
    message_type: str | None
    text_summary: str
    source_snapshot_json: str | None
    raw_message_summary: str
    media_count: int
    session_id: str | None
    session_key: str | None
    session_message_ref: str | None
    projected_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("record_id", None)
        source_json = data.pop("source_snapshot_json", None)
        if source_json:
            try:
                data["source_snapshot"] = json.loads(source_json)
            except json.JSONDecodeError:
                data["source_snapshot"] = {}
        else:
            data["source_snapshot"] = {}
        return data


@dataclass
class EventProcessingTransition:
    transition_id: int
    record_id: str
    from_status: str | None
    to_status: str
    at: str
    reason: str | None
    error: str | None
    metadata_json: str | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        metadata_json = data.pop("metadata_json", None)
        if metadata_json:
            try:
                data["metadata"] = json.loads(metadata_json)
            except json.JSONDecodeError:
                data["metadata"] = {}
        else:
            data["metadata"] = {}
        return data


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)


def _truncate(value: Any, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_dumps_display(value: Any, limit: int = 500) -> str:
    try:
        return _truncate(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str), limit)
    except Exception:
        return _truncate(value, limit)


def _serialize_payload(value: Any) -> tuple[str | None, bool, str | None]:
    if value is None:
        return None, False, None
    try:
        return _json_dumps(value), True, None
    except (TypeError, ValueError) as exc:
        return None, False, str(exc)


def _source_snapshot(source: Any) -> dict[str, Any]:
    if source is None:
        return {}
    to_dict = getattr(source, "to_dict", None)
    if callable(to_dict):
        try:
            data = to_dict()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    if isinstance(source, dict):
        return dict(source)
    return {
        key: _enum_value(getattr(source, key, None))
        for key in (
            "platform",
            "chat_id",
            "chat_name",
            "chat_type",
            "user_id",
            "user_name",
            "thread_id",
            "message_id",
        )
        if getattr(source, key, None) is not None
    }


def _source_summary(source_data: dict[str, Any]) -> str:
    platform = source_data.get("platform") or "unknown"
    chat = source_data.get("chat_name") or source_data.get("chat_id")
    user = source_data.get("user_name") or source_data.get("user_id")
    parts = [str(platform)]
    if chat:
        parts.append(f"chat={chat}")
    if user:
        parts.append(f"user={user}")
    thread = source_data.get("thread_id")
    if thread:
        parts.append(f"thread={thread}")
    return " / ".join(parts)


def _raw_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_source_category(platform: str | None, raw: dict[str, Any]) -> str:
    if platform == "linz_world" or raw.get("subject") or raw.get("nats_sequence"):
        if platform == "linz_world" or raw.get("sequence_key") or raw.get("nats_sequence"):
            return "linz_world_nats"
    return platform or "unknown"


def _stable_record_id(*parts: Any) -> str:
    material = _json_dumps_display(parts, 2000)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
    return f"event:{digest}"


def record_id_for_message_event(event: Any) -> str:
    raw = _raw_dict(getattr(event, "raw_message", None))
    source_data = _source_snapshot(getattr(event, "source", None))
    platform = source_data.get("platform")
    source_category = _extract_source_category(platform, raw)
    event_id = raw.get("event_id") or getattr(event, "message_id", None) or raw.get("message_id")
    if event_id:
        return f"{source_category}:{event_id}"
    return _stable_record_id(
        source_category,
        platform,
        source_data.get("chat_id"),
        getattr(event, "text", ""),
        _coerce_datetime(getattr(event, "timestamp", None)),
    )


def record_id_for_linz_event(raw_event: dict[str, Any], record: Any | None = None) -> str:
    event_id = getattr(record, "event_id", None) or raw_event.get("event_id")
    if event_id:
        return f"linz_world_nats:{event_id}"
    sequence = raw_event.get("sequence") if isinstance(raw_event.get("sequence"), dict) else {}
    return _stable_record_id(
        "linz_world_nats",
        raw_event.get("subject"),
        raw_event.get("event_type"),
        sequence.get("stream"),
        sequence.get("consumer"),
        sequence.get("nats_sequence"),
    )


def _encode_cursor(consumed_at: str, record_id: str) -> str:
    payload = _json_dumps({"consumed_at": consumed_at, "record_id": record_id}).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        consumed_at = str(data["consumed_at"])
        record_id = str(data["record_id"])
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc
    return consumed_at, record_id


class EventProjectionStore:
    """SQLite-backed projection ledger scoped to the active Hermes profile."""

    def __init__(self, root: Path | str | None = None, path: Path | str | None = None):
        self.root = Path(root) if root is not None else get_hermes_home()
        self.path = Path(path) if path is not None else self.root / "gateway" / "message_events.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _initialize_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS event_records (
                    record_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    source_category TEXT NOT NULL,
                    platform TEXT,
                    source_summary TEXT NOT NULL DEFAULT '',
                    subject TEXT,
                    event_type TEXT,
                    occurred_at TEXT,
                    consumed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sequence_key TEXT,
                    nats_sequence TEXT,
                    payload_summary TEXT NOT NULL DEFAULT '',
                    raw_payload_json TEXT,
                    raw_payload_available INTEGER NOT NULL DEFAULT 0,
                    raw_payload_error TEXT,
                    consume_status TEXT NOT NULL,
                    projection_status TEXT NOT NULL,
                    dedupe_status TEXT,
                    duplicate_of_record_id TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS message_event_projections (
                    record_id TEXT PRIMARY KEY,
                    message_event_id TEXT,
                    message_type TEXT,
                    text_summary TEXT NOT NULL DEFAULT '',
                    source_snapshot_json TEXT,
                    raw_message_summary TEXT NOT NULL DEFAULT '',
                    media_count INTEGER NOT NULL DEFAULT 0,
                    session_id TEXT,
                    session_key TEXT,
                    session_message_ref TEXT,
                    projected_at TEXT NOT NULL,
                    FOREIGN KEY(record_id) REFERENCES event_records(record_id)
                );
                CREATE TABLE IF NOT EXISTS event_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    at TEXT NOT NULL,
                    reason TEXT,
                    error TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY(record_id) REFERENCES event_records(record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_event_records_consumed
                    ON event_records(consumed_at DESC, record_id DESC);
                CREATE INDEX IF NOT EXISTS idx_event_records_source_category
                    ON event_records(source_category);
                CREATE INDEX IF NOT EXISTS idx_event_records_status
                    ON event_records(consume_status, projection_status);
                CREATE INDEX IF NOT EXISTS idx_event_records_subject_type
                    ON event_records(subject, event_type);
                """
            )
            self._conn.commit()

    def _record_from_row(self, row: sqlite3.Row) -> GatewayInboundEventRecord:
        return GatewayInboundEventRecord(
            record_id=row["record_id"],
            event_id=row["event_id"],
            source_category=row["source_category"],
            platform=row["platform"],
            source_summary=row["source_summary"],
            subject=row["subject"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            consumed_at=row["consumed_at"],
            updated_at=row["updated_at"],
            sequence_key=row["sequence_key"],
            nats_sequence=row["nats_sequence"],
            payload_summary=row["payload_summary"],
            raw_payload_json=row["raw_payload_json"],
            raw_payload_available=bool(row["raw_payload_available"]),
            raw_payload_error=row["raw_payload_error"],
            consume_status=row["consume_status"],
            projection_status=row["projection_status"],
            dedupe_status=row["dedupe_status"],
            duplicate_of_record_id=row["duplicate_of_record_id"],
            attempt_count=int(row["attempt_count"] or 0),
            last_error=row["last_error"],
        )

    def _projection_from_row(self, row: sqlite3.Row | None) -> HermesMessageEventProjection | None:
        if row is None:
            return None
        return HermesMessageEventProjection(
            record_id=row["record_id"],
            message_event_id=row["message_event_id"],
            message_type=row["message_type"],
            text_summary=row["text_summary"],
            source_snapshot_json=row["source_snapshot_json"],
            raw_message_summary=row["raw_message_summary"],
            media_count=int(row["media_count"] or 0),
            session_id=row["session_id"],
            session_key=row["session_key"],
            session_message_ref=row["session_message_ref"],
            projected_at=row["projected_at"],
        )

    def _transition_from_row(self, row: sqlite3.Row) -> EventProcessingTransition:
        return EventProcessingTransition(
            transition_id=int(row["transition_id"]),
            record_id=row["record_id"],
            from_status=row["from_status"],
            to_status=row["to_status"],
            at=row["at"],
            reason=row["reason"],
            error=row["error"],
            metadata_json=row["metadata_json"],
        )

    def _get_record_row(self, record_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM event_records WHERE record_id = ?", (record_id,)).fetchone()

    def _upsert_record(self, record: GatewayInboundEventRecord, *, preserve_existing_payload: bool = True) -> None:
        existing = self._get_record_row(record.record_id)
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO event_records (
                    record_id, event_id, source_category, platform, source_summary, subject, event_type,
                    occurred_at, consumed_at, updated_at, sequence_key, nats_sequence, payload_summary,
                    raw_payload_json, raw_payload_available, raw_payload_error, consume_status,
                    projection_status, dedupe_status, duplicate_of_record_id, attempt_count, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.event_id,
                    record.source_category,
                    record.platform,
                    record.source_summary,
                    record.subject,
                    record.event_type,
                    record.occurred_at,
                    record.consumed_at,
                    record.updated_at,
                    record.sequence_key,
                    record.nats_sequence,
                    record.payload_summary,
                    record.raw_payload_json,
                    int(record.raw_payload_available),
                    record.raw_payload_error,
                    record.consume_status,
                    record.projection_status,
                    record.dedupe_status,
                    record.duplicate_of_record_id,
                    record.attempt_count,
                    record.last_error,
                ),
            )
            return

        raw_json = record.raw_payload_json
        raw_available = int(record.raw_payload_available)
        raw_error = record.raw_payload_error
        payload_summary = record.payload_summary
        if preserve_existing_payload and existing["raw_payload_json"] and not record.raw_payload_json:
            raw_json = existing["raw_payload_json"]
            raw_available = int(existing["raw_payload_available"] or 0)
            raw_error = existing["raw_payload_error"]
            payload_summary = existing["payload_summary"]
        if preserve_existing_payload and existing["raw_payload_json"] and record.raw_payload_json:
            raw_json = existing["raw_payload_json"]
            raw_available = int(existing["raw_payload_available"] or 0)
            raw_error = existing["raw_payload_error"]
            payload_summary = existing["payload_summary"]

        self._conn.execute(
            """
            UPDATE event_records SET
                event_id = COALESCE(?, event_id),
                source_category = ?,
                platform = COALESCE(?, platform),
                source_summary = COALESCE(NULLIF(?, ''), source_summary),
                subject = COALESCE(?, subject),
                event_type = COALESCE(?, event_type),
                occurred_at = COALESCE(?, occurred_at),
                updated_at = ?,
                sequence_key = COALESCE(?, sequence_key),
                nats_sequence = COALESCE(?, nats_sequence),
                payload_summary = COALESCE(NULLIF(?, ''), payload_summary),
                raw_payload_json = ?,
                raw_payload_available = ?,
                raw_payload_error = ?,
                consume_status = ?,
                projection_status = ?,
                dedupe_status = COALESCE(?, dedupe_status),
                duplicate_of_record_id = COALESCE(?, duplicate_of_record_id),
                attempt_count = MAX(attempt_count, ?),
                last_error = COALESCE(?, last_error)
            WHERE record_id = ?
            """,
            (
                record.event_id,
                record.source_category,
                record.platform,
                record.source_summary,
                record.subject,
                record.event_type,
                record.occurred_at,
                record.updated_at,
                record.sequence_key,
                record.nats_sequence,
                payload_summary,
                raw_json,
                raw_available,
                raw_error,
                record.consume_status,
                record.projection_status,
                record.dedupe_status,
                record.duplicate_of_record_id,
                record.attempt_count,
                record.last_error,
                record.record_id,
            ),
        )

    def _upsert_projection(self, projection: HermesMessageEventProjection) -> None:
        self._conn.execute(
            """
            INSERT INTO message_event_projections (
                record_id, message_event_id, message_type, text_summary, source_snapshot_json,
                raw_message_summary, media_count, session_id, session_key, session_message_ref, projected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                message_event_id = COALESCE(excluded.message_event_id, message_event_id),
                message_type = COALESCE(excluded.message_type, message_type),
                text_summary = COALESCE(NULLIF(excluded.text_summary, ''), text_summary),
                source_snapshot_json = COALESCE(excluded.source_snapshot_json, source_snapshot_json),
                raw_message_summary = COALESCE(NULLIF(excluded.raw_message_summary, ''), raw_message_summary),
                media_count = excluded.media_count,
                session_id = COALESCE(excluded.session_id, session_id),
                session_key = COALESCE(excluded.session_key, session_key),
                session_message_ref = COALESCE(excluded.session_message_ref, session_message_ref),
                projected_at = excluded.projected_at
            """,
            (
                projection.record_id,
                projection.message_event_id,
                projection.message_type,
                projection.text_summary,
                projection.source_snapshot_json,
                projection.raw_message_summary,
                projection.media_count,
                projection.session_id,
                projection.session_key,
                projection.session_message_ref,
                projection.projected_at,
            ),
        )

    def _insert_transition(
        self,
        record_id: str,
        from_status: str | None,
        to_status: str,
        *,
        reason: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        at: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO event_transitions(record_id, from_status, to_status, at, reason, error, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                from_status,
                to_status,
                at or utc_now_iso(),
                reason,
                error,
                _json_dumps(metadata or {}) if metadata else None,
            ),
        )

    def record_transition(
        self,
        record_id: str,
        to_status: str,
        *,
        from_status: str | None = None,
        reason: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if to_status not in CONSUME_STATUSES:
            raise ValueError(f"Invalid consume status: {to_status}")
        with self._lock:
            existing = self._get_record_row(record_id)
            if from_status is None and existing is not None:
                from_status = existing["consume_status"]
            now = utc_now_iso()
            self._conn.execute(
                """
                UPDATE event_records
                SET consume_status = ?, updated_at = ?, last_error = COALESCE(?, last_error)
                WHERE record_id = ?
                """,
                (to_status, now, error, record_id),
            )
            self._insert_transition(record_id, from_status, to_status, reason=reason, error=error, metadata=metadata, at=now)
            self._conn.commit()

    def record_message_event_received(
        self,
        event: Any,
        *,
        raw_payload: Any | None = None,
        consume_status: str = "received",
        projection_status: str = "pending",
        session_id: str | None = None,
        session_key: str | None = None,
        session_message_ref: str | None = None,
        record_id: str | None = None,
    ) -> str:
        return self._record_message_event(
            event,
            raw_payload=raw_payload,
            consume_status=consume_status,
            projection_status=projection_status,
            session_id=session_id,
            session_key=session_key,
            session_message_ref=session_message_ref,
            record_id=record_id,
            include_projection=False,
        )

    def record_message_event_projected(
        self,
        event: Any,
        *,
        raw_payload: Any | None = None,
        consume_status: str = "received",
        projection_status: str = "projected",
        session_id: str | None = None,
        session_key: str | None = None,
        session_message_ref: str | None = None,
        record_id: str | None = None,
    ) -> str:
        return self._record_message_event(
            event,
            raw_payload=raw_payload,
            consume_status=consume_status,
            projection_status=projection_status,
            session_id=session_id,
            session_key=session_key,
            session_message_ref=session_message_ref,
            record_id=record_id,
            include_projection=True,
        )

    def _record_message_event(
        self,
        event: Any,
        *,
        raw_payload: Any | None,
        consume_status: str,
        projection_status: str,
        session_id: str | None,
        session_key: str | None,
        session_message_ref: str | None,
        record_id: str | None,
        include_projection: bool,
    ) -> str:
        if consume_status not in CONSUME_STATUSES:
            raise ValueError(f"Invalid consume status: {consume_status}")
        if projection_status not in PROJECTION_STATUSES:
            raise ValueError(f"Invalid projection status: {projection_status}")
        raw_message = getattr(event, "raw_message", None)
        raw = _raw_dict(raw_message)
        source_data = _source_snapshot(getattr(event, "source", None))
        platform = source_data.get("platform")
        source_category = _extract_source_category(platform, raw)
        event_id = raw.get("event_id") or getattr(event, "message_id", None) or raw.get("message_id")
        now = utc_now_iso()
        record_id = record_id or record_id_for_message_event(event)
        payload = raw_payload if raw_payload is not None else raw_message
        raw_json, raw_available, raw_error = _serialize_payload(payload)
        occurred_at = raw.get("occurred_at") or _coerce_datetime(getattr(event, "timestamp", None))
        payload_summary = (
            raw.get("payload_summary")
            or raw.get("summary")
            or _json_dumps_display(payload if payload is not None else getattr(event, "text", ""), 500)
        )

        record = GatewayInboundEventRecord(
            record_id=record_id,
            event_id=str(event_id) if event_id is not None else None,
            source_category=source_category,
            platform=platform,
            source_summary=_source_summary(source_data),
            subject=str(raw.get("subject")) if raw.get("subject") is not None else None,
            event_type=str(raw.get("event_type")) if raw.get("event_type") is not None else _enum_value(getattr(event, "message_type", None)),
            occurred_at=occurred_at,
            consumed_at=now,
            updated_at=now,
            sequence_key=str(raw.get("sequence_key")) if raw.get("sequence_key") is not None else None,
            nats_sequence=str(raw.get("nats_sequence")) if raw.get("nats_sequence") is not None else None,
            payload_summary=_truncate(payload_summary, 500),
            raw_payload_json=raw_json,
            raw_payload_available=raw_available,
            raw_payload_error=raw_error,
            consume_status=consume_status,
            projection_status=projection_status,
            dedupe_status=None,
            duplicate_of_record_id=None,
            attempt_count=0,
            last_error=None,
        )
        projection = HermesMessageEventProjection(
            record_id=record_id,
            message_event_id=str(getattr(event, "message_id", "") or event_id or "") or None,
            message_type=_enum_value(getattr(event, "message_type", None)),
            text_summary=_truncate(getattr(event, "text", ""), 500),
            source_snapshot_json=_json_dumps(source_data) if source_data else None,
            raw_message_summary=_json_dumps_display(raw_message, 500),
            media_count=len(getattr(event, "media_urls", None) or []),
            session_id=session_id,
            session_key=session_key,
            session_message_ref=session_message_ref,
            projected_at=now,
        )

        with self._lock:
            existing = self._get_record_row(record_id)
            from_status = existing["consume_status"] if existing is not None else None
            self._upsert_record(record)
            if include_projection:
                self._upsert_projection(projection)
            self._insert_transition(record_id, from_status, consume_status, reason="message_event_recorded", at=now)
            self._conn.commit()
        return record_id

    def record_linz_world_event(
        self,
        raw_event: dict[str, Any],
        record: Any,
        *,
        message_event: Any | None = None,
        consume_status: str = "processing",
        projection_status: str = "pending",
        dedupe_status: str | None = None,
    ) -> str:
        if consume_status not in CONSUME_STATUSES:
            raise ValueError(f"Invalid consume status: {consume_status}")
        if projection_status not in PROJECTION_STATUSES:
            raise ValueError(f"Invalid projection status: {projection_status}")
        now = utc_now_iso()
        record_id = record_id_for_linz_event(raw_event, record)
        raw_json, raw_available, raw_error = _serialize_payload(raw_event)
        sequence = raw_event.get("sequence") if isinstance(raw_event.get("sequence"), dict) else {}
        nats_sequence = getattr(record, "nats_sequence", "") or sequence.get("nats_sequence")
        source = getattr(record, "source", {}) or raw_event.get("source") or {}
        platform = "linz_world"
        source_data = {
            "platform": platform,
            "chat_id": source.get("room_id") or source.get("chat_id") or "world",
            "chat_name": source.get("room_name") or "Linz World",
            "chat_type": "world",
            "user_id": source.get("actor_id") or source.get("user_id") or "world",
            "user_name": source.get("actor_name") or "Linz World",
            "message_id": getattr(record, "event_id", None) or raw_event.get("event_id"),
        }
        inbound = GatewayInboundEventRecord(
            record_id=record_id,
            event_id=getattr(record, "event_id", None) or raw_event.get("event_id"),
            source_category="linz_world_nats",
            platform=platform,
            source_summary=_source_summary(source_data),
            subject=getattr(record, "subject", None) or raw_event.get("subject"),
            event_type=getattr(record, "event_type", None) or raw_event.get("event_type"),
            occurred_at=getattr(record, "occurred_at", None) or raw_event.get("occurred_at"),
            consumed_at=now,
            updated_at=now,
            sequence_key=getattr(record, "sequence_key", None) or raw_event.get("sequence_key"),
            nats_sequence=str(nats_sequence) if nats_sequence not in (None, "") else None,
            payload_summary=_truncate(getattr(record, "payload_summary", None) or raw_event.get("payload_summary") or _json_dumps_display(raw_event.get("payload"), 500), 500),
            raw_payload_json=raw_json,
            raw_payload_available=raw_available,
            raw_payload_error=raw_error,
            consume_status=consume_status,
            projection_status=projection_status,
            dedupe_status=dedupe_status,
            duplicate_of_record_id=record_id if dedupe_status == "duplicate" else None,
            attempt_count=int(getattr(record, "attempt_count", 0) or 0),
            last_error=getattr(record, "last_error", None) or None,
        )

        with self._lock:
            existing = self._get_record_row(record_id)
            from_status = existing["consume_status"] if existing is not None else None
            self._upsert_record(inbound, preserve_existing_payload=False)
            if message_event is not None:
                projection_id = self.record_message_event_projected(
                    message_event,
                    raw_payload=None,
                    consume_status=consume_status,
                    projection_status="projected",
                    record_id=record_id,
                )
                # record_message_event_projected already committed and inserted a transition.
                return projection_id
            self._insert_transition(record_id, from_status, consume_status, reason="linz_world_event_recorded", at=now)
            self._conn.commit()
        return record_id

    def _mark(self, record_id: str, status: str, *, reason: str | None = None, error: str | None = None) -> None:
        self.record_transition(record_id, status, reason=reason, error=error)

    def mark_processing(self, record_id: str, *, session_id: str | None = None, session_key: str | None = None) -> None:
        metadata = {k: v for k, v in {"session_id": session_id, "session_key": session_key}.items() if v}
        with self._lock:
            existing = self._get_record_row(record_id)
            from_status = existing["consume_status"] if existing is not None else None
            now = utc_now_iso()
            self._conn.execute(
                "UPDATE event_records SET consume_status = ?, updated_at = ? WHERE record_id = ?",
                ("processing", now, record_id),
            )
            if session_id or session_key:
                self._conn.execute(
                    """
                    UPDATE message_event_projections
                    SET session_id = COALESCE(?, session_id), session_key = COALESCE(?, session_key)
                    WHERE record_id = ?
                    """,
                    (session_id, session_key, record_id),
                )
            self._insert_transition(record_id, from_status, "processing", reason="gateway_processing", metadata=metadata, at=now)
            self._conn.commit()

    def mark_handled(self, record_id: str) -> None:
        self._mark(record_id, "handled", reason="gateway_handled")

    def mark_failed(self, record_id: str, error: str | None = None) -> None:
        self._mark(record_id, "failed", reason="gateway_failed", error=error)

    def mark_duplicate(self, record_id: str, *, duplicate_of_record_id: str | None = None) -> None:
        with self._lock:
            existing = self._get_record_row(record_id)
            from_status = existing["consume_status"] if existing is not None else None
            now = utc_now_iso()
            self._conn.execute(
                """
                UPDATE event_records
                SET consume_status = 'duplicate', dedupe_status = 'duplicate',
                    duplicate_of_record_id = COALESCE(?, duplicate_of_record_id), updated_at = ?
                WHERE record_id = ?
                """,
                (duplicate_of_record_id, now, record_id),
            )
            self._insert_transition(record_id, from_status, "duplicate", reason="duplicate_event", at=now)
            self._conn.commit()

    def mark_ignored(self, record_id: str, reason: str | None = None) -> None:
        self._mark(record_id, "ignored", reason=reason or "gateway_ignored")

    def mark_unauthorized(self, record_id: str, reason: str | None = None) -> None:
        self._mark(record_id, "unauthorized", reason=reason or "gateway_unauthorized")

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._get_record_row(record_id)
            if row is None:
                return None
            projection_row = self._conn.execute(
                "SELECT * FROM message_event_projections WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            transition_rows = self._conn.execute(
                "SELECT * FROM event_transitions WHERE record_id = ? ORDER BY transition_id ASC",
                (record_id,),
            ).fetchall()
            record = self._record_from_row(row)
            projection = self._projection_from_row(projection_row)
            return {
                "record": record.to_dict(include_raw_payload=True),
                "projection": projection.to_dict() if projection else None,
                "transitions": [self._transition_from_row(item).to_dict() for item in transition_rows],
            }

    def list_records(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        source_category: str | None = None,
        consume_status: str | None = None,
        projection_status: str | None = None,
        source: str | None = None,
        subject: str | None = None,
        event_type: str | None = None,
        q: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        if consume_status and consume_status not in CONSUME_STATUSES:
            raise ValueError(f"Invalid consume status: {consume_status}")
        if projection_status and projection_status not in PROJECTION_STATUSES:
            raise ValueError(f"Invalid projection status: {projection_status}")

        where: list[str] = []
        params: list[Any] = []
        if source_category:
            where.append("r.source_category = ?")
            params.append(source_category)
        if consume_status:
            where.append("r.consume_status = ?")
            params.append(consume_status)
        if projection_status:
            where.append("r.projection_status = ?")
            params.append(projection_status)
        if source:
            where.append("(r.platform = ? OR r.source_summary LIKE ?)")
            params.extend([source, f"%{source}%"])
        if subject:
            where.append("r.subject = ?")
            params.append(subject)
        if event_type:
            where.append("r.event_type = ?")
            params.append(event_type)
        if from_time:
            where.append("r.consumed_at >= ?")
            params.append(from_time)
        if to_time:
            where.append("r.consumed_at <= ?")
            params.append(to_time)
        if q:
            pattern = f"%{q}%"
            where.append(
                """
                (
                    r.record_id LIKE ? OR r.event_id LIKE ? OR r.subject LIKE ? OR
                    r.event_type LIKE ? OR r.source_summary LIKE ? OR r.payload_summary LIKE ? OR
                    p.message_event_id LIKE ? OR p.text_summary LIKE ?
                )
                """
            )
            params.extend([pattern] * 8)
        if cursor:
            consumed_at, record_id = _decode_cursor(cursor)
            where.append("(r.consumed_at < ? OR (r.consumed_at = ? AND r.record_id < ?))")
            params.extend([consumed_at, consumed_at, record_id])

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        query = f"""
            SELECT r.*, p.message_event_id, p.text_summary, p.session_id
            FROM event_records r
            LEFT JOIN message_event_projections p ON p.record_id = r.record_id
            {where_sql}
            ORDER BY r.consumed_at DESC, r.record_id DESC
            LIMIT ?
        """
        params.append(limit + 1)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()

        next_cursor = None
        page_rows = rows[:limit]
        if len(rows) > limit and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_cursor(last["consumed_at"], last["record_id"])

        records = []
        for row in page_rows:
            record = self._record_from_row(row).to_dict()
            record["message_event_id"] = row["message_event_id"]
            record["message_event_summary"] = row["text_summary"]
            record["session_id"] = row["session_id"]
            records.append(record)
        return {"records": records, "next_cursor": next_cursor}


def close_all(stores: Iterable[EventProjectionStore]) -> None:
    for store in stores:
        store.close()
