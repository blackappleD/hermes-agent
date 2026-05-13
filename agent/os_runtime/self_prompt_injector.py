"""Ephemeral and redacted SelfPrompt injection for the current user turn."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from agent.os_runtime.domain import SelfPrompt


SENSITIVE_KEY_RE = re.compile(
    r"(token|api[_-]?key|authorization|password|secret|private[_-]?key|raw_payload|restricted_audit)",
    re.IGNORECASE,
)


@dataclass
class EphemeralSelfPromptInjection:
    injected: bool
    request: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class SelfPromptInjector:
    """Inject a short-lived SelfPrompt under user-message metadata only."""

    def inject(
        self,
        request: dict[str, Any],
        self_prompt: SelfPrompt | dict[str, Any],
        *,
        evidence_refs: list[str] | None = None,
    ) -> EphemeralSelfPromptInjection:
        payload = self._payload(self_prompt, evidence_refs=evidence_refs)
        next_request = deepcopy(request)
        messages = next_request.setdefault("messages", [])
        if not isinstance(messages, list):
            messages = []
            next_request["messages"] = messages

        target: dict[str, Any] | None = None
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                target = message
                break
        if target is None:
            target = {"role": "user", "content": ""}
            messages.append(target)

        metadata = dict(target.get("metadata") or {})
        ephemeral_context = dict(metadata.get("ephemeral_context") or {})
        ephemeral_context["os_runtime_self_prompt"] = payload
        metadata["ephemeral_context"] = ephemeral_context
        target["metadata"] = metadata
        return EphemeralSelfPromptInjection(True, next_request, payload)

    def _payload(
        self,
        self_prompt: SelfPrompt | dict[str, Any],
        *,
        evidence_refs: list[str] | None,
    ) -> dict[str, Any]:
        data = self_prompt.to_dict() if hasattr(self_prompt, "to_dict") else dict(self_prompt or {})
        metadata = _dict(data.get("metadata"))
        refs = list(evidence_refs or metadata.get("evidence_refs") or [])
        payload = {
            "prompt_id": _safe_text(data.get("prompt_id")),
            "state_summary": _safe_text(data.get("state_summary")),
            "tension_summary": _safe_text(data.get("tension_summary")),
            "potential_summary": _safe_text(data.get("potential_summary")),
            "open_space": _safe_open_space(data.get("open_space")),
            "target_direction": _safe_target_direction(data.get("target_direction")),
            "constraints": _safe_list(data.get("constraint_scope")),
            "evidence_refs": _safe_list(refs),
        }
        return _redact(payload)


def _safe_open_space(value: Any) -> dict[str, Any]:
    data = _dict(value)
    return {
        "description": _safe_text(data.get("description")),
        "available_action_families": _safe_list(data.get("available_action_families")),
        "constraints": _safe_list(data.get("constraints")),
    }


def _safe_target_direction(value: Any) -> dict[str, Any]:
    data = _dict(value)
    return {
        "description": _safe_text(data.get("description")),
        "success_condition": _safe_text(data.get("success_condition")),
        "stop_condition": _safe_text(data.get("stop_condition")),
    }


def _dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {"value": data}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _safe_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    return [_safe_text(item) for item in value if _safe_text(item)]


def _safe_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "")
    return text[:1000]


def _redact(value: Any, *, key: str = "") -> Any:
    if SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        if SENSITIVE_KEY_RE.search(value):
            return "[REDACTED]"
        return re.sub(
            r"(?i)(token|api[_-]?key|authorization|password|secret|private[_-]?key)\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]",
            value,
        )
    return value


__all__ = ["EphemeralSelfPromptInjection", "SelfPromptInjector"]
