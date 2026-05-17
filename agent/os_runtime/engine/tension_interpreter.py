"""Rule-based explanation of tension operations from os_runtime signals."""

from __future__ import annotations

from typing import Any

from agent.os_runtime.domain import (
    LifeState,
    OSRuntimeEventRef,
    SignalSet,
    TaskContextView,
    Tension,
    TensionExplanation,
    TensionInterpretation,
    TensionOperation,
    TensionOperationType,
    TensionSet,
    TensionType,
)


class TensionInterpreter:
    """Convert signals into auditable operations without mutating tensions."""

    rule_version = "tension_interpreter.v1"

    def interpret(
        self,
        event_ref: OSRuntimeEventRef | None,
        signal_set: SignalSet | None,
        task_context: TaskContextView | None,
        life_state: LifeState | None,
        previous_tensions: TensionSet | None,
    ) -> TensionInterpretation:
        signals = signal_set or SignalSet()
        task = task_context or signals.task_context or TaskContextView()
        life = life_state or LifeState()
        previous = previous_tensions or TensionSet()
        event_id = _event_id(event_ref, signals)
        items = _signal_items(signals)

        operations: list[TensionOperation] = []
        conflicts: list[str] = []
        evidence: list[str] = []

        goal_evidence = _evidence_for(items, ("need", "goal", "requirement", "opportunity"))
        if task.active_goal:
            goal_evidence.append("task_context:active_goal")
        if task.user_goal:
            goal_evidence.append("task_context:user_goal")
        if goal_evidence:
            tension_id = _existing_id(previous, TensionType.UNSATISFIED_GOAL) or "goal:unsatisfied"
            operation = _operation(
                TensionOperationType.UPDATE if _has_tension(previous, tension_id) else TensionOperationType.GENERATE,
                tension_id,
                TensionType.UNSATISFIED_GOAL,
                0.18 + life.creative_pressure * 0.10,
                "Unfinished goal or world requirement remains unresolved.",
                [event_id, *goal_evidence],
                conflict="goal-vs-current-state",
                summary=task.active_goal or task.user_goal or "unsatisfied goal",
            )
            operations.append(operation)
            conflicts.append("goal-vs-current-state")
            evidence.extend(operation.evidence)

        world_evidence = _evidence_for(items, ("requirement", "order", "world_opportunity"))
        if world_evidence:
            operation = _operation(
                TensionOperationType.GENERATE,
                "value:world-opportunity",
                TensionType.VALUE_CONFLICT,
                0.12,
                "World requirement or order creates value opportunity pressure.",
                [event_id, *world_evidence],
                conflict="value-opportunity-vs-capacity",
            )
            operations.append(operation)
            conflicts.append("value-opportunity-vs-capacity")
            evidence.extend(operation.evidence)

        risk_evidence = _risk_evidence_for(items)
        if risk_evidence or life.restraint >= 0.65:
            tension_id = _existing_id(previous, TensionType.CONSTRAINT) or "constraint:risk"
            operation = _operation(
                TensionOperationType.UPDATE if _has_tension(previous, tension_id) else TensionOperationType.GENERATE,
                tension_id,
                TensionType.CONSTRAINT,
                0.22 + min(0.12, life.restraint * 0.10),
                "Risk, authorization, approval, settlement, or rent constraint limits action.",
                [event_id, *risk_evidence],
                conflict="value-benefit-vs-risk-constraint",
            )
            operations.append(operation)
            conflicts.append("value-benefit-vs-risk-constraint")
            evidence.extend(operation.evidence)

        social_evidence = _evidence_for(items, ("relationship", "chat", "message", "social"))
        if social_evidence:
            operation = _operation(
                TensionOperationType.GENERATE,
                "social:relationship",
                TensionType.SOCIAL_SIGNAL,
                0.11 + life.social_hunger * 0.05,
                "Chat or relationship signal creates social response tension.",
                [event_id, *social_evidence],
                conflict="social-connection-vs-focus",
            )
            operations.append(operation)
            conflicts.append("social-connection-vs-focus")
            evidence.extend(operation.evidence)

        memory_evidence = _memory_evidence(signals, items)
        if memory_evidence:
            operation = _operation(
                TensionOperationType.UPDATE
                if _has_tension(previous, "memory:soul-summary")
                else TensionOperationType.GENERATE,
                "memory:soul-summary",
                TensionType.MEMORY_RESONANCE,
                0.10,
                "Soul Memory summary resonates with current value interpretation.",
                [event_id, *memory_evidence],
                conflict="memory-resonance-vs-present-context",
            )
            operations.append(operation)
            conflicts.append("memory-resonance-vs-present-context")
            evidence.extend(operation.evidence)

        operations.extend(_merge_operations(previous, event_id))
        operations.extend(_hibernate_operations(previous, event_id))
        operations.extend(_eliminate_operations(previous, event_id, items))
        for operation in operations:
            conflicts.extend(operation.metadata.get("conflicts", []))
            evidence.extend(operation.evidence)

        explanation = TensionExplanation(
            event_id=event_id,
            detected_conflicts=_dedupe(conflicts),
            operation_reasons=[operation.reason for operation in operations],
            evidence=_dedupe(evidence),
            summary=_summary(operations),
            metadata={"rule_version": self.rule_version},
        )
        return TensionInterpretation(
            event_id=event_id,
            detected_conflicts=explanation.detected_conflicts,
            operations=operations,
            explanation=explanation.summary,
            evidence=explanation.evidence,
            metadata={
                "rule_version": self.rule_version,
                "explanation": explanation.to_dict(),
            },
        )


def _operation(
    operation: TensionOperationType,
    tension_id: str,
    tension_type: TensionType,
    intensity_delta: float,
    reason: str,
    evidence: list[str],
    *,
    conflict: str,
    summary: str = "",
) -> TensionOperation:
    return TensionOperation(
        operation=operation,
        tension_id=tension_id,
        tension_type=tension_type,
        intensity_delta=round(float(intensity_delta), 6),
        reason=reason,
        evidence=_dedupe(evidence),
        metadata={
            "conflicts": [conflict],
            "summary": summary or reason,
        },
    )


def _merge_operations(previous: TensionSet, event_id: str) -> list[TensionOperation]:
    operations: list[TensionOperation] = []
    by_type: dict[TensionType, list[Tension]] = {}
    for tension in [*previous.core_tensions, *previous.dynamic_tensions]:
        by_type.setdefault(tension.tension_type, []).append(tension)
    for tension_type, tensions in by_type.items():
        active = [item for item in tensions if item.activation >= 0.20 and item.intensity >= 0.10]
        if len(active) < 2:
            continue
        target = active[0]
        source = active[1]
        operations.append(
            TensionOperation(
                operation=TensionOperationType.MERGE,
                tension_id=target.tension_id,
                tension_type=tension_type,
                intensity_delta=0.0,
                reason="Similar active tensions should be merged to preserve a stable network.",
                evidence=_dedupe([event_id, *target.evidence, *source.evidence]),
                metadata={
                    "source_ids": [source.tension_id],
                    "conflicts": ["duplicate-tension-vs-network-clarity"],
                    "summary": f"merge {source.tension_id} into {target.tension_id}",
                },
            )
        )
        break
    return operations


def _hibernate_operations(previous: TensionSet, event_id: str) -> list[TensionOperation]:
    operations: list[TensionOperation] = []
    for tension in previous.dynamic_tensions:
        if tension.intensity <= 0.08 or tension.activation <= 0.05:
            operations.append(
                TensionOperation(
                    operation=TensionOperationType.HIBERNATE,
                    tension_id=tension.tension_id,
                    tension_type=tension.tension_type,
                    reason="Low activation tension should hibernate instead of driving action.",
                    evidence=_dedupe([event_id, *tension.evidence]),
                    metadata={"conflicts": ["low-activation-vs-action-readiness"]},
                )
            )
            break
    return operations


def _eliminate_operations(previous: TensionSet, event_id: str, items: list[dict[str, Any]]) -> list[TensionOperation]:
    operations: list[TensionOperation] = []
    has_resolution = bool(_evidence_for(items, ("resolved", "completed", "success")))
    for tension in [*previous.dynamic_tensions, *previous.core_tensions]:
        status = str(tension.metadata.get("status") or "").lower()
        if status in {"resolved", "completed", "eliminate"} or has_resolution and tension.tension_type == TensionType.UNSATISFIED_GOAL:
            operations.append(
                TensionOperation(
                    operation=TensionOperationType.ELIMINATE,
                    tension_id=tension.tension_id,
                    tension_type=tension.tension_type,
                    reason="Resolved or contradicted tension should be eliminated.",
                    evidence=_dedupe([event_id, *tension.evidence]),
                    metadata={"conflicts": ["resolved-state-vs-stale-tension"]},
                )
            )
            break
    return operations


def _signal_items(signal_set: SignalSet) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group, value in signal_set.signals.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            normalized = dict(item) if isinstance(item, dict) else {"value": item}
            normalized["_group"] = str(group)
            items.append(normalized)
    return items


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


def _risk_evidence_for(items: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for item in items:
        if not _matches(item, ("risk", "authorization", "approval", "settlement", "rent", "constraint")):
            continue
        if _is_allowed_authorization_signal(item):
            continue
        group = str(item.get("_group", "signal"))
        code = str(item.get("code") or item.get("kind") or item.get("type") or "value")
        evidence.append(f"signal:{group}:{code}")
        for event_id in item.get("event_ids") or []:
            evidence.append(f"event:{event_id}")
    return evidence


def _memory_evidence(signal_set: SignalSet, items: list[dict[str, Any]]) -> list[str]:
    evidence = _evidence_for(items, ("memory", "soul"))
    agent_context = signal_set.agent_context
    if agent_context and agent_context.memory_summary:
        evidence.append("agent_context:memory_summary")
    if agent_context and agent_context.world_identity and agent_context.world_identity.memory_summary_available:
        evidence.append("world_identity:memory_summary_available")
    return evidence


def _matches(item: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("_group", "code", "kind", "type", "level", "status", "reason", "summary", "value")
    ).lower()
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        haystack = f"{haystack} {' '.join(str(value) for value in metadata.values()).lower()}"
    return any(needle in haystack for needle in needles)


def _is_allowed_authorization_signal(item: dict[str, Any]) -> bool:
    group = str(item.get("_group") or "").lower()
    code = str(item.get("code") or "").lower()
    status = str(item.get("status") or item.get("level") or "").lower()
    return group == "world_authorization" and code == "world_authorization_allowed" and status == "allowed"


def _event_id(event_ref: OSRuntimeEventRef | None, signal_set: SignalSet) -> str:
    if event_ref and event_ref.event_id:
        return event_ref.event_id
    if signal_set.event_refs:
        return signal_set.event_refs[0].event_id
    return "event:unknown"


def _has_tension(tensions: TensionSet, tension_id: str) -> bool:
    return any(item.tension_id == tension_id for item in [*tensions.core_tensions, *tensions.dynamic_tensions])


def _existing_id(tensions: TensionSet, tension_type: TensionType) -> str:
    for item in [*tensions.core_tensions, *tensions.dynamic_tensions]:
        if item.tension_type == tension_type:
            return item.tension_id
    return ""


def _summary(operations: list[TensionOperation]) -> str:
    if not operations:
        return "No tension operation was needed for the event."
    kinds = ", ".join(_dedupe([operation.operation.value for operation in operations]))
    reasons = "; ".join(_dedupe([operation.reason for operation in operations]))
    return f"Event produced {kinds} operations: {reasons}"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


__all__ = ["TensionInterpreter"]
