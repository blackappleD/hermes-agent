"""Gateway adapter registration for Linz World events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platform_registry import PlatformEntry, platform_registry
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult

from .event_bus import project_to_message_event
from .event_state import LinzStateRepository
from .models import EventDispatchRecord


class LinzWorldPlatformAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("linz_world"))

    async def connect(self) -> bool:
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        self._mark_disconnected()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        return SendResult(success=False, error="Linz World gateway adapter is receive-only; use linz_publish for external publish.")


@dataclass
class PersistedWorldEvent:
    record: EventDispatchRecord
    message_event: MessageEvent | None
    created: bool
    ack_ready: bool = True


def persist_world_event_for_gateway(
    raw_event: dict[str, Any],
    repository: LinzStateRepository | None = None,
) -> PersistedWorldEvent:
    """Persist and dedupe a raw world event before creating a MessageEvent."""
    repo = repository or LinzStateRepository()
    record, created = repo.persist_world_event(raw_event)
    if not created:
        return PersistedWorldEvent(record=record, message_event=None, created=False)
    refreshed = repo.mark_processing(record.event_id)
    return PersistedWorldEvent(
        record=refreshed,
        message_event=project_to_message_event(refreshed),
        created=True,
    )


def register_platform() -> None:
    if platform_registry.is_registered("linz_world"):
        return
    platform_registry.register(
        PlatformEntry(
            name="linz_world",
            label="Linz World",
            adapter_factory=lambda cfg: LinzWorldPlatformAdapter(cfg),
            check_fn=lambda: True,
            validate_config=lambda cfg: True,
            source="builtin",
            emoji="🌐",
            platform_hint="Linz World events are external world signals. Respond using redacted summaries only.",
            allow_update_command=False,
        )
    )


register_platform()
