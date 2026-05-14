"""Gateway adapter registration for Linz World events."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platform_registry import PlatformEntry, platform_registry
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult

from . import auth
from .config import load_linz_world_config
from .event_bus import project_to_message_event
from .event_state import LinzStateRepository
from .models import EventDispatchRecord
from .nats_transport import NatsEventListener


class LinzWorldPlatformAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("linz_world"))
        self._repository = LinzStateRepository()
        self._listener: NatsEventListener | None = None
        self._loop = None

    async def connect(self) -> bool:
        try:
            auth_map = auth.refresh_authorization_map(self._repository)
            subjects = list(auth_map.allowed_subscribe_subjects)
            cfg = load_linz_world_config()
            self._loop = asyncio.get_running_loop()
            if subjects:
                self._listener = NatsEventListener(
                    nats_url=cfg.nats_url,
                    subjects=subjects,
                    on_event=self._dispatch_from_listener,
                )
                self._listener.start()
        except Exception as exc:
            self._set_fatal_error(
                "linz_world_listener_failed",
                f"Linz World listener failed to start: {exc}",
                retryable=True,
            )
            return False
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._mark_disconnected()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        return SendResult(success=False, error="Linz World gateway adapter is receive-only; use linz_publish for external publish.")

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {
            "id": chat_id,
            "name": "Linz World",
            "type": "channel",
            "platform": "linz_world",
        }

    async def handle_world_event(
        self,
        raw_event: dict[str, Any],
        repository: LinzStateRepository | None = None,
    ) -> "WorldEventDispatchResult":
        return await dispatch_world_event(
            raw_event,
            self.handle_message,
            repository,
            session_store=getattr(self, "_session_store", None),
        )

    def _dispatch_from_listener(self, raw_event: dict[str, Any]) -> None:
        if self._loop is None:
            return

        future = asyncio.run_coroutine_threadsafe(
            self.handle_world_event(raw_event, self._repository),
            self._loop,
        )

        def _consume_error(done):
            try:
                done.result()
            except Exception:
                return

        future.add_done_callback(_consume_error)


@dataclass
class PersistedWorldEvent:
    record: EventDispatchRecord
    message_event: MessageEvent | None
    created: bool
    ack_ready: bool = True


@dataclass
class WorldEventDispatchResult:
    persisted: PersistedWorldEvent
    handled: bool
    record: EventDispatchRecord
    error: str = ""


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


async def dispatch_world_event(
    raw_event: dict[str, Any],
    handle_message: Callable[[MessageEvent], Any],
    repository: LinzStateRepository | None = None,
    *,
    retry_limit: int = 3,
    session_store: Any = None,
) -> WorldEventDispatchResult:
    repo = repository or LinzStateRepository()
    persisted = persist_world_event_for_gateway(raw_event, repo)
    if not persisted.created or persisted.message_event is None:
        return WorldEventDispatchResult(
            persisted=persisted,
            handled=False,
            record=persisted.record,
        )

    _wake_autonomous_runtime(
        persisted,
        session_store=session_store,
    )

    try:
        maybe_result = handle_message(persisted.message_event)
        if inspect.isawaitable(maybe_result):
            await maybe_result
    except Exception as exc:
        failed = repo.mark_processing_failure(
            persisted.record.event_id,
            f"{type(exc).__name__}: {exc}",
            retry_limit=retry_limit,
        )
        return WorldEventDispatchResult(
            persisted=persisted,
            handled=False,
            record=failed,
            error=failed.last_error,
        )

    handled = repo.mark_handled(persisted.record.event_id)
    return WorldEventDispatchResult(
        persisted=persisted,
        handled=True,
        record=handled,
    )


def _wake_autonomous_runtime(
    persisted: PersistedWorldEvent,
    *,
    session_store: Any = None,
) -> None:
    message = persisted.message_event
    if message is None:
        return
    try:
        from hermes_cli.os_runtime import load_runtime_config

        config = load_runtime_config()
        autonomous = getattr(config, "autonomous", None)
        if (
            not config.enabled
            or autonomous is None
            or not autonomous.enabled
            or not autonomous.respond_to_world_events
        ):
            return

        session_id = _resolve_session_id(message, session_store=session_store)
        if not session_id:
            return

        from agent.os_runtime.world_event_waker import WorldEventWaker

        WorldEventWaker(
            session_id,
            profile_id=getattr(session_store, "profile_id", "") if session_store is not None else "",
            config=config,
        ).handle_persisted_event(
            {
                "event_id": persisted.record.event_id,
                "event_type": "world_event",
                "source": "linz_world",
                "trace_id": persisted.record.event_id,
                "session_id": session_id,
                "summary": persisted.record.payload_summary,
                "metadata": dict(message.raw_message or {}),
                "content_ref": persisted.record.audit_ref,
                "status": "recorded",
            }
        )
    except Exception:
        return


def _resolve_session_id(message: MessageEvent, *, session_store: Any = None) -> str:
    if session_store is not None:
        try:
            entry = session_store.get_or_create_session(message.source)
            session_id = str(getattr(entry, "session_id", "") or "")
            if session_id:
                return session_id
        except Exception:
            pass
    source = message.source
    if source is None:
        return ""
    platform = getattr(source.platform, "value", None) or str(source.platform or "linz_world")
    chat_id = str(getattr(source, "chat_id", "") or "")
    user_id = str(getattr(source, "user_id", "") or "")
    return f"{platform}:{chat_id}:{user_id}".strip(":")


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
