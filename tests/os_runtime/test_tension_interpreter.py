from agent.os_runtime.domain import (
    AgentContextView,
    EventSource,
    LifeState,
    OSRuntimeEventRef,
    SignalSet,
    TaskContextView,
    Tension,
    TensionOperationType,
    TensionSet,
    TensionType,
    WorldIdentityRef,
)
from agent.os_runtime.engine.tension_interpreter import TensionInterpreter


def _event():
    return OSRuntimeEventRef("evt-1", EventSource.LINZ_WORLD, summary="world requirement requires approval")


def _signal(code, group, *, level="medium", status="", event_ids=None):
    return {
        "code": code,
        "level": level,
        "status": status,
        "reason": code,
        "event_ids": event_ids or ["evt-1"],
    }, group


def _signal_set(*signals, task_context=None, agent_context=None):
    grouped = {}
    for item, group in signals:
        grouped.setdefault(group, []).append(item)
    return SignalSet(
        event_refs=[_event()],
        task_context=task_context,
        agent_context=agent_context,
        signals=grouped,
    )


def _operations_by_type(interpretation):
    return {operation.operation for operation in interpretation.operations}


def test_interpreter_generates_goal_and_risk_operations_with_auditable_explanation():
    task_context = TaskContextView(user_goal="finish feature", active_goal="ship module 3")
    signal_set = _signal_set(
        _signal("context_active_goal", "needs"),
        _signal("world_requirement_opportunity", "world_opportunities"),
        _signal("network_send", "risks", level="high"),
        _signal("world_authorization_map_blocked", "world_authorization", status="blocked"),
        task_context=task_context,
    )

    interpretation = TensionInterpreter().interpret(
        _event(),
        signal_set,
        task_context,
        LifeState(creative_pressure=0.4, restraint=0.7),
        TensionSet(),
    )

    assert TensionOperationType.GENERATE in _operations_by_type(interpretation)
    assert "goal-vs-current-state" in interpretation.detected_conflicts
    assert "value-benefit-vs-risk-constraint" in interpretation.detected_conflicts
    assert any(operation.tension_type == TensionType.UNSATISFIED_GOAL for operation in interpretation.operations)
    assert any(operation.tension_type == TensionType.CONSTRAINT for operation in interpretation.operations)
    assert any("event:evt-1" in operation.evidence for operation in interpretation.operations)
    assert "operations" in interpretation.explanation


def test_interpreter_covers_update_merge_hibernate_eliminate_without_mutating_previous_set():
    task_context = TaskContextView(active_goal="complete approved goal")
    previous = TensionSet(
        dynamic_tensions=[
            Tension(
                "goal:unsatisfied",
                TensionType.UNSATISFIED_GOAL,
                intensity=0.5,
                activation=0.6,
                evidence=["evt-old"],
            ),
            Tension(
                "goal:duplicate",
                TensionType.UNSATISFIED_GOAL,
                intensity=0.4,
                activation=0.5,
                evidence=["evt-dup"],
            ),
            Tension(
                "social:stale",
                TensionType.SOCIAL_SIGNAL,
                intensity=0.03,
                activation=0.02,
                evidence=["evt-low"],
            ),
            Tension(
                "constraint:done",
                TensionType.CONSTRAINT,
                intensity=0.2,
                activation=0.2,
                evidence=["evt-done"],
                metadata={"status": "resolved"},
            ),
        ]
    )
    before = previous.to_dict()
    signal_set = _signal_set(
        _signal("context_active_goal", "needs"),
        _signal("goal_completed_success", "feedback", status="completed"),
        task_context=task_context,
    )

    interpretation = TensionInterpreter().interpret(_event(), signal_set, task_context, LifeState(), previous)

    assert {
        TensionOperationType.UPDATE,
        TensionOperationType.MERGE,
        TensionOperationType.HIBERNATE,
        TensionOperationType.ELIMINATE,
    } <= _operations_by_type(interpretation)
    assert previous.to_dict() == before
    assert any(operation.metadata.get("source_ids") == ["goal:duplicate"] for operation in interpretation.operations)


def test_interpreter_maps_social_and_memory_signals():
    task_context = TaskContextView()
    agent_context = AgentContextView(
        memory_summary="The soul remembers collaborative obligations.",
        world_identity=WorldIdentityRef(memory_summary_available=True),
    )
    signal_set = _signal_set(
        _signal("relationship_record", "relationships"),
        _signal("chat_message_received", "relationships"),
        _signal("soul_memory_summary", "feedback"),
        task_context=task_context,
        agent_context=agent_context,
    )

    interpretation = TensionInterpreter().interpret(_event(), signal_set, task_context, LifeState(), TensionSet())

    assert "social-connection-vs-focus" in interpretation.detected_conflicts
    assert "memory-resonance-vs-present-context" in interpretation.detected_conflicts
    assert any(operation.tension_type == TensionType.SOCIAL_SIGNAL for operation in interpretation.operations)
    assert any(operation.tension_type == TensionType.MEMORY_RESONANCE for operation in interpretation.operations)
