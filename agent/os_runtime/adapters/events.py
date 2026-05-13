"""Projection helpers from Hermes/Linz surfaces into os_runtime events."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.linz_world.redaction import redact_value
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import EventSource

from .session_store import OSRuntimeEvent, OSRuntimeEventRepository


MAX_SUMMARY_CHARS = 1024
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|api[_-]?key|password|secret|private[_-]?key|authorization)\b\s*[:=]\s*([^\s,;&]+)"
)


@dataclass
class ProjectionResult:
    status: str
    event: OSRuntimeEvent | None = None
    error: str = ""

    @property
    def written(self) -> bool:
        return self.status == "written" and self.event is not None


class EventProjectionAdapter:
    def __init__(
        self,
        repository: OSRuntimeEventRepository,
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        *,
        max_summary_chars: int = MAX_SUMMARY_CHARS,
    ):
        self.repository = repository
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.max_summary_chars = max(64, int(max_summary_chars))

    def project(
        self,
        *,
        event_type: str,
        source: EventSource,
        summary: Any,
        trace_id: str = "",
        session_id: str = "",
        event_id: str = "",
        metadata: dict[str, Any] | None = None,
        content: Any = None,
        content_ref: str = "",
        payload: Any = None,
        payload_hash: str = "",
        status: str = "recorded",
    ) -> ProjectionResult:
        if not self.config.enabled:
            return ProjectionResult(status="skipped")
        try:
            summary_text, generated_ref = bounded_summary(
                summary,
                max_chars=self.max_summary_chars,
                content_ref=content_ref,
            )
            if content is not None:
                content_text, generated_ref = bounded_summary(
                    content,
                    max_chars=self.max_summary_chars,
                    content_ref=generated_ref,
                )
                summary_text = content_text if not summary_text else summary_text
            metadata_payload = dict(metadata or {})
            if generated_ref:
                metadata_payload.setdefault("content_ref", generated_ref)
            event = OSRuntimeEvent(
                event_id=event_id or f"osr_{uuid.uuid4().hex}",
                event_type=event_type,
                source=source,
                trace_id=trace_id,
                session_id=session_id,
                timestamp=utc_now_iso(),
                summary=summary_text,
                metadata=metadata_payload,
                content_ref=generated_ref,
                payload_hash=payload_hash or stable_hash(payload if payload is not None else content),
                status=status,
            )
            stored = self.repository.append(event)
            if stored is None:
                return ProjectionResult(status="skipped")
            return ProjectionResult(status="written", event=stored)
        except Exception as exc:
            return ProjectionResult(status="error", error=f"{type(exc).__name__}: {exc}")

    def world_event(self, message_event: Any, *, trace_id: str = "", session_id: str = "") -> ProjectionResult:
        raw = getattr(message_event, "raw_message", None) or {}
        source_obj = getattr(message_event, "source", None)
        metadata = {
            "message_id": getattr(message_event, "message_id", "") or raw.get("event_id", ""),
            "subject": raw.get("subject", ""),
            "event_type": raw.get("event_type", ""),
            "nats_sequence": raw.get("nats_sequence", ""),
            "sequence_key": raw.get("sequence_key", ""),
            "os_id": raw.get("os_id", ""),
            "soul_id": raw.get("soul_id", ""),
            "audit_ref": raw.get("audit_ref", ""),
            "chat_id": getattr(source_obj, "chat_id", "") if source_obj is not None else "",
        }
        return self.project(
            event_type="world_event",
            source=EventSource.LINZ_WORLD,
            summary=getattr(message_event, "text", ""),
            trace_id=trace_id or str(raw.get("event_id") or ""),
            session_id=session_id,
            event_id=f"world_{raw.get('event_id')}" if raw.get("event_id") else "",
            metadata=metadata,
        )

    def human_request(self, text: str, *, session_id: str, trace_id: str = "", metadata: dict[str, Any] | None = None) -> ProjectionResult:
        return self.project(
            event_type="human_request",
            source=EventSource.HERMES_CONVERSATION,
            summary=text,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata,
        )

    def conversation_turn(self, summary: str, *, session_id: str, trace_id: str = "", metadata: dict[str, Any] | None = None) -> ProjectionResult:
        return self.project(
            event_type="conversation_turn",
            source=EventSource.HERMES_CONVERSATION,
            summary=summary,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata,
        )

    def assistant_response(self, text: str, *, session_id: str, trace_id: str = "", metadata: dict[str, Any] | None = None) -> ProjectionResult:
        return self.project(
            event_type="assistant_response",
            source=EventSource.HERMES_CONVERSATION,
            summary=text,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata,
        )

    def tool_called(
        self,
        tool_name: str,
        arguments: Any,
        *,
        session_id: str,
        trace_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProjectionResult:
        metadata_payload = {"tool_name": tool_name, "arguments_hash": stable_hash(arguments)}
        metadata_payload.update(metadata or {})
        return self.project(
            event_type="tool_called",
            source=EventSource.HERMES_CONVERSATION,
            summary=f"Tool called: {tool_name}",
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata_payload,
            payload=arguments,
        )

    def tool_result(
        self,
        tool_name: str,
        result: Any,
        *,
        session_id: str,
        trace_id: str = "",
        content_ref: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ProjectionResult:
        metadata_payload = {"tool_name": tool_name}
        metadata_payload.update(metadata or {})
        return self.project(
            event_type="tool_result",
            source=EventSource.TOOL_RESULT,
            summary=result,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata_payload,
            content=result,
            content_ref=content_ref or f"tool_result:{tool_name}:{stable_hash(result)[:16]}",
        )

    def os_runtime_continuation(self, prompt_summary: str, *, session_id: str, trace_id: str = "", metadata: dict[str, Any] | None = None) -> ProjectionResult:
        return self.project(
            event_type="os_runtime_continuation",
            source=EventSource.SYSTEM,
            summary=prompt_summary,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata,
        )

    def world_event_published(self, receipt: dict[str, Any], *, session_id: str = "", trace_id: str = "") -> ProjectionResult:
        return self.project(
            event_type="world_event_published",
            source=EventSource.LINZ_WORLD,
            summary=receipt.get("payload_summary") or receipt.get("message") or receipt.get("status") or "world event published",
            session_id=session_id,
            trace_id=trace_id or str(receipt.get("request_id") or receipt.get("world_event_id") or ""),
            metadata={
                "request_id": receipt.get("request_id", ""),
                "subject": receipt.get("subject", ""),
                "event_type": receipt.get("event_type", ""),
                "world_event_id": receipt.get("world_event_id", ""),
                "status": receipt.get("status", ""),
                "map_version": receipt.get("map_version", ""),
            },
            payload=receipt,
        )

    def runtime_feedback(self, error: str, *, session_id: str = "", trace_id: str = "", metadata: dict[str, Any] | None = None) -> ProjectionResult:
        return self.project(
            event_type="runtime_feedback",
            source=EventSource.RUNTIME_FEEDBACK,
            summary=error,
            session_id=session_id,
            trace_id=trace_id,
            metadata=metadata,
            status="error",
        )


def bounded_summary(value: Any, *, max_chars: int = MAX_SUMMARY_CHARS, content_ref: str = "") -> tuple[str, str]:
    safe_value = redact_for_summary(value)
    if isinstance(safe_value, str):
        text = safe_value
    else:
        try:
            text = json.dumps(safe_value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(safe_value)
    text = text.replace("\x00", "")
    if len(text) <= max_chars:
        return text, content_ref
    ref = content_ref or f"content:{stable_hash(text)[:16]}"
    suffix = f"... [truncated; ref={ref}]"
    if len(suffix) >= max_chars:
        suffix = "... [truncated]"
    return f"{text[: max_chars - len(suffix)]}{suffix}", ref


def redact_for_summary(value: Any) -> Any:
    if isinstance(value, str):
        return _SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    return redact_value(value)


def stable_hash(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        data = value
    else:
        try:
            data = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        except TypeError:
            data = str(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _load_runtime_config() -> OSRuntimeConfig:
    try:
        from hermes_cli.config import load_config
        raw = (load_config() or {}).get("os_runtime") or {}
    except Exception:
        raw = {}
    return OSRuntimeConfig.from_dict(raw)


def _with_runtime_adapter() -> tuple[OSRuntimeEventRepository, EventProjectionAdapter] | None:
    config = _load_runtime_config()
    if not config.enabled:
        return None
    repo = OSRuntimeEventRepository(enabled=True)
    return repo, EventProjectionAdapter(repo, config)


def project_post_llm_call(
    *,
    session_id: str,
    user_message: str,
    assistant_response: str,
    conversation_history: list[dict[str, Any]] | None = None,
    model: str = "",
    platform: str = "",
) -> list[ProjectionResult]:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return [ProjectionResult(status="skipped")]
    repo, adapter = runtime
    try:
        metadata = {
            "model": model,
            "platform": platform,
            "message_count": len(conversation_history or []),
        }
        trace_id = session_id or ""
        return [
            adapter.human_request(
                user_message or "",
                session_id=session_id or "",
                trace_id=trace_id,
                metadata=metadata,
            ),
            adapter.assistant_response(
                assistant_response or "",
                session_id=session_id or "",
                trace_id=trace_id,
                metadata=metadata,
            ),
        ]
    finally:
        repo.close()


def project_post_tool_call(
    *,
    tool_name: str,
    args: Any,
    result: Any,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    duration_ms: int = 0,
) -> list[ProjectionResult]:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return [ProjectionResult(status="skipped")]
    repo, adapter = runtime
    try:
        trace_id = task_id or session_id or tool_call_id
        called = adapter.tool_called(
            tool_name,
            args,
            session_id=session_id or "",
            trace_id=trace_id,
            metadata={
                "task_id": task_id or "",
                "tool_call_id": tool_call_id or "",
                "duration_ms": duration_ms,
            },
        )
        result_event = adapter.tool_result(
            tool_name,
            result,
            session_id=session_id or "",
            trace_id=trace_id,
            content_ref=f"tool_result:{tool_name}:{tool_call_id or stable_hash(result)[:16]}",
            metadata={
                "task_id": task_id or "",
                "tool_call_id": tool_call_id or "",
                "duration_ms": duration_ms,
            },
        )
        return [called, result_event]
    finally:
        repo.close()


def project_goal_continuation(
    *,
    session_id: str,
    continuation_prompt: str,
    goal: str = "",
    reason: str = "",
    turns_used: int = 0,
    max_turns: int = 0,
) -> ProjectionResult:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return ProjectionResult(status="skipped")
    repo, adapter = runtime
    try:
        return adapter.os_runtime_continuation(
            continuation_prompt,
            session_id=session_id or "",
            trace_id=session_id or "",
            metadata={
                "goal": goal,
                "reason": reason,
                "turns_used": turns_used,
                "max_turns": max_turns,
            },
        )
    finally:
        repo.close()


__all__ = [
    "EventProjectionAdapter",
    "MAX_SUMMARY_CHARS",
    "ProjectionResult",
    "bounded_summary",
    "project_goal_continuation",
    "project_post_llm_call",
    "project_post_tool_call",
    "redact_for_summary",
    "stable_hash",
]
