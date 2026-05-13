from agent.os_runtime.domain import EventSource, LifeState, OSRuntimeEventRef, SignalSet, TaskContextView
from agent.os_runtime.engine.life_state import LifeStateSystem


def _signal(code, *, group="feedback", level="medium", status="", event_ids=None, reason=""):
    return {
        "code": code,
        "level": level,
        "status": status,
        "reason": reason or code,
        "event_ids": event_ids or ["evt-1"],
    }, group


def _signal_set(*signals, metadata=None, task_context=None):
    grouped = {}
    for item, group in signals:
        grouped.setdefault(group, []).append(item)
    return SignalSet(
        event_refs=[OSRuntimeEventRef("evt-1", EventSource.RUNTIME_FEEDBACK)],
        task_context=task_context,
        signals=grouped,
        metadata=metadata or {},
    )


def test_life_state_initializes_deterministically_when_signal_set_is_empty():
    state, delta = LifeStateSystem().update(SignalSet())

    assert state.life_cycle == "active"
    assert state.recovery_cycle == "stable"
    assert state.health == 1.0
    assert state.restraint == 0.2
    assert "life_state:initialized" in delta.evidence
    assert delta.current.to_dict() == state.to_dict()


def test_continuous_failures_and_high_risk_raise_restraint_and_lower_action_readiness():
    previous = LifeState(
        energy=0.8,
        fatigue=0.2,
        health=0.9,
        wakefulness=0.8,
        restraint=0.25,
        generated_intent_count=4,
        life_cycle="active",
    )
    signal_set = _signal_set(
        _signal("tool_failure_feedback", level="high"),
        _signal("test_failure_feedback", level="high"),
        _signal("network_send", group="risks", level="high"),
        _signal("world_authorization_map_blocked", group="world_authorization", status="blocked"),
        metadata={"consecutive_failures": 1},
    )

    state, delta = LifeStateSystem(max_generated_intents=5).update(
        signal_set,
        previous,
        execution_feedback={"status": "failed", "generated_intent": True},
    )

    assert state.fatigue > previous.fatigue
    assert state.restraint > previous.restraint
    assert state.energy < previous.energy
    assert state.wakefulness < previous.wakefulness
    assert state.life_cycle == "cooldown"
    assert delta.changes["fatigue"]["delta"] > 0
    assert any("failure" in reason for reason in delta.reasons)
    assert any("authorization" in item for item in delta.evidence)


def test_unfinished_goal_positive_feedback_and_silence_update_distinct_fields():
    task_context = TaskContextView(user_goal="ship module 3", active_goal="finish tension field")
    previous = LifeState(energy=0.9, fatigue=0.25, wakefulness=0.9, restraint=0.2)
    signal_set = _signal_set(
        _signal("context_active_goal", group="needs"),
        _signal("world_requirement_opportunity", group="world_opportunities"),
        _signal("positive_user_feedback", group="feedback", status="success"),
        _signal("duplicate_low_value_event", group="feedback"),
        metadata={"silence_seconds": 1800},
        task_context=task_context,
    )

    state, delta = LifeStateSystem().update(signal_set, previous, execution_feedback={"status": "completed"})

    assert state.curiosity > previous.curiosity
    assert state.creative_pressure > previous.creative_pressure
    assert state.silence_pressure > previous.silence_pressure
    assert state.boredom > previous.boredom
    assert state.restraint >= previous.restraint
    assert "task_context:active_goal" in delta.evidence
