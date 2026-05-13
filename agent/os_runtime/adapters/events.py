"""Projection helpers from Hermes/Linz surfaces into os_runtime events."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import EventSource

from .session_store import OSRuntimeEvent, OSRuntimeEventRepository


MAX_SUMMARY_CHARS = 1024


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

    def tool_called(self, tool_name: str, arguments: Any, *, session_id: str, trace_id: str = "") -> ProjectionResult:
        return self.project(
            event_type="tool_called",
            source=EventSource.HERMES_CONVERSATION,
            summary=f"Tool called: {tool_name}",
            session_id=session_id,
            trace_id=trace_id,
            metadata={"tool_name": tool_name, "arguments_hash": stable_hash(arguments)},
            payload=arguments,
        )

    def tool_result(self, tool_name: str, result: Any, *, session_id: str, trace_id: str = "", content_ref: str = "") -> ProjectionResult:
        return self.project(
            event_type="tool_result",
            source=EventSource.TOOL_RESULT,
            summary=result,
            session_id=session_id,
            trace_id=trace_id,
            metadata={"tool_name": tool_name},
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
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
    text = text.replace("\x00", "")
    if len(text) <= max_chars:
        return text, content_ref
    ref = content_ref or f"content:{stable_hash(text)[:16]}"
    suffix = f"... [truncated; ref={ref}]"
    if len(suffix) >= max_chars:
        suffix = "... [truncated]"
    return f"{text[: max_chars - len(suffix)]}{suffix}", ref


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


__all__ = ["EventProjectionAdapter", "MAX_SUMMARY_CHARS", "ProjectionResult", "bounded_summary", "stable_hash"]
