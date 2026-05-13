"""Copy-on-write tension field maintenance for os_runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent.os_runtime.domain import (
    LifeState,
    SignalSet,
    Tension,
    TensionNetworkDelta,
    TensionOperation,
    TensionOperationType,
    TensionSet,
    TensionType,
)


class TensionFieldEngine:
    """Apply interpreted operations to a tension network without side effects."""

    rule_version = "tension_field.v1"

    def update(
        self,
        previous_tensions: TensionSet | None,
        operations: list[TensionOperation] | None,
        signal_set: SignalSet | None = None,
        life_state: LifeState | None = None,
    ) -> tuple[TensionSet, TensionNetworkDelta]:
        previous = previous_tensions or TensionSet()
        current = deepcopy(previous)
        life = life_state or LifeState(restraint=0.2)
        delta = TensionNetworkDelta(
            operations=list(operations or []),
            propagation_edges=[],
            metadata={"rule_version": self.rule_version},
        )

        for operation in operations or []:
            kind = _operation_type(operation)
            if kind == TensionOperationType.GENERATE:
                self._generate(current, operation, life, delta)
            elif kind == TensionOperationType.UPDATE:
                self._update(current, operation, life, delta)
            elif kind == TensionOperationType.MERGE:
                self._merge(current, operation, life, delta)
            elif kind == TensionOperationType.HIBERNATE:
                self._hibernate(current, operation, delta)
            elif kind == TensionOperationType.ELIMINATE:
                self._eliminate(current, operation, delta)
            else:
                delta.rejected_operations.append(operation)

        self._refresh_edges(current, operations or [], signal_set, life, delta)
        current.propagation_edges = _dedupe_edges([*current.propagation_edges, *delta.propagation_edges])
        current.metadata = {
            **current.metadata,
            "rule_version": self.rule_version,
            "active_tension_count": len(delta.activated_tensions),
            "hibernated_tension_count": len(delta.hibernated_tensions),
            "eliminated_tension_count": len(delta.eliminated_tensions),
        }
        return current, delta

    def _generate(
        self,
        tension_set: TensionSet,
        operation: TensionOperation,
        life: LifeState,
        delta: TensionNetworkDelta,
    ) -> None:
        existing = _find(tension_set, operation.tension_id)
        if existing:
            self._apply_update(existing, operation, life)
            delta.activated_tensions.append(existing.tension_id)
            return
        intensity = _clamp(0.20 + operation.intensity_delta)
        tension = Tension(
            tension_id=operation.tension_id,
            tension_type=operation.tension_type or TensionType.UNCERTAINTY,
            intensity=intensity,
            trend=operation.intensity_delta,
            trend_slope=operation.intensity_delta,
            baseline=_clamp(intensity * 0.50),
            activation=_activation(intensity, life),
            confidence=_confidence(operation, 0.20),
            summary=str(operation.metadata.get("summary") or operation.reason),
            evidence=_dedupe(operation.evidence),
            metadata={
                "status": "active",
                "operation": "generate",
                "influence_weight": _influence_weight(operation, life),
            },
        )
        if operation.metadata.get("core") or tension.tension_type == TensionType.MEMORY_RESONANCE:
            tension_set.core_tensions.append(tension)
        else:
            tension_set.dynamic_tensions.append(tension)
        delta.activated_tensions.append(tension.tension_id)

    def _update(
        self,
        tension_set: TensionSet,
        operation: TensionOperation,
        life: LifeState,
        delta: TensionNetworkDelta,
    ) -> None:
        tension = _find(tension_set, operation.tension_id)
        if tension is None:
            degraded = deepcopy(operation)
            degraded.operation = TensionOperationType.GENERATE
            degraded.metadata = {**degraded.metadata, "degraded_from": "update"}
            self._generate(tension_set, degraded, life, delta)
            delta.metadata.setdefault("degraded_operations", []).append(operation.tension_id)
            return
        self._apply_update(tension, operation, life)
        delta.activated_tensions.append(tension.tension_id)

    def _apply_update(self, tension: Tension, operation: TensionOperation, life: LifeState) -> None:
        old_intensity = tension.intensity
        old_trend = tension.trend
        tension.intensity = _clamp(tension.intensity + operation.intensity_delta)
        tension.trend = round(tension.intensity - old_intensity, 6)
        tension.trend_slope = round(tension.trend - old_trend, 6)
        tension.baseline = _clamp((tension.baseline * 0.75) + (tension.intensity * 0.25))
        tension.activation = _activation(tension.intensity, life)
        tension.confidence = _clamp(tension.confidence + _confidence(operation, 0.08))
        tension.evidence = _dedupe([*tension.evidence, *operation.evidence])
        if operation.reason:
            tension.summary = operation.metadata.get("summary") or tension.summary or operation.reason
        tension.metadata = {
            **tension.metadata,
            "status": "active",
            "last_operation": operation.operation.value,
            "influence_weight": _influence_weight(operation, life),
        }

    def _merge(
        self,
        tension_set: TensionSet,
        operation: TensionOperation,
        life: LifeState,
        delta: TensionNetworkDelta,
    ) -> None:
        target = _find(tension_set, operation.tension_id)
        if target is None:
            delta.rejected_operations.append(operation)
            return
        source_ids = list(operation.metadata.get("source_ids") or operation.metadata.get("merge_from") or [])
        if not source_ids:
            delta.rejected_operations.append(operation)
            return
        for source_id in source_ids:
            source = _find(tension_set, source_id)
            if source is None:
                continue
            target.intensity = _clamp(max(target.intensity, source.intensity) + 0.05)
            target.baseline = _clamp((target.baseline + source.baseline) / 2.0)
            target.trend = _clamp(target.trend + source.trend, -1.0, 1.0)
            target.trend_slope = _clamp(target.trend_slope + source.trend_slope, -1.0, 1.0)
            target.activation = _activation(target.intensity, life)
            target.confidence = _clamp(max(target.confidence, source.confidence) + 0.05)
            target.evidence = _dedupe([*target.evidence, *source.evidence, *operation.evidence])
            target.metadata = {
                **target.metadata,
                "status": "active",
                "merged_from": _dedupe([*target.metadata.get("merged_from", []), source_id]),
            }
            _remove(tension_set, source_id)
            delta.propagation_edges.append(
                _edge(source_id, target.tension_id, "merge", 0.90, operation.evidence)
            )
        delta.activated_tensions.append(target.tension_id)

    def _hibernate(
        self,
        tension_set: TensionSet,
        operation: TensionOperation,
        delta: TensionNetworkDelta,
    ) -> None:
        tension = _find(tension_set, operation.tension_id)
        if tension is None:
            delta.rejected_operations.append(operation)
            return
        tension.activation = 0.0
        tension.trend = min(0.0, tension.trend)
        tension.metadata = {
            **tension.metadata,
            "status": "hibernating",
            "hibernate_reason": operation.reason,
        }
        delta.hibernated_tensions.append(tension.tension_id)

    def _eliminate(
        self,
        tension_set: TensionSet,
        operation: TensionOperation,
        delta: TensionNetworkDelta,
    ) -> None:
        if _find(tension_set, operation.tension_id) is None:
            delta.rejected_operations.append(operation)
            return
        _remove(tension_set, operation.tension_id)
        delta.eliminated_tensions.append(operation.tension_id)

    def _refresh_edges(
        self,
        tension_set: TensionSet,
        operations: list[TensionOperation],
        signal_set: SignalSet | None,
        life: LifeState,
        delta: TensionNetworkDelta,
    ) -> None:
        active = [
            tension
            for tension in [*tension_set.core_tensions, *tension_set.dynamic_tensions]
            if tension.activation > 0.0
        ]
        if len(active) < 2:
            return
        operation_ids = {operation.tension_id for operation in operations}
        for source in active:
            for target in active:
                if source.tension_id == target.tension_id:
                    continue
                if target.tension_id not in operation_ids and source.tension_id not in operation_ids:
                    continue
                relation = _relation(source, target)
                if not relation:
                    continue
                weight = _clamp(((source.activation + target.activation) / 2.0) * (1.0 - life.restraint * 0.25))
                delta.propagation_edges.append(
                    _edge(
                        source.tension_id,
                        target.tension_id,
                        relation,
                        weight,
                        _event_evidence(signal_set),
                    )
                )


def _operation_type(operation: TensionOperation) -> TensionOperationType:
    if isinstance(operation.operation, TensionOperationType):
        return operation.operation
    return TensionOperationType(operation.operation)


def _find(tension_set: TensionSet, tension_id: str) -> Tension | None:
    for tension in [*tension_set.core_tensions, *tension_set.dynamic_tensions]:
        if tension.tension_id == tension_id:
            return tension
    return None


def _remove(tension_set: TensionSet, tension_id: str) -> None:
    tension_set.core_tensions = [item for item in tension_set.core_tensions if item.tension_id != tension_id]
    tension_set.dynamic_tensions = [item for item in tension_set.dynamic_tensions if item.tension_id != tension_id]


def _activation(intensity: float, life: LifeState) -> float:
    readiness = (life.energy + life.wakefulness + life.health) / 3.0
    inhibition = (life.fatigue * 0.25) + (life.restraint * 0.35) + (life.boredom * 0.10)
    return _clamp(intensity * (0.65 + readiness * 0.35) * (1.0 - inhibition))


def _confidence(operation: TensionOperation, base: float) -> float:
    return _clamp(base + min(0.25, len(operation.evidence) * 0.04) + min(0.12, abs(operation.intensity_delta) * 0.20))


def _influence_weight(operation: TensionOperation, life: LifeState) -> float:
    return _clamp(abs(operation.intensity_delta) + 0.20 + life.wakefulness * 0.10 - life.restraint * 0.05)


def _relation(source: Tension, target: Tension) -> str:
    if source.tension_type == target.tension_type:
        return "same-type"
    if TensionType.CONSTRAINT in {source.tension_type, target.tension_type}:
        return "constraint-modulates"
    if TensionType.UNSATISFIED_GOAL in {source.tension_type, target.tension_type}:
        return "goal-influences"
    return ""


def _edge(source: str, target: str, relation: str, weight: float, evidence: list[str]) -> dict[str, Any]:
    return {
        "source_tension_id": source,
        "target_tension_id": target,
        "relation": relation,
        "influence_weight": _clamp(weight),
        "evidence": _dedupe(evidence),
    }


def _event_evidence(signal_set: SignalSet | None) -> list[str]:
    if not signal_set:
        return []
    return [f"event:{event.event_id}" for event in signal_set.event_refs if event.event_id]


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (
            str(edge.get("source_tension_id")),
            str(edge.get("target_tension_id")),
            str(edge.get("relation")),
        )
        if key not in unique:
            unique[key] = edge
    return list(unique.values())


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 6)))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


__all__ = ["TensionFieldEngine"]
