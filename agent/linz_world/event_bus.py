"""Projection from Linz World events to Hermes gateway message events."""

from __future__ import annotations

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource

from .event_catalog import event_category
from .models import EventDispatchRecord


def chat_id_for_record(record: EventDispatchRecord) -> str:
    source = record.source or {}
    return str(
        source.get("room_id")
        or source.get("relationship_id")
        or source.get("task_id")
        or source.get("order_id")
        or record.subject
    )


def project_to_message_event(record: EventDispatchRecord) -> MessageEvent:
    source = SessionSource(
        platform=Platform("linz_world"),
        chat_id=chat_id_for_record(record),
        chat_name="Linz World",
        chat_type="channel",
        user_id=str((record.source or {}).get("actor_id") or "linz_world"),
        user_name=str((record.source or {}).get("actor_name") or "Linz World"),
        message_id=record.event_id,
    )
    text = f"[Linz World {event_category(record.subject, record.event_type)}] {record.payload_summary}"
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=source,
        raw_message={"event_id": record.event_id, "audit_ref": record.audit_ref},
        message_id=record.event_id,
        internal=False,
    )
