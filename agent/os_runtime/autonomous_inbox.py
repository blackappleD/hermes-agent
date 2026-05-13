"""Autonomous runtime inbox with event-id and sequence-key dedupe."""

from __future__ import annotations

from typing import Any

from agent.os_runtime.adapters.runtime_queue import AutonomousInboxRecord, RuntimeQueueRepository


class AutonomousInbox:
    def __init__(self, repository: RuntimeQueueRepository):
        self.repository = repository

    def enqueue(
        self,
        *,
        session_id: str,
        profile_id: str = "",
        event_ref: Any = None,
        wake_reason: str = "world_event",
        payload: dict[str, Any] | None = None,
    ) -> tuple[AutonomousInboxRecord, bool]:
        event_payload = _to_payload(event_ref)
        merged_payload = {**event_payload, **dict(payload or {})}
        event_id = str(
            merged_payload.get("event_id")
            or merged_payload.get("world_event_id")
            or ""
        )
        sequence_key = str(
            merged_payload.get("sequence_key")
            or merged_payload.get("nats_sequence")
            or merged_payload.get("payload_hash")
            or ""
        )
        return self.repository.enqueue_inbox(
            session_id=session_id,
            profile_id=profile_id,
            event_id=event_id,
            sequence_key=sequence_key,
            wake_reason=wake_reason,
            payload=merged_payload,
        )

    def claim_next(self, session_id: str) -> AutonomousInboxRecord | None:
        return self.repository.claim_next(session_id)

    def mark_handled(self, item_id: str) -> AutonomousInboxRecord | None:
        return self.repository.update_inbox_status(item_id, "handled")

    def mark_skipped(self, item_id: str, reason: str = "") -> AutonomousInboxRecord | None:
        return self.repository.update_inbox_status(item_id, "skipped", error=reason)

    def mark_failed(self, item_id: str, error: str = "") -> AutonomousInboxRecord | None:
        return self.repository.update_inbox_status(item_id, "failed", error=error)

    def list(self, session_id: str = "", *, status: str = "", limit: int = 20) -> list[AutonomousInboxRecord]:
        return self.repository.list_inbox(session_id, status=status, limit=limit)


def _to_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {"value": data}
    if isinstance(value, dict):
        return dict(value)
    return {
        "event_id": str(getattr(value, "event_id", "") or ""),
        "summary": str(getattr(value, "summary", value) or ""),
        "sequence_key": str(getattr(value, "sequence_key", "") or ""),
    }


__all__ = ["AutonomousInbox"]
