"""Rule-based action potential evaluation for os_runtime."""

from __future__ import annotations

from dataclasses import is_dataclass
from enum import Enum
from typing import Any

from agent.os_runtime.domain import (
    ActionPotential,
    LifeState,
    OpenActionFamily,
    OpenIntent,
    RecommendedDepth,
    RiskLevel,
    SignalSet,
    Tension,
    TensionSet,
    TensionType,
)


ALLOWED_RECOMMENDED_DEPTHS = tuple(item.value for item in RecommendedDepth)


class ActionPotentialEvaluator:
    """Compute explainable action potential without invoking tools or models."""

    rule_version = "action_potential.v1"

    def __init__(self, *, thresholds: dict[str, float] | None = None) -> None:
        self.thresholds = {
            "none_below": 0.18,
            "draft_at": 0.34,
            "continue_at": 0.48,
            "tool_at": 0.66,
            "world_publish_at": 0.72,
            "bubble_at": 0.74,
            "medium_risk": 0.42,
            "high_risk": 0.68,
            **(thresholds or {}),
        }

    def evaluate(
        self,
        *,
        signal_set: SignalSet | None = None,
        life_state: LifeState | None = None,
        tension_set: TensionSet | None = None,
        candidate: OpenIntent | dict[str, Any] | None = None,
        intent_id: str = "",
    ) -> ActionPotential:
        signals = signal_set or SignalSet()
        life = life_state or LifeState(restraint=0.2, life_cycle="active")
        tensions = tension_set or TensionSet()
        candidate_view = _candidate_view(candidate)
        signal_items = _signal_items(signals)
        active_tensions = _active_tensions(tensions)

        value, value_evidence = self._value_potential(signals, signal_items, active_tensions, candidate_view)
        mutual, mutual_evidence = self._mutual_benefit_potential(signals, signal_items, active_tensions, life)
        learning, learning_evidence = self._learning_potential(signals, signal_items, active_tensions, life, candidate_view)
        risk, risk_evidence = self._risk_cost(signal_items, active_tensions, life, candidate_view)
        overall = _clamp(
            value * 0.55
            + mutual * 0.15
            + learning * 0.25
            - risk * 0.35
            + _readiness(life) * 0.10
        )
        depth = self._recommended_depth(
            overall=overall,
            risk=risk,
            value=value,
            mutual=mutual,
            learning=learning,
            signals=signals,
            signal_items=signal_items,
            active_tensions=active_tensions,
            life=life,
            candidate=candidate_view,
        )

        evidence = {
            "value_potential": _dedupe(value_evidence + ["config:action_potential:value_weights"]),
            "mutual_benefit_potential": _dedupe(mutual_evidence + ["config:action_potential:mutual_weights"]),
            "learning_potential": _dedupe(learning_evidence + ["config:action_potential:learning_weights"]),
            "risk_cost": _dedupe(risk_evidence + ["config:action_potential:risk_weights"]),
            "overall_score": [
                "config:action_potential:overall_weights",
                f"config:threshold:medium_risk:{self.thresholds['medium_risk']}",
                f"config:threshold:continue_at:{self.thresholds['continue_at']}",
            ],
            "recommended_depth": [
                f"config:recommended_depth:{depth.value}",
                f"config:allowed_depths:{','.join(ALLOWED_RECOMMENDED_DEPTHS)}",
            ],
        }

        return ActionPotential(
            intent_id=intent_id or str(candidate_view.get("intent_id") or ""),
            value_potential=value,
            mutual_benefit_potential=mutual,
            learning_potential=learning,
            risk_cost=risk,
            overall_score=overall,
            recommended_depth=depth,
            rationale=_rationale(depth, overall, risk),
            metadata={
                "rule_version": self.rule_version,
                "score_evidence": evidence,
                "recommended_depth": depth.value,
                "allowed_recommended_depths": list(ALLOWED_RECOMMENDED_DEPTHS),
                "thresholds": dict(self.thresholds),
                "candidate": _safe_candidate_metadata(candidate_view),
            },
        )

    def _value_potential(
        self,
        signals: SignalSet,
        items: list[dict[str, Any]],
        tensions: list[Tension],
        candidate: dict[str, Any],
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence: list[str] = []
        task = signals.task_context
        if task and task.user_goal:
            score += 0.18
            evidence.append("task_context:user_goal")
        if task and task.active_goal:
            score += 0.24
            evidence.append("task_context:active_goal")
        for item in items:
            if _matches(item, ("need", "goal", "requirement", "opportunity")):
                score += 0.10 + _severity_weight(item) * 0.08
                evidence.extend(_item_evidence(item))
            if _matches(item, ("low_value", "duplicate", "repeated", "noop")):
                score -= 0.12
                evidence.extend(_item_evidence(item))
        for tension in tensions:
            if tension.tension_type in {TensionType.UNSATISFIED_GOAL, TensionType.VALUE_CONFLICT}:
                score += tension.intensity * 0.36 + tension.activation * 0.12
                evidence.extend(_tension_evidence(tension))
            elif tension.tension_type == TensionType.CREATIVE_PRESSURE:
                score += tension.intensity * 0.18
                evidence.extend(_tension_evidence(tension))
        priority = float(candidate.get("priority") or candidate.get("value_priority") or 0.0)
        if priority:
            score += min(0.18, priority * 0.18)
            evidence.append("candidate:priority")
        return _clamp(score), _dedupe(evidence)

    def _mutual_benefit_potential(
        self,
        signals: SignalSet,
        items: list[dict[str, Any]],
        tensions: list[Tension],
        life: LifeState,
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence: list[str] = []
        for item in items:
            if _matches(item, ("relationship", "social", "chat", "message", "collaboration", "order")):
                score += 0.10 + _severity_weight(item) * 0.06
                evidence.extend(_item_evidence(item))
        for tension in tensions:
            if tension.tension_type == TensionType.SOCIAL_SIGNAL:
                score += tension.intensity * 0.30 + tension.activation * 0.08
                evidence.extend(_tension_evidence(tension))
        social_hunger = _life_metric(life, "social_hunger")
        if social_hunger:
            score += min(0.12, social_hunger * 0.12)
            evidence.append("life_state:social_hunger")
        if signals.task_context and signals.task_context.user_goal and _has_relationship_signal(items):
            score += 0.10
            evidence.append("task_context:user_goal")
        return _clamp(score), _dedupe(evidence)

    def _learning_potential(
        self,
        signals: SignalSet,
        items: list[dict[str, Any]],
        tensions: list[Tension],
        life: LifeState,
        candidate: dict[str, Any],
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence: list[str] = []
        for item in items:
            if _matches(item, ("uncertain", "uncertainty", "unknown", "memory", "new_task", "explore")):
                score += 0.10 + _severity_weight(item) * 0.07
                evidence.extend(_item_evidence(item))
        for tension in tensions:
            if tension.tension_type in {TensionType.UNCERTAINTY, TensionType.MEMORY_RESONANCE, TensionType.CREATIVE_PRESSURE}:
                score += tension.intensity * 0.28 + tension.activation * 0.08
                evidence.extend(_tension_evidence(tension))
        curiosity = _life_metric(life, "curiosity")
        if curiosity:
            score += min(0.16, curiosity * 0.18)
            evidence.append("life_state:curiosity")
        creative_pressure = _life_metric(life, "creative_pressure")
        if creative_pressure:
            score += min(0.12, creative_pressure * 0.14)
            evidence.append("life_state:creative_pressure")
        if candidate.get("uncertainty") or candidate.get("new_task_type"):
            score += 0.16
            evidence.append("candidate:uncertainty")
        if signals.agent_context and signals.agent_context.memory_summary:
            score += 0.06
            evidence.append("agent_context:memory_summary")
        return _clamp(score), _dedupe(evidence)

    def _risk_cost(
        self,
        items: list[dict[str, Any]],
        tensions: list[Tension],
        life: LifeState,
        candidate: dict[str, Any],
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence: list[str] = []
        current_allowed_chat = _current_allowed_direct_world_chat(items)
        for item in items:
            if _is_allowed_authorization_signal(item):
                continue
            if _matches(item, ("risk", "authorization", "approval", "settlement", "rent", "constraint")):
                score += 0.08 + _risk_weight(item)
                evidence.extend(_item_evidence(item))
        for tension in tensions:
            if tension.tension_type in {TensionType.CONSTRAINT, TensionType.VALUE_CONFLICT}:
                weight = 0.25 if current_allowed_chat and tension.tension_type == TensionType.CONSTRAINT else 1.0
                score += (tension.intensity * 0.32 + tension.activation * 0.08) * weight
                evidence.extend(_tension_evidence(tension))
        restraint = _life_metric(life, "restraint")
        fatigue = _life_metric(life, "fatigue")
        score += max(0.0, restraint - 0.25) * 0.22
        score += fatigue * 0.18
        if restraint >= 0.25:
            evidence.append("life_state:restraint")
        if fatigue:
            evidence.append("life_state:fatigue")
        risk_level = str(candidate.get("risk_level") or "").lower()
        if risk_level:
            score += {
                RiskLevel.LOW.value: 0.04,
                RiskLevel.MEDIUM.value: 0.22,
                RiskLevel.HIGH.value: 0.46,
                RiskLevel.CRITICAL.value: 0.70,
            }.get(risk_level, 0.18)
            evidence.append(f"candidate:risk_level:{risk_level}")
        if _candidate_requires_approval(candidate):
            score += 0.28
            evidence.append("candidate:requires_approval")
        if _candidate_has_side_effect(candidate):
            score += 0.20
            evidence.append("candidate:external_side_effect")
        auth = str(candidate.get("authorization") or candidate.get("authorization_status") or "").lower()
        if auth in {"unknown", "blocked", "missing", "stale"}:
            score += 0.25
            evidence.append(f"candidate:authorization:{auth}")
        return _clamp(score), _dedupe(evidence)

    def _recommended_depth(
        self,
        *,
        overall: float,
        risk: float,
        value: float,
        mutual: float,
        learning: float,
        signals: SignalSet,
        signal_items: list[dict[str, Any]],
        active_tensions: list[Tension],
        life: LifeState,
        candidate: dict[str, Any],
    ) -> RecommendedDepth:
        has_goal = bool(signals.task_context and (signals.task_context.active_goal or signals.task_context.user_goal))
        action_family = str(candidate.get("action_family") or candidate.get("family") or "").lower()
        is_tool = action_family == OpenActionFamily.USE_TOOL.value or bool(candidate.get("tools_needed") or candidate.get("tool_names"))
        inhibited = (
            _life_metric(life, "fatigue") >= 0.75
            or _life_metric(life, "restraint") >= 0.82
            or life.life_cycle == "cooldown"
        )
        simple_chat = _is_simple_chat(signal_items, has_goal=has_goal)
        direct_world_chat = _is_direct_world_chat(signal_items)

        if risk >= self.thresholds["high_risk"]:
            if is_tool and overall >= self.thresholds["draft_at"]:
                return RecommendedDepth.SANDBOX
            return RecommendedDepth.REPORT if overall >= self.thresholds["none_below"] else RecommendedDepth.NONE
        if risk >= self.thresholds["medium_risk"] or inhibited:
            if is_tool and overall >= self.thresholds["draft_at"] and not inhibited:
                return RecommendedDepth.SANDBOX
            return RecommendedDepth.REPORT if overall >= self.thresholds["none_below"] else RecommendedDepth.NONE
        if simple_chat and not has_goal and value < 0.20:
            if direct_world_chat and _simple_chat_action_ready(
                overall=overall,
                risk=risk,
                mutual=mutual,
                life=life,
                signal_items=signal_items,
                active_tensions=active_tensions,
                thresholds=self.thresholds,
                inhibited=inhibited,
            ):
                return RecommendedDepth.DRAFT
            return RecommendedDepth.REPORT if overall >= self.thresholds["draft_at"] else RecommendedDepth.NONE
        if candidate.get("world_publish") and overall >= self.thresholds["world_publish_at"]:
            return RecommendedDepth.WORLD_PUBLISH
        if candidate.get("bubble") and overall >= self.thresholds["bubble_at"]:
            return RecommendedDepth.BUBBLE
        if is_tool and overall >= self.thresholds["tool_at"] and _candidate_authorized(candidate):
            return RecommendedDepth.TOOL
        if has_goal and overall >= self.thresholds["continue_at"] and value >= 0.35:
            return RecommendedDepth.CONTINUE_TURN
        if overall >= self.thresholds["draft_at"] or learning >= 0.35:
            return RecommendedDepth.DRAFT
        if overall >= self.thresholds["none_below"]:
            return RecommendedDepth.REPORT
        return RecommendedDepth.NONE


def _signal_items(signal_set: SignalSet) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group, value in signal_set.signals.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            normalized = dict(item) if isinstance(item, dict) else {"value": item}
            normalized["_group"] = str(group)
            items.append(normalized)
    return items


def _active_tensions(tension_set: TensionSet) -> list[Tension]:
    return [
        tension
        for tension in [*tension_set.core_tensions, *tension_set.dynamic_tensions]
        if tension.activation > 0.0 or str(tension.metadata.get("status") or "").lower() == "active"
    ]


def _candidate_view(candidate: OpenIntent | dict[str, Any] | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    if isinstance(candidate, OpenIntent):
        return candidate.to_dict()
    if isinstance(candidate, dict):
        return dict(candidate)
    if is_dataclass(candidate) and hasattr(candidate, "to_dict"):
        return candidate.to_dict()
    return {"value": candidate}


def _matches(item: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("_group", "code", "kind", "type", "level", "status", "reason", "summary", "value")
    ).lower()
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        haystack = f"{haystack} {' '.join(str(value) for value in metadata.values()).lower()}"
    return any(needle in haystack for needle in needles)


def _item_evidence(item: dict[str, Any]) -> list[str]:
    group = str(item.get("_group", "signal"))
    code = str(item.get("code") or item.get("kind") or item.get("type") or "value")
    evidence = [f"signal:{group}:{code}"]
    evidence.extend(f"event:{event_id}" for event_id in item.get("event_ids") or [])
    return evidence


def _tension_evidence(tension: Tension) -> list[str]:
    evidence = [f"tension:{tension.tension_type.value}:{tension.tension_id}"]
    evidence.extend(f"tension_evidence:{item}" for item in tension.evidence)
    return evidence


def _severity_weight(item: dict[str, Any]) -> float:
    level = str(item.get("level") or item.get("status") or "").lower()
    return {
        "info": 0.05,
        "low": 0.10,
        "medium": 0.22,
        "high": 0.36,
        "critical": 0.50,
        "allowed": 0.14,
        "unknown": 0.22,
        "blocked": 0.32,
    }.get(level, 0.12)


def _risk_weight(item: dict[str, Any]) -> float:
    level = str(item.get("level") or item.get("status") or "").lower()
    code = str(item.get("code") or "").lower()
    base = {
        "low": 0.06,
        "medium": 0.18,
        "high": 0.34,
        "critical": 0.55,
        "unknown": 0.22,
        "blocked": 0.36,
        "allowed": 0.02,
    }.get(level, 0.10)
    if any(token in code for token in ("approval", "settlement", "rent", "blocked", "unknown")):
        base += 0.12
    return base


def _readiness(life: LifeState) -> float:
    return _clamp(
        (
            _life_metric(life, "energy")
            + _life_metric(life, "health")
            + _life_metric(life, "wakefulness")
        )
        / 3.0
        - _life_metric(life, "fatigue") * 0.25
        - _life_metric(life, "restraint") * 0.15
    )


def _life_metric(life: LifeState, field: str) -> float:
    return _clamp(getattr(life, field, 0.0))


def _is_simple_chat(items: list[dict[str, Any]], *, has_goal: bool) -> bool:
    if has_goal or not items:
        return False
    has_social = any(_matches(item, ("chat", "message", "social", "relationship")) for item in items)
    has_goal_signal = any(_matches(item, ("need", "goal", "requirement", "opportunity", "risk")) for item in items)
    return has_social and not has_goal_signal


def _has_relationship_signal(items: list[dict[str, Any]]) -> bool:
    return any(_matches(item, ("relationship", "social", "chat", "message")) for item in items)


def _is_direct_world_chat(items: list[dict[str, Any]]) -> bool:
    for item in items:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        subject = str(metadata.get("subject") or "")
        event_type = str(metadata.get("event_type") or "")
        chat_kind = str(metadata.get("chat_kind") or "")
        if chat_kind == "linz_world_direct":
            return True
        if subject == "wsp.chat.message.sent" and event_type == "message.sent":
            return True
        if subject.startswith("wsp.") and subject.count(".") == 1 and event_type == "wsp.chat.message.sent":
            return True
    return False


def _simple_chat_action_ready(
    *,
    overall: float,
    risk: float,
    mutual: float,
    life: LifeState,
    signal_items: list[dict[str, Any]],
    active_tensions: list[Tension],
    thresholds: dict[str, float],
    inhibited: bool,
) -> bool:
    if inhibited or risk >= thresholds["medium_risk"]:
        return False
    if not _logged_in_for_world_chat(signal_items):
        return False
    if (
        _readiness(life) < 0.55
        or _life_metric(life, "energy") < 0.30
        or _life_metric(life, "health") < 0.55
        or _life_metric(life, "wakefulness") < 0.45
    ):
        return False
    if _constraint_activation(active_tensions, signal_items) >= 0.55:
        return False
    social_activation = _social_activation(active_tensions)
    social_pressure = max(mutual, social_activation, _life_metric(life, "social_hunger"))
    return social_pressure >= 0.18 and (overall >= thresholds["none_below"] or social_pressure >= 0.35)


def _logged_in_for_world_chat(items: list[dict[str, Any]]) -> bool:
    for item in items:
        if _is_allowed_authorization_signal(item):
            return True
    return False


def _social_activation(active_tensions: list[Tension]) -> float:
    social = [
        tension.activation
        for tension in active_tensions
        if tension.tension_type == TensionType.SOCIAL_SIGNAL
    ]
    return max(social, default=0.0)


def _constraint_activation(active_tensions: list[Tension], signal_items: list[dict[str, Any]] | None = None) -> float:
    constraints = [
        tension.activation
        for tension in active_tensions
        if tension.tension_type == TensionType.CONSTRAINT
    ]
    activation = max(constraints, default=0.0)
    if signal_items and _current_allowed_direct_world_chat(signal_items):
        return _clamp(activation * 0.25)
    return activation


def _current_allowed_direct_world_chat(items: list[dict[str, Any]]) -> bool:
    if not _is_direct_world_chat(items) or not _logged_in_for_world_chat(items):
        return False
    for item in items:
        if _is_allowed_authorization_signal(item):
            continue
        if str(item.get("_group") or "").lower() == "risks":
            return False
        if _matches(item, ("approval", "settlement", "rent", "constraint", "credential", "secret", "token")):
            return False
    return True


def _is_allowed_authorization_signal(item: dict[str, Any]) -> bool:
    group = str(item.get("_group") or "").lower()
    code = str(item.get("code") or "").lower()
    status = str(item.get("status") or item.get("level") or "").lower()
    return group == "world_authorization" and code == "world_authorization_allowed" and status == "allowed"


def _candidate_has_side_effect(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("external_side_effect")
        or candidate.get("side_effect")
        or candidate.get("world_publish")
        or candidate.get("requires_settlement")
        or candidate.get("tools_needed")
        or candidate.get("tool_names")
    )


def _candidate_requires_approval(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("requires_approval")
        or candidate.get("approval_required")
        or str(candidate.get("approval") or "").lower() in {"required", "unknown"}
    )


def _candidate_authorized(candidate: dict[str, Any]) -> bool:
    auth = str(candidate.get("authorization") or candidate.get("authorization_status") or "").lower()
    return auth in {"allowed", "approved", "current", "granted", "explicit"}


def _safe_candidate_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _enum_value(value)
        for key, value in candidate.items()
        if str(key).lower() not in {"token", "api_key", "secret"}
    }


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_enum_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _enum_value(item) for key, item in value.items()}
    return value


def _rationale(depth: RecommendedDepth, overall: float, risk: float) -> str:
    return f"recommended_depth={depth.value}; overall_score={overall:.2f}; risk_cost={risk:.2f}"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 6)))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
