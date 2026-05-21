"""Structured Linz World rule projection for os_runtime.

The public Linz guide tool is useful for user-facing exploration, but its
free-text query scoring is intentionally not authoritative enough for runtime
decisions.  This adapter only promotes guide sections into os_runtime context
when the match is anchored by structured fields such as subject, event_type,
Bubble type, lifecycle state, or a normalized intent from event metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.os_runtime.domain import EventSource


AUTHORITATIVE_REASONS = {
    "subject_exact",
    "event_type_exact",
    "bubble_type_exact",
    "lifecycle_state_exact",
    "intent_exact",
}

HIGH_CONFIDENCE_REASONS = {
    "event_type_exact",
    "subject_exact",
    "bubble_type_exact",
}


@dataclass(frozen=True)
class LinzRuleResolution:
    status: str
    authoritative: bool = False
    confidence: str = "none"
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    phase: str = "unknown"
    summary: str = ""
    matched_sections: list[dict[str, Any]] = field(default_factory=list)
    recommended_tools: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    approval_required: bool = False
    required_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    discarded_matches: list[dict[str, Any]] = field(default_factory=list)
    manual_path: str = ""
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authoritative": self.authoritative,
            "confidence": self.confidence,
            "reason": self.reason,
            "context": dict(self.context),
            "phase": self.phase,
            "summary": self.summary,
            "matched_sections": list(self.matched_sections),
            "recommended_tools": list(self.recommended_tools),
            "next_steps": list(self.next_steps),
            "approval_required": self.approval_required,
            "required_fields": list(self.required_fields),
            "missing_fields": list(self.missing_fields),
            "forbidden": list(self.forbidden),
            "retrieval": {
                "mode": "structured_metadata",
                "source": "linz_world_guide",
                "discarded_match_count": len(self.discarded_matches),
                "manual_path": self.manual_path,
            },
            "discarded_matches": list(self.discarded_matches[:5]),
            "diagnostics": list(self.diagnostics),
        }


class LinzRuleContextResolver:
    """Resolve Linz guide sections from structured runtime context only."""

    def resolve(self, snapshot: Any, *, events: list[Any] | None = None) -> LinzRuleResolution:
        task = getattr(snapshot, "task_context", None)
        context = _extract_context(task, events if events is not None else getattr(snapshot, "recent_events", []))
        if not _has_structured_anchor(context):
            return LinzRuleResolution(
                status="skipped",
                reason="no structured Linz World rule anchor",
                context=context,
                diagnostics=["free_text_query_not_authoritative"],
            )

        try:
            from agent.linz_world.guide import resolve_flow

            flow = resolve_flow(
                query="",
                subject=str(context.get("subject") or ""),
                event_type=str(context.get("event_type") or ""),
                bubble_type=str(context.get("bubble_type") or ""),
                lifecycle_state=str(context.get("lifecycle_state") or ""),
                user_intent=str(context.get("user_intent") or ""),
                bubble_id=str(context.get("bubble_id") or ""),
                known_fields=dict(context.get("known_fields") or {}),
                limit=8,
            )
        except Exception as exc:
            return LinzRuleResolution(
                status="error",
                reason=f"rule resolution failed: {type(exc).__name__}",
                context=context,
                diagnostics=[str(exc)],
            )

        matches = list(flow.get("matched_sections") or [])
        authoritative = [item for item in matches if _is_authoritative_match(item)]
        discarded = [item for item in matches if item not in authoritative]
        if not authoritative:
            return LinzRuleResolution(
                status="unmatched",
                authoritative=False,
                confidence="none",
                reason="no structured guide match; keyword/text matches are not authoritative",
                context=context,
                discarded_matches=discarded,
                manual_path=str(flow.get("manual_path") or ""),
                diagnostics=["structured_match_required"],
            )

        reasons = _match_reasons(authoritative)
        confidence = "high" if any(reason in HIGH_CONFIDENCE_REASONS for reason in reasons) else "medium"
        return LinzRuleResolution(
            status="matched",
            authoritative=True,
            confidence=confidence,
            reason="structured Linz World rule match",
            context=context,
            phase=str(flow.get("phase") or "unknown"),
            summary=str(flow.get("summary") or ""),
            matched_sections=authoritative,
            recommended_tools=_string_list(flow.get("recommended_tools")),
            next_steps=_string_list(flow.get("next_steps")),
            approval_required=bool(flow.get("approval_required")),
            required_fields=_string_list(flow.get("required_fields")),
            missing_fields=_string_list(flow.get("missing_fields")),
            forbidden=_string_list(flow.get("forbidden")),
            discarded_matches=discarded,
            manual_path=str(flow.get("manual_path") or ""),
        )


def constraints_from_rule_context(rule_context: dict[str, Any]) -> list[str]:
    """Return compact constraints derived from a rule context payload."""

    if not isinstance(rule_context, dict) or not rule_context:
        return []
    constraints: list[str] = []
    if rule_context.get("status") == "unmatched":
        constraints.append("linz_rule_no_authoritative_match")
    if rule_context.get("authoritative"):
        phase = str(rule_context.get("phase") or "").strip()
        if phase:
            constraints.append(f"linz_rule_phase:{phase}")
    if rule_context.get("approval_required"):
        constraints.append("linz_rule_approval_required")
    for field_name in _string_list(rule_context.get("missing_fields")):
        constraints.append(f"linz_rule_missing_field:{field_name}")
    for item in _string_list(rule_context.get("forbidden"))[:12]:
        constraints.append(f"linz_rule_forbidden:{item}")
    return constraints


def _extract_context(task: Any, events: list[Any] | None) -> dict[str, Any]:
    metadata_sources = [_metadata(event) for event in events or []]
    task_metadata = dict(getattr(task, "metadata", {}) or {})
    metadata_sources.append(task_metadata)

    subject = _first(metadata_sources, "subject", "world_subject")
    event_type = _first(metadata_sources, "event_type", "world_event_type", "type")
    bubble_type = _first(metadata_sources, "bubble_type", "bubble_kind")
    lifecycle_state = _first(metadata_sources, "lifecycle_state", "lifecycle", "state", "status")
    user_intent = _first(metadata_sources, "user_intent", "intent", "action", "operation")
    bubble_id = _first(
        metadata_sources,
        "bubble_id",
        "demand_bubble_id",
        "task_bubble_id",
        "parent_bubble_id",
    )
    known_fields = _known_fields(metadata_sources)
    if subject:
        known_fields.setdefault("subject", subject)
    if event_type:
        known_fields.setdefault("event_type", event_type)
    if event_type == "wsp.chat.message.sent":
        reply_target = _first(metadata_sources, "to_os_id", "target_os_id", "os_id", "sender_os_id", "publisher_id")
        if reply_target:
            known_fields.setdefault("to_os_id", reply_target)
    if bubble_id:
        known_fields.setdefault("bubble_id", bubble_id)

    event_refs = []
    for event in events or []:
        event_id = str(getattr(event, "event_id", "") or (_dict(event).get("event_id") if isinstance(event, dict) else "") or "")
        if event_id:
            event_refs.append(event_id)

    return {
        "subject": subject,
        "event_type": event_type,
        "bubble_type": bubble_type,
        "lifecycle_state": lifecycle_state,
        "user_intent": user_intent,
        "bubble_id": bubble_id,
        "known_fields": known_fields,
        "event_ids": _dedupe(event_refs),
    }


def _has_structured_anchor(context: dict[str, Any]) -> bool:
    return any(
        str(context.get(key) or "").strip()
        for key in ("subject", "event_type", "bubble_type", "lifecycle_state", "user_intent", "bubble_id")
    )


def _is_authoritative_match(match: dict[str, Any]) -> bool:
    return any(reason in AUTHORITATIVE_REASONS for reason in match.get("reasons") or [])


def _match_reasons(matches: list[dict[str, Any]]) -> set[str]:
    reasons: set[str] = set()
    for match in matches:
        reasons.update(str(item) for item in match.get("reasons") or [])
    return reasons


def _metadata(event: Any) -> dict[str, Any]:
    if event is None:
        return {}
    if isinstance(event, dict):
        data = dict(event)
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            data.update(metadata)
        return data
    metadata = dict(getattr(event, "metadata", {}) or {})
    event_type = str(getattr(event, "event_type", "") or "")
    source = getattr(event, "source", "")
    if event_type and event_type != "world_event":
        metadata.setdefault("event_type", event_type)
    if getattr(source, "value", source) == EventSource.LINZ_WORLD.value:
        metadata.setdefault("source", EventSource.LINZ_WORLD.value)
    return metadata


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first(sources: list[dict[str, Any]], *keys: str) -> str:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
    return ""


def _known_fields(sources: list[dict[str, Any]]) -> dict[str, Any]:
    known: dict[str, Any] = {}
    for source in sources:
        explicit = source.get("known_fields")
        if isinstance(explicit, dict):
            known.update({str(key): value for key, value in explicit.items() if value not in (None, "")})
        for key, value in source.items():
            if value in (None, "") or isinstance(value, (dict, list, tuple, set)):
                continue
            if key.startswith("_"):
                continue
            known.setdefault(str(key), value)
    return known


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return _dedupe([str(item) for item in values if str(item or "").strip()])


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


__all__ = [
    "LinzRuleContextResolver",
    "LinzRuleResolution",
    "constraints_from_rule_context",
]
