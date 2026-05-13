from agent.os_runtime.domain import (
    EventSource,
    LifeState,
    OpenActionFamily,
    RecommendedDepth,
    RiskLevel,
    SignalSet,
    TaskContextView,
    Tension,
    TensionSet,
    TensionType,
    OSRuntimeEventRef,
)
from agent.os_runtime.engine.action_potential import ActionPotentialEvaluator, ALLOWED_RECOMMENDED_DEPTHS


def _signal(code, *, group="needs", level="medium", status="", reason="", event_ids=None):
    return {
        "code": code,
        "level": level,
        "status": status,
        "reason": reason or code,
        "event_ids": event_ids or ["evt-1"],
    }, group


def _signal_set(*signals, task_context=None):
    grouped = {}
    for item, group in signals:
        grouped.setdefault(group, []).append(item)
    return SignalSet(
        event_refs=[OSRuntimeEventRef("evt-1", EventSource.HERMES_CONVERSATION)],
        task_context=task_context,
        signals=grouped,
    )


def _tension(tension_type, *, intensity=0.7, activation=0.7, tension_id="tension-1"):
    return Tension(
        tension_id=tension_id,
        tension_type=tension_type,
        intensity=intensity,
        activation=activation,
        evidence=["evt-1"],
        metadata={"status": "active"},
    )


def test_recommended_depth_values_are_limited_to_spec_allowlist():
    assert ALLOWED_RECOMMENDED_DEPTHS == tuple(item.value for item in RecommendedDepth)
    assert set(ALLOWED_RECOMMENDED_DEPTHS) == {
        "none",
        "report",
        "draft",
        "continue_turn",
        "sandbox",
        "tool",
        "world_publish",
        "bubble",
    }


def test_simple_chat_does_not_trigger_self_driven_continuation():
    potential = ActionPotentialEvaluator().evaluate(
        signal_set=_signal_set(_signal("friendly_chat_message", group="relationships", level="low")),
        life_state=LifeState(energy=0.9, health=1.0, wakefulness=0.95, restraint=0.2),
    )

    assert potential.recommended_depth in {RecommendedDepth.NONE, RecommendedDepth.REPORT}
    assert potential.recommended_depth != RecommendedDepth.CONTINUE_TURN
    assert potential.overall_score < 0.18


def test_unfinished_low_risk_goal_can_recommend_continue_turn_with_evidence():
    potential = ActionPotentialEvaluator().evaluate(
        signal_set=_signal_set(
            _signal("context_active_goal", group="needs"),
            task_context=TaskContextView(user_goal="ship module 4", active_goal="finish action potential"),
        ),
        life_state=LifeState(
            energy=0.88,
            health=0.95,
            wakefulness=0.88,
            curiosity=0.5,
            creative_pressure=0.45,
            restraint=0.2,
        ),
        tension_set=TensionSet(
            dynamic_tensions=[
                _tension(TensionType.UNSATISFIED_GOAL, intensity=0.85, activation=0.80, tension_id="goal:unsatisfied")
            ]
        ),
    )

    assert potential.recommended_depth == RecommendedDepth.CONTINUE_TURN
    assert potential.value_potential > potential.risk_cost
    evidence = potential.metadata["score_evidence"]
    assert "task_context:active_goal" in evidence["value_potential"]
    assert "life_state:curiosity" in evidence["learning_potential"]
    assert any(item.startswith("config:threshold") for item in evidence["overall_score"])


def test_high_risk_tool_action_is_never_recommended_direct_tool():
    potential = ActionPotentialEvaluator().evaluate(
        signal_set=_signal_set(
            _signal("network_send_high_risk", group="risks", level="high"),
            task_context=TaskContextView(user_goal="deploy change", active_goal="run external command"),
        ),
        life_state=LifeState(energy=0.8, health=0.9, wakefulness=0.85, restraint=0.35),
        tension_set=TensionSet(
            dynamic_tensions=[
                _tension(TensionType.UNSATISFIED_GOAL, intensity=0.65, activation=0.6),
                _tension(TensionType.CONSTRAINT, intensity=0.7, activation=0.65, tension_id="constraint:risk"),
            ]
        ),
        candidate={
            "intent_id": "intent-tool",
            "action_family": OpenActionFamily.USE_TOOL,
            "risk_level": RiskLevel.HIGH,
            "requires_approval": True,
            "external_side_effect": True,
            "authorization": "unknown",
            "tools_needed": ["shell"],
        },
    )

    assert potential.risk_cost >= 0.68
    assert potential.recommended_depth in {
        RecommendedDepth.SANDBOX,
        RecommendedDepth.REPORT,
        RecommendedDepth.NONE,
    }
    assert potential.recommended_depth != RecommendedDepth.TOOL
    assert "candidate:requires_approval" in potential.metadata["score_evidence"]["risk_cost"]


def test_all_score_fields_have_traceable_evidence():
    potential = ActionPotentialEvaluator().evaluate(
        signal_set=_signal_set(
            _signal("event_need", group="needs"),
            _signal("memory_unknown", group="feedback", level="medium"),
            task_context=TaskContextView(user_goal="understand a new task"),
        ),
        life_state=LifeState(curiosity=0.4, restraint=0.2),
        tension_set=TensionSet(
            dynamic_tensions=[_tension(TensionType.MEMORY_RESONANCE, intensity=0.6, activation=0.5)]
        ),
    )

    evidence = potential.metadata["score_evidence"]
    for field in (
        "value_potential",
        "mutual_benefit_potential",
        "learning_potential",
        "risk_cost",
        "overall_score",
        "recommended_depth",
    ):
        assert evidence[field]
        assert any(item.startswith(("signal:", "tension:", "life_state:", "task_context:", "config:")) for item in evidence[field])
