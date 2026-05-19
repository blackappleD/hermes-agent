"""Gateway adapter registration for Linz World events."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from gateway.config import Platform, PlatformConfig
from gateway.event_projection_store import EventProjectionStore
from gateway.platform_registry import PlatformEntry, platform_registry
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult

from . import auth
from .config import load_linz_world_config
from .event_bus import project_to_message_event
from .event_state import LinzStateRepository
from .models import AuthState, EventDispatchRecord, ReceiptStatus, to_plain, utc_now_iso
from .nats_transport import NatsEventListener

logger = logging.getLogger(__name__)


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
            if auth_map.state != AuthState.CURRENT:
                message = auth_map.last_error or "Linz World authorization map is not current."
                logger.warning(message)
                self._mark_listener_offline(message, only_current_pid=False)
                self._set_fatal_error(
                    "linz_world_authorization_refresh_failed",
                    message,
                    retryable=True,
                )
                return False
            if not subjects:
                message = (
                    "Linz World listener has no authorized NATS subscribe subjects; "
                    "refresh login/authorization before starting the gateway."
                )
                logger.warning(message)
                self._mark_listener_offline(message, only_current_pid=False)
                self._set_fatal_error(
                    "linz_world_listener_not_authorized",
                    message,
                    retryable=True,
                )
                return False
            logger.info("Starting Linz World NATS listener for %d subject(s)", len(subjects))
            self._listener = NatsEventListener(
                nats_url=cfg.nats_url,
                subjects=subjects,
                on_event=self._dispatch_from_listener,
            )
            self._listener.start()
            self._mark_listener_online()
        except Exception as exc:
            if self._listener is not None:
                self._listener.stop()
                self._listener = None
            self._mark_listener_offline(f"{type(exc).__name__}: {exc}", only_current_pid=False)
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
        self._mark_listener_offline()
        self._mark_disconnected()

    def _mark_listener_online(self) -> None:
        session = self._repository.get_login()
        session.online = True
        session.listener_pid = os.getpid()
        session.listener_started_at = utc_now_iso()
        session.listener_last_error = ""
        self._repository.save_login(session)

    def _mark_listener_offline(self, error: str = "", *, only_current_pid: bool = True) -> None:
        session = self._repository.get_login()
        current_pid = os.getpid()
        had_current_listener = bool(session.listener_pid and session.listener_pid == current_pid)
        if only_current_pid and session.listener_pid and session.listener_pid != current_pid:
            return
        session.online = False
        session.listener_pid = 0
        session.listener_started_at = ""
        if error:
            session.listener_last_error = error
        elif had_current_listener:
            session.listener_last_error = ""
        self._repository.save_login(session)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        cfg = load_linz_world_config()
        if cfg.auto_respond or cfg.auto_publish:
            target_os_id = _linz_reply_target(metadata)
            if target_os_id:
                try:
                    from .chat import send_chat_message

                    receipt = send_chat_message(
                        target_os_id,
                        content,
                        to_os_name=str((metadata or {}).get("linz_world_user_name") or ""),
                        conversation_id=str((metadata or {}).get("linz_world_chat_id") or chat_id or ""),
                        repository=self._repository,
                    )
                    success = receipt.status == ReceiptStatus.PUBLISHED
                    if success:
                        logger.info(
                            "Published Linz World gateway response to %s (%s chars)",
                            target_os_id,
                            len(content or ""),
                        )
                    else:
                        logger.warning(
                            "Linz World gateway response publish rejected: target=%s status=%s code=%s message=%s",
                            target_os_id,
                            receipt.status.value,
                            receipt.governance_code,
                            receipt.message,
                        )
                    return SendResult(
                        success=success,
                        message_id=receipt.world_event_id or receipt.request_id,
                        error="" if success else (receipt.message or receipt.governance_code or receipt.status.value),
                        raw_response=to_plain(receipt),
                    )
                except Exception as exc:
                    logger.warning(
                        "Linz World gateway response publish failed: %s",
                        exc,
                        exc_info=True,
                    )
                    return SendResult(
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                        raw_response={"reason": "linz_world_gateway_publish_failed"},
                    )

        logger.info(
            "Suppressing Linz World gateway response to %s; adapter is receive-only and external publish must use linz_publish.",
            chat_id,
        )
        return SendResult(
            success=True,
            raw_response={
                "suppressed": True,
                "reason": "linz_world_gateway_receive_only",
            },
        )

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


def _linz_reply_target(metadata: Optional[dict[str, Any]]) -> str:
    if not isinstance(metadata, dict):
        return ""
    target = str(metadata.get("linz_world_user_id") or "").strip()
    if target.lower() in {"", "linz_world", "world"}:
        return ""
    if target.startswith("wsp."):
        target = target.removeprefix("wsp.")
    return target


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
        _record_projection_ledger(
            raw_event,
            record,
            consume_status="duplicate",
            projection_status="pending",
            dedupe_status="duplicate",
        )
        return PersistedWorldEvent(record=record, message_event=None, created=False)
    refreshed = repo.mark_processing(record.event_id)
    message_event = project_to_message_event(refreshed)
    _record_projection_ledger(
        raw_event,
        refreshed,
        message_event=message_event,
        consume_status="processing",
        projection_status="projected",
    )
    return PersistedWorldEvent(
        record=refreshed,
        message_event=message_event,
        created=True,
    )


async def dispatch_world_event(
    raw_event: dict[str, Any],
    handle_message: Callable[[MessageEvent], Any],
    repository: LinzStateRepository | None = None,
    *,
    retry_limit: int = 3,
    session_store: Any = None,
    wake_inline: bool = False,
) -> WorldEventDispatchResult:
    repo = repository or LinzStateRepository()
    persisted = persist_world_event_for_gateway(raw_event, repo)
    if not persisted.created or persisted.message_event is None:
        return WorldEventDispatchResult(
            persisted=persisted,
            handled=False,
            record=persisted.record,
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
        _mark_projection_failed(persisted.message_event, failed.last_error)
        _start_autonomous_runtime_wake(
            persisted,
            session_store=session_store,
            final_status="failed",
            inline=wake_inline,
        )
        return WorldEventDispatchResult(
            persisted=persisted,
            handled=False,
            record=failed,
            error=failed.last_error,
        )

    handled = repo.mark_handled(persisted.record.event_id)
    _mark_projection_handled(persisted.message_event)
    _start_autonomous_runtime_wake(
        persisted,
        session_store=session_store,
        final_status="handled",
        inline=wake_inline,
    )
    return WorldEventDispatchResult(
        persisted=persisted,
        handled=True,
        record=handled,
    )


def _record_projection_ledger(
    raw_event: dict[str, Any],
    record: EventDispatchRecord,
    *,
    message_event: MessageEvent | None = None,
    consume_status: str,
    projection_status: str,
    dedupe_status: str | None = None,
) -> None:
    store = None
    try:
        store = EventProjectionStore()
        store.record_linz_world_event(
            raw_event,
            record,
            message_event=message_event,
            consume_status=consume_status,
            projection_status=projection_status,
            dedupe_status=dedupe_status,
        )
    except Exception:
        return
    finally:
        if store is not None:
            store.close()


def _mark_projection_handled(message_event: MessageEvent | None) -> None:
    if message_event is None:
        return
    store = None
    try:
        from gateway.event_projection_store import record_id_for_message_event

        store = EventProjectionStore()
        store.mark_handled(record_id_for_message_event(message_event))
    except Exception:
        return
    finally:
        if store is not None:
            store.close()


def _mark_projection_failed(message_event: MessageEvent | None, error: str) -> None:
    if message_event is None:
        return
    store = None
    try:
        from gateway.event_projection_store import record_id_for_message_event

        store = EventProjectionStore()
        store.mark_failed(record_id_for_message_event(message_event), error=error)
    except Exception:
        return
    finally:
        if store is not None:
            store.close()


def _start_autonomous_runtime_wake(
    persisted: PersistedWorldEvent,
    *,
    session_store: Any = None,
    final_status: str,
    inline: bool = False,
) -> None:
    message = persisted.message_event
    if message is None:
        return
    config, skip_result = _load_autonomous_world_wake_config()
    if skip_result is not None:
        _record_os_runtime_pipeline(message, skip_result, final_status=final_status)
        return
    session_id = _resolve_session_id(message, session_store=session_store)
    profile_id = getattr(session_store, "profile_id", "") if session_store is not None else ""
    if not session_id:
        _record_os_runtime_pipeline(
            message,
            {"queued": False, "woke": False, "reason": "no gateway session resolved"},
            final_status=final_status,
        )
        return

    _record_os_runtime_wake_scheduled(message, final_status=final_status, session_id=session_id)
    if inline:
        _record_os_runtime_wake_started(message, final_status=final_status, session_id=session_id)
        wake_result = _wake_autonomous_runtime(
            persisted,
            session_id=session_id,
            profile_id=profile_id,
            config=config,
        )
        _record_os_runtime_pipeline(message, wake_result, final_status=final_status)
        return

    def _run_wake() -> None:
        _record_os_runtime_wake_started(message, final_status=final_status, session_id=session_id)
        wake_result = _wake_autonomous_runtime(
            persisted,
            session_id=session_id,
            profile_id=profile_id,
            config=config,
        )
        _record_os_runtime_pipeline(message, wake_result, final_status=final_status)

    try:
        thread = threading.Thread(
            target=_run_wake,
            name=f"linz-world-os-runtime-wake-{persisted.record.event_id}",
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        _record_os_runtime_pipeline(
            message,
            {
                "queued": False,
                "woke": False,
                "reason": "autonomous runtime wake thread failed",
                "error": f"{type(exc).__name__}: {exc}",
            },
            final_status=final_status,
        )


def _record_os_runtime_wake_started(
    message_event: MessageEvent | None,
    *,
    final_status: str,
    session_id: str,
) -> None:
    if message_event is None:
        return
    store = None
    try:
        from gateway.event_projection_store import record_id_for_message_event

        store = EventProjectionStore()
        store.record_transition(
            record_id_for_message_event(message_event),
            final_status,
            reason="os_runtime_wake_started",
            metadata={"session_id": session_id},
        )
    except Exception:
        logger.debug("Linz World os_runtime wake-start projection failed", exc_info=True)
    finally:
        if store is not None:
            store.close()


def _record_os_runtime_wake_scheduled(
    message_event: MessageEvent | None,
    *,
    final_status: str,
    session_id: str,
) -> None:
    if message_event is None:
        return
    store = None
    try:
        from gateway.event_projection_store import record_id_for_message_event

        store = EventProjectionStore()
        store.record_transition(
            record_id_for_message_event(message_event),
            final_status,
            reason="os_runtime_wake_scheduled",
            metadata={"session_id": session_id},
        )
    except Exception:
        logger.debug("Linz World os_runtime wake-scheduled projection failed", exc_info=True)
    finally:
        if store is not None:
            store.close()


def _load_autonomous_world_wake_config() -> tuple[Any, dict[str, Any] | None]:
    try:
        from hermes_cli.os_runtime import load_runtime_config

        config = load_runtime_config()
    except Exception as exc:
        return None, {
            "queued": False,
            "woke": False,
            "reason": "autonomous runtime config load failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    autonomous = getattr(config, "autonomous", None)
    if not getattr(config, "enabled", False):
        return config, {"queued": False, "woke": False, "reason": "os_runtime disabled"}
    if autonomous is None or not getattr(autonomous, "enabled", False):
        return config, {"queued": False, "woke": False, "reason": "autonomous runtime disabled"}
    if not getattr(autonomous, "respond_to_world_events", False):
        return config, {"queued": False, "woke": False, "reason": "respond_to_world_events=false"}
    return config, None


def _record_os_runtime_pipeline(
    message_event: MessageEvent | None,
    wake_result: Any,
    *,
    final_status: str,
) -> None:
    if message_event is None or wake_result is None:
        return
    store = None
    try:
        from gateway.event_projection_store import record_id_for_message_event

        store = EventProjectionStore()
        record_id = record_id_for_message_event(message_event)
        wake_metadata = _wake_result_metadata(wake_result)
        if wake_metadata:
            store.record_transition(
                record_id,
                final_status,
                reason="os_runtime_wake",
                metadata=wake_metadata,
            )

        evidence = _wake_result_evidence(wake_result)
        if not evidence:
            return

        steps = [
            (
                "os_runtime_life_state",
                {
                    "wake_reason": evidence.get("wake_reason"),
                    "event_ids": evidence.get("event_ids"),
                    "life_state": evidence.get("life_state"),
                    "life_delta": evidence.get("life_delta"),
                },
            ),
            (
                "os_runtime_tension_field",
                {
                    "tension_set": evidence.get("tension_set"),
                    "tension_delta": evidence.get("tension_delta"),
                },
            ),
            (
                "os_runtime_action_potential",
                {"action_potential": evidence.get("action_potential")},
            ),
            (
                "os_runtime_self_prompt",
                {"self_prompt": evidence.get("self_prompt")},
            ),
            (
                "os_runtime_open_intent",
                {"open_intent": evidence.get("open_intent")},
            ),
            (
                "os_runtime_arbitration",
                {
                    "arbitration": evidence.get("arbitration"),
                    "action_summary": evidence.get("action_summary"),
                    "stop_reason": evidence.get("stop_reason"),
                },
            ),
            (
                "os_runtime_action_execution",
                {
                    "execution": evidence.get("execution"),
                    "execution_feedback": evidence.get("execution_feedback"),
                },
            ),
            (
                "os_runtime_evidence_package",
                {"evidence_package": _evidence_package_summary(evidence.get("evidence_package"))},
            ),
        ]
        for reason, metadata in steps:
            compact = _compact_metadata(metadata)
            if compact:
                store.record_transition(record_id, final_status, reason=reason, metadata=compact)
    except Exception:
        logger.debug("Linz World os_runtime pipeline projection failed", exc_info=True)
    finally:
        if store is not None:
            store.close()


def _wake_autonomous_runtime(
    persisted: PersistedWorldEvent,
    *,
    session_id: str = "",
    profile_id: str = "",
    config: Any = None,
) -> Any:
    message = persisted.message_event
    if message is None:
        return None
    try:
        if config is None:
            config, skip_result = _load_autonomous_world_wake_config()
            if skip_result is not None:
                return skip_result
        autonomous = getattr(config, "autonomous", None)
        if (
            not config.enabled
            or autonomous is None
            or not autonomous.enabled
            or not autonomous.respond_to_world_events
        ):
            return {
                "queued": False,
                "woke": False,
                "reason": "autonomous runtime disabled or not subscribed to world events",
            }

        if not session_id:
            return {"queued": False, "woke": False, "reason": "no gateway session resolved"}

        from agent.os_runtime.world_event_waker import WorldEventWaker

        return WorldEventWaker(
            session_id,
            profile_id=profile_id,
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
    except Exception as exc:
        return {
            "queued": False,
            "woke": False,
            "reason": "autonomous runtime wake failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _wake_result_metadata(wake_result: Any) -> dict[str, Any]:
    run_result = _result_get(wake_result, "run_result")
    wake_record = _result_get(run_result, "wake_record") if run_result is not None else None
    wake_record_data = _jsonable(wake_record)
    if isinstance(wake_record_data, dict):
        wake_record_data.pop("evidence", None)
    metadata = {
        "queued": _result_get(wake_result, "queued"),
        "woke": _result_get(wake_result, "woke"),
        "reason": _result_get(wake_result, "reason"),
        "item_id": _result_get(wake_result, "item_id"),
        "error": _result_get(wake_result, "error"),
        "run_status": _result_get(run_result, "status") if run_result is not None else None,
        "run_reason": _result_get(run_result, "reason") if run_result is not None else None,
        "wake_record": wake_record_data,
    }
    return _compact_metadata(metadata)


def _wake_result_evidence(wake_result: Any) -> dict[str, Any]:
    evidence = _result_get(wake_result, "evidence")
    if isinstance(evidence, dict) and evidence:
        return _jsonable(evidence)
    run_result = _result_get(wake_result, "run_result")
    evidence = _result_get(run_result, "evidence") if run_result is not None else None
    if isinstance(evidence, dict) and evidence:
        return _jsonable(evidence)
    wake_record = _result_get(run_result, "wake_record") if run_result is not None else None
    evidence = _result_get(wake_record, "evidence") if wake_record is not None else None
    if isinstance(evidence, dict):
        return _jsonable(evidence)
    return {}


def _result_get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    data = _jsonable(metadata)
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if value not in (None, "", {}, [])}


def _evidence_package_summary(value: Any) -> dict[str, Any]:
    data = _jsonable(value)
    if not isinstance(data, dict) or not data:
        return {}
    receipts = data.get("receipts") if isinstance(data.get("receipts"), list) else []
    commands = data.get("commands") if isinstance(data.get("commands"), list) else []
    evidence_items = data.get("evidence") if isinstance(data.get("evidence"), list) else []
    return _compact_metadata(
        {
            "evidence_id": data.get("evidence_id"),
            "trace_id": data.get("trace_id"),
            "intent_id": data.get("intent_id"),
            "arbitration_id": data.get("arbitration_id"),
            "event_ids": data.get("event_ids"),
            "receipt_ids": data.get("receipt_ids"),
            "summary": data.get("summary"),
            "known_risks": data.get("known_risks"),
            "diagnostics": data.get("diagnostics"),
            "complete": data.get("complete"),
            "receipt_count": len(receipts),
            "command_count": len(commands),
            "evidence_count": len(evidence_items),
        }
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _jsonable(to_dict())
        except Exception:
            pass
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)
    return str(value)


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


def _setup_linz_world_from_gateway_menu() -> None:
    from hermes_cli.config import load_config
    from hermes_cli.setup import setup_linz_world

    setup_linz_world(load_config())


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
            setup_fn=_setup_linz_world_from_gateway_menu,
            source="builtin",
            emoji="🌐",
            platform_hint="Linz World events are external world signals. Respond using redacted summaries only.",
            allow_update_command=False,
        )
    )


register_platform()
