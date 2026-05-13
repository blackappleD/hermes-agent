from agent.os_runtime.domain import (
    EventSource,
    LifeState,
    OSRuntimeEventRef,
    SignalSet,
    Tension,
    TensionOperation,
    TensionOperationType,
    TensionSet,
    TensionType,
)
from agent.os_runtime.engine.tension_field import TensionFieldEngine


def _operation(kind, tension_id, tension_type, delta=0.0, *, evidence=None, metadata=None):
    return TensionOperation(
        operation=kind,
        tension_id=tension_id,
        tension_type=tension_type,
        intensity_delta=delta,
        reason=f"{kind.value} {tension_id}",
        evidence=evidence or ["evt-1"],
        metadata=metadata or {},
    )


def _signal_set():
    return SignalSet(event_refs=[OSRuntimeEventRef("evt-1", EventSource.RUNTIME_FEEDBACK)])


def _ids(tensions):
    return {tension.tension_id for tension in tensions}


def test_field_engine_applies_generate_update_and_tracks_observable_network_fields():
    previous = TensionSet(
        dynamic_tensions=[
            Tension(
                "goal:unsatisfied",
                TensionType.UNSATISFIED_GOAL,
                intensity=0.4,
                trend=0.05,
                baseline=0.2,
                activation=0.3,
                confidence=0.2,
                evidence=["evt-old"],
            )
        ]
    )
    before = previous.to_dict()
    operations = [
        _operation(TensionOperationType.UPDATE, "goal:unsatisfied", TensionType.UNSATISFIED_GOAL, 0.25),
        _operation(TensionOperationType.GENERATE, "constraint:risk", TensionType.CONSTRAINT, 0.30),
    ]

    current, delta = TensionFieldEngine().update(
        previous,
        operations,
        _signal_set(),
        LifeState(energy=0.9, health=1.0, wakefulness=0.9, restraint=0.3),
    )

    assert previous.to_dict() == before
    goal = next(tension for tension in current.dynamic_tensions if tension.tension_id == "goal:unsatisfied")
    constraint = next(tension for tension in current.dynamic_tensions if tension.tension_id == "constraint:risk")
    assert goal.intensity > 0.4
    assert goal.trend > 0
    assert goal.trend_slope != 0
    assert goal.baseline > 0.2
    assert goal.activation > 0
    assert goal.confidence > 0.2
    assert "evt-1" in goal.evidence
    assert constraint.metadata["status"] == "active"
    assert {"goal:unsatisfied", "constraint:risk"} <= set(delta.activated_tensions)
    assert current.propagation_edges
    assert all("influence_weight" in edge for edge in current.propagation_edges)


def test_field_engine_applies_merge_hibernate_and_eliminate_with_delta_records():
    previous = TensionSet(
        core_tensions=[
            Tension("core:value", TensionType.VALUE_CONFLICT, intensity=0.6, activation=0.7, baseline=0.4)
        ],
        dynamic_tensions=[
            Tension("goal:primary", TensionType.UNSATISFIED_GOAL, intensity=0.5, activation=0.6, evidence=["evt-a"]),
            Tension("goal:duplicate", TensionType.UNSATISFIED_GOAL, intensity=0.45, activation=0.5, evidence=["evt-b"]),
            Tension("social:quiet", TensionType.SOCIAL_SIGNAL, intensity=0.04, activation=0.03),
            Tension("constraint:resolved", TensionType.CONSTRAINT, intensity=0.2, activation=0.2),
        ],
    )
    operations = [
        _operation(
            TensionOperationType.MERGE,
            "goal:primary",
            TensionType.UNSATISFIED_GOAL,
            metadata={"source_ids": ["goal:duplicate"]},
        ),
        _operation(TensionOperationType.HIBERNATE, "social:quiet", TensionType.SOCIAL_SIGNAL),
        _operation(TensionOperationType.ELIMINATE, "constraint:resolved", TensionType.CONSTRAINT),
    ]

    current, delta = TensionFieldEngine().update(previous, operations, _signal_set(), LifeState(restraint=0.2))

    dynamic_ids = _ids(current.dynamic_tensions)
    assert "goal:primary" in dynamic_ids
    assert "goal:duplicate" not in dynamic_ids
    assert "constraint:resolved" not in dynamic_ids
    quiet = next(tension for tension in current.dynamic_tensions if tension.tension_id == "social:quiet")
    assert quiet.activation == 0.0
    assert quiet.metadata["status"] == "hibernating"
    assert "social:quiet" in delta.hibernated_tensions
    assert "constraint:resolved" in delta.eliminated_tensions
    assert any(edge["relation"] == "merge" for edge in delta.propagation_edges)


def test_field_engine_degrades_update_for_unknown_tension_into_generate():
    operation = _operation(
        TensionOperationType.UPDATE,
        "goal:missing",
        TensionType.UNSATISFIED_GOAL,
        0.2,
    )

    current, delta = TensionFieldEngine().update(TensionSet(), [operation], _signal_set(), LifeState())

    assert "goal:missing" in _ids(current.dynamic_tensions)
    assert delta.metadata["degraded_operations"] == ["goal:missing"]
