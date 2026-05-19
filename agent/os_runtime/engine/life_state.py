"""Deterministic life-state updates for the os_runtime tension field."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agent.os_runtime.domain import LifeState, LifeStateDelta, SignalSet


NUMERIC_FIELDS = (
    "energy",
    "fatigue",
    "health",
    "wakefulness",
    "curiosity",
    "boredom",
    "creative_pressure",
    "social_hunger",
    "silence_pressure",
    "restraint",
)


class LifeStateSystem:
    """Apply rule-based signal effects to a LifeState without side effects."""

    rule_version = "life_state.v1"

    def __init__(
        self,
        *,
        max_generated_intents: int = 5,
        silence_seconds_threshold: float = 900.0,
        long_duration_seconds: float = 120.0,
    ) -> None:
        self.max_generated_intents = max_generated_intents
        self.silence_seconds_threshold = silence_seconds_threshold
        self.long_duration_seconds = long_duration_seconds

    def update(
        self,
        signal_set: SignalSet | None,
        previous_state: LifeState | None = None,
        execution_feedback: dict[str, Any] | None = None,
    ) -> tuple[LifeState, LifeStateDelta]:
        signals = signal_set or SignalSet()
        previous = previous_state or LifeState(
            restraint=0.2,
            life_cycle="active",
            recovery_cycle="stable",
        )
        current = replace(previous, metadata=dict(previous.metadata))
        evidence: list[str] = []
        reasons: list[str] = []
        items = _signal_items(signals)

        failure_count = _failure_weight(items)
        if _feedback_status(execution_feedback) in {"failed", "failure", "error", "blocked"}:
            failure_count += 1
            evidence.append("execution_feedback:failed")
        failure_count += int(signals.metadata.get("consecutive_failures") or 0)
        if failure_count:
            _add(current, "fatigue", 0.12 * failure_count)
            _add(current, "restraint", 0.10 * failure_count)
            _add(current, "energy", -0.08 * failure_count)
            _add(current, "wakefulness", -0.05 * failure_count)
            _add(current, "health", -0.03 * failure_count)
            reasons.append("continuous failures increase fatigue and restraint")
            evidence.extend(_evidence_for(items, ("failure", "failed", "error", "blocked", "test_failure")))

        continuation_count = _continuation_weight(items)
        continuation_count += int(signals.metadata.get("consecutive_continuations") or 0)
        if continuation_count:
            _add(current, "fatigue", 0.05 * continuation_count)
            _add(current, "energy", -0.03 * continuation_count)
            _add(current, "wakefulness", -0.02 * continuation_count)
            reasons.append("continuations add cognitive load")
            evidence.extend(_evidence_for(items, ("continuation",)))

        duration = float(signals.metadata.get("duration_seconds") or signals.metadata.get("elapsed_seconds") or 0)
        feedback_duration = execution_feedback.get("duration_seconds") if execution_feedback else 0
        duration = max(duration, float(feedback_duration or 0))
        if duration >= self.long_duration_seconds:
            _add(current, "fatigue", min(0.18, duration / 1200.0))
            _add(current, "wakefulness", -0.05)
            reasons.append("long duration lowers wakefulness")
            evidence.append("metadata:duration_seconds")

        unfinished_goal = bool(
            _count_matching(items, ("active_goal", "user_goal", "event_need", "requirement", "opportunity"))
            or (signals.task_context and (signals.task_context.active_goal or signals.task_context.user_goal))
        )
        if unfinished_goal:
            _add(current, "curiosity", 0.08)
            _add(current, "creative_pressure", 0.12)
            reasons.append("unfinished goals raise curiosity and creative pressure")
            evidence.extend(_evidence_for(items, ("active_goal", "user_goal", "event_need", "requirement", "opportunity")))
            if signals.task_context and signals.task_context.active_goal:
                evidence.append("task_context:active_goal")

        positive_count = _count_matching(items, ("success", "completed", "positive", "allowed"))
        if _feedback_status(execution_feedback) in {"success", "succeeded", "completed", "passed"}:
            positive_count += 1
            evidence.append("execution_feedback:success")
        if positive_count:
            _add(current, "curiosity", 0.04 * positive_count)
            _add(current, "creative_pressure", 0.03 * positive_count)
            _add(current, "fatigue", -0.04 * positive_count)
            _add(current, "health", 0.02 * positive_count)
            reasons.append("positive feedback supports recovery and exploration")
            evidence.extend(_evidence_for(items, ("success", "completed", "positive", "allowed")))

        silence_seconds = float(signals.metadata.get("silence_seconds") or 0)
        if silence_seconds >= self.silence_seconds_threshold or _count_matching(items, ("no_feedback", "silence")):
            _add(current, "silence_pressure", 0.16)
            _add(current, "wakefulness", -0.04)
            reasons.append("silence increases pressure to seek feedback")
            evidence.append("metadata:silence_seconds")

        low_value_count = _count_matching(items, ("low_value", "duplicate", "repeated", "noop"))
        if low_value_count:
            _add(current, "boredom", 0.10 * low_value_count)
            _add(current, "curiosity", -0.02 * low_value_count)
            reasons.append("repeated low-value events increase boredom")
            evidence.extend(_evidence_for(items, ("low_value", "duplicate", "repeated", "noop")))

        social_count = _count_matching(items, ("relationship", "chat", "message", "social"))
        if social_count:
            _add(current, "social_hunger", 0.07 * social_count)
            evidence.extend(_evidence_for(items, ("relationship", "chat", "message", "social")))
            reasons.append("social signals increase social hunger")

        simple_chat_count = _simple_chat_weight(items)
        if simple_chat_count:
            _add(current, "energy", 0.005 * simple_chat_count)
            _add(current, "fatigue", -0.01 * simple_chat_count)
            _add(current, "wakefulness", 0.005 * simple_chat_count)
            reasons.append("simple chat is a low-load interaction")
            evidence.extend(_evidence_for(items, ("simple_chat",)))

        risk_count = _risk_weight(items)
        if risk_count:
            _add(current, "restraint", 0.14 * risk_count)
            _add(current, "wakefulness", -0.03 * risk_count)
            reasons.append("risk, approval, authorization, or settlement constraints raise restraint")
            evidence.extend(_evidence_for(items, ("risk", "authorization", "approval", "settlement", "rent", "constraint")))

        current.generated_intent_count = max(0, int(current.generated_intent_count))
        if execution_feedback and "generated_intent_count" in execution_feedback:
            current.generated_intent_count = max(0, int(execution_feedback["generated_intent_count"]))
        elif execution_feedback and execution_feedback.get("generated_intent"):
            current.generated_intent_count += 1
        if current.generated_intent_count >= self.max_generated_intents:
            _add(current, "restraint", 0.18)
            _add(current, "fatigue", 0.08)
            reasons.append("intent generation threshold moves the system toward cooldown")
            evidence.append("life_state:generated_intent_count")

        for field in NUMERIC_FIELDS:
            setattr(current, field, _round_numeric(getattr(current, field)))
        current.life_cycle = _life_cycle(current, self.max_generated_intents)
        current.recovery_cycle = _recovery_cycle(current)
        current.metadata = {
            **current.metadata,
            "rule_version": self.rule_version,
            "action_inhibition": _clamp(
                (
                    _bounded_metric(current, "fatigue")
                    + _bounded_metric(current, "restraint")
                    + _bounded_metric(current, "boredom")
                )
                / 3.0
            ),
        }

        changes = _changes(previous, current)
        if not changes:
            reasons.append("no matching signals; state remains stable")
        if not previous_state:
            evidence.append("life_state:initialized")
            reasons.append("initialized default life state")
        delta = LifeStateDelta(
            previous=previous.to_dict(),
            current=current,
            changes=changes,
            reasons=_dedupe(reasons),
            evidence=_dedupe(evidence),
            metadata={
                "rule_version": self.rule_version,
                "life_cycle": current.life_cycle,
                "recovery_cycle": current.recovery_cycle,
            },
        )
        return current, delta


def _signal_items(signal_set: SignalSet) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group, value in signal_set.signals.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict):
                normalized = dict(item)
            else:
                normalized = {"value": item}
            normalized["_group"] = str(group)
            items.append(normalized)
    return items


def _count_matching(items: list[dict[str, Any]], needles: tuple[str, ...]) -> int:
    return sum(1 for item in items if _matches(item, needles))


def _matches(item: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("_group", "code", "kind", "type", "level", "status", "reason", "summary", "value")
    ).lower()
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        haystack = f"{haystack} {' '.join(str(value) for value in metadata.values()).lower()}"
    return any(needle in haystack for needle in needles)


def _evidence_for(items: list[dict[str, Any]], needles: tuple[str, ...]) -> list[str]:
    evidence: list[str] = []
    for item in items:
        if not _matches(item, needles):
            continue
        group = str(item.get("_group", "signal"))
        code = str(item.get("code") or item.get("kind") or item.get("type") or "value")
        evidence.append(f"signal:{group}:{code}")
        for event_id in item.get("event_ids") or []:
            evidence.append(f"event:{event_id}")
    return evidence


def _failure_weight(items: list[dict[str, Any]]) -> int:
    weight = 0
    for item in items:
        group = str(item.get("_group") or "").lower()
        code = str(item.get("code") or item.get("kind") or item.get("type") or "").lower()
        status = str(item.get("status") or item.get("level") or "").lower()
        if group == "constraints" and code.startswith("constraint_world_"):
            continue
        if "test_failure" in code or "tool_failure" in code:
            weight += 1
            continue
        if any(token in code for token in ("failure", "failed", "error")):
            weight += 1
            continue
        if status in {"failed", "failure", "error"}:
            weight += 1
    return weight


def _continuation_weight(items: list[dict[str, Any]]) -> int:
    weight = 0
    for item in items:
        code = str(item.get("code") or item.get("kind") or item.get("type") or item.get("value") or "").lower()
        metadata = item.get("metadata")
        event_type = str(metadata.get("event_type") or "").lower() if isinstance(metadata, dict) else ""
        if code in {"continuation_need", "os_runtime_continuation"} or event_type == "os_runtime_continuation":
            weight += 1
    return weight


def _simple_chat_weight(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if str(item.get("code") or "").lower() == "simple_chat_message")


def _risk_weight(items: list[dict[str, Any]]) -> int:
    weight = 0
    for item in items:
        if not _matches(item, ("risk", "authorization", "approval", "settlement", "rent", "constraint")):
            continue
        group = str(item.get("_group") or "").lower()
        code = str(item.get("code") or "").lower()
        if group == "constraints" and code in {
            "constraint_world_identity_missing",
            "constraint_world_identity_incomplete",
            "constraint_world_login_not_active",
            "constraint_world_authorization_unknown",
        }:
            continue
        level = str(item.get("level") or item.get("status") or "").lower()
        if level in {"high", "critical", "blocked", "unknown"} or any(
            token in code for token in ("blocked", "unknown", "approval", "settlement", "rent")
        ):
            weight += 2 if level == "critical" else 1
    return weight


def _feedback_status(execution_feedback: dict[str, Any] | None) -> str:
    if not execution_feedback:
        return ""
    return str(execution_feedback.get("status") or execution_feedback.get("result") or "").lower()


def _add(state: LifeState, field: str, delta: float) -> None:
    setattr(state, field, getattr(state, field) + delta)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 6)))


def _round_numeric(value: float) -> float:
    return round(float(value), 6)


def _bounded_metric(state: LifeState, field: str) -> float:
    return _clamp(getattr(state, field))


def _life_cycle(state: LifeState, max_generated_intents: int) -> str:
    if state.generated_intent_count >= max_generated_intents or state.restraint >= 0.78:
        return "cooldown"
    if state.fatigue >= 0.70 or state.energy <= 0.25 or state.health <= 0.50:
        return "recovering"
    return "active"


def _recovery_cycle(state: LifeState) -> str:
    if state.life_cycle == "cooldown":
        return "cooldown"
    if state.fatigue >= 0.50 or state.health < 0.75:
        return "recovering"
    return "stable"


def _changes(previous: LifeState, current: LifeState) -> dict[str, dict[str, float]]:
    changes: dict[str, dict[str, float]] = {}
    for field in (*NUMERIC_FIELDS, "generated_intent_count"):
        before = getattr(previous, field)
        after = getattr(current, field)
        if before != after:
            changes[field] = {
                "before": before,
                "after": after,
                "delta": round(after - before, 6),
            }
    return changes


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


__all__ = ["LifeStateSystem"]
