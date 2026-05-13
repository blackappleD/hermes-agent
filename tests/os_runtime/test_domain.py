import json
from dataclasses import fields

from agent.os_runtime.domain import (
    ActionPotential,
    AgentContextView,
    ArbitrationDecision,
    ArbitrationResult,
    BubbleLifecycle,
    BubbleSpec,
    EventSource,
    EvidencePackage,
    ExecutionReceipt,
    LifeState,
    LifeStateDelta,
    OpenActionFamily,
    OpenIntent,
    OpenSpace,
    OSRuntimeEventRef,
    PermissionTicket,
    RiskLevel,
    RuleCrystal,
    RuleMaturity,
    SelfPrompt,
    SignalSet,
    TargetDirection,
    TaskContextView,
    Tension,
    TensionExplanation,
    TensionInterpretation,
    TensionNetworkDelta,
    TensionOperation,
    TensionOperationType,
    TensionSet,
    TensionType,
    WorldIdentityRef,
)


def _round_trip(instance):
    payload = instance.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    restored = type(instance).from_dict(json.loads(encoded))
    assert restored.to_dict() == payload
    return restored


def test_core_enum_values_are_stable():
    assert EventSource.LINZ_WORLD.value == "linz_world"
    assert TensionType.VALUE_CONFLICT.value == "value_conflict"
    assert TensionOperationType.GENERATE.value == "generate"
    assert OpenActionFamily.USE_TOOL.value == "use_tool"
    assert RiskLevel.MEDIUM.value == "medium"
    assert BubbleLifecycle.PROPOSED.value == "proposed"
    assert [item.value for item in RuleMaturity] == ["R0", "R1", "R2", "R3", "R4"]


def test_arbitration_decision_uses_new_protocol_values_only():
    assert [item.value for item in ArbitrationDecision] == [
        "auto_execute",
        "sandbox_execute",
        "require_approval",
        "report_only",
        "reject",
    ]
    assert "allow_reply" not in {item.value for item in ArbitrationDecision}
    assert "allow_draft" not in {item.value for item in ArbitrationDecision}
    assert "allow_sandbox" not in {item.value for item in ArbitrationDecision}


def test_world_identity_ref_is_read_only_identity_view():
    names = {item.name for item in fields(WorldIdentityRef)}
    assert {"os_id", "soul_id", "os_name", "account_id"} <= names
    assert "token" not in names
    assert "login" not in names
    assert "registry" not in names


def test_context_views_do_not_replace_runtime_infrastructure():
    task_names = {item.name for item in fields(TaskContextView)}
    agent_names = {item.name for item in fields(AgentContextView)}
    forbidden = {
        "session_db",
        "memory_manager",
        "context_engine",
        "tool_registry",
    }
    assert task_names.isdisjoint(forbidden)
    assert agent_names.isdisjoint(forbidden)


def test_nested_round_trip_preserves_chinese_trace_timestamp_and_metadata():
    event = OSRuntimeEventRef(
        event_id="evt-1",
        source=EventSource.LINZ_WORLD,
        trace_id="trace-中文-001",
        session_id="session-1",
        timestamp="2026-05-12T05:58:46+08:00",
        summary="世界事件：新的关系信号",
        metadata={"unknown_future_key": {"保留": True}},
    )
    identity = WorldIdentityRef(
        os_id="os-1",
        soul_id="soul-1",
        os_name="元神甲",
        account_id="acct-1",
        authorization_state="mapped",
        map_version="map-v1",
        memory_summary_available=True,
    )
    signal_set = SignalSet(
        event_refs=[event],
        task_context=TaskContextView(
            task_id="task-1",
            session_id="session-1",
            user_goal="完成模块 0",
            recent_event_ids=["evt-1"],
            memory_refs=["mem-1"],
            tool_names=["read_file"],
            constraints=["只读世界身份"],
        ),
        agent_context=AgentContextView(
            agent_id="agent-1",
            profile_name="default",
            world_identity=identity,
            capabilities=["reasoning"],
            active_tools=["read_file"],
            memory_summary="保留上下文摘要",
            context_summary="投影视图",
        ),
        signals={"关系张力": 0.7},
    )

    restored = _round_trip(signal_set)

    restored_event = restored.event_refs[0]
    assert restored_event.summary == "世界事件：新的关系信号"
    assert restored_event.trace_id == "trace-中文-001"
    assert restored_event.timestamp == "2026-05-12T05:58:46+08:00"
    assert restored_event.metadata["unknown_future_key"]["保留"] is True
    assert restored.agent_context.world_identity.os_name == "元神甲"


def test_all_core_objects_round_trip_json():
    tension_op = TensionOperation(
        operation=TensionOperationType.GENERATE,
        tension_id="tension-1",
        tension_type=TensionType.UNSATISFIED_GOAL,
        intensity_delta=0.25,
        reason="目标尚未完成",
        evidence=["evt-1"],
    )
    tension = Tension(
        tension_id="tension-1",
        tension_type=TensionType.UNSATISFIED_GOAL,
        intensity=0.8,
        trend=0.2,
        baseline=0.3,
        activation=0.9,
        summary="推进目标的张力",
    )
    instances = [
        OSRuntimeEventRef("evt-1", EventSource.HERMES_CONVERSATION),
        WorldIdentityRef(os_id="os-1"),
        TaskContextView(task_id="task-1"),
        AgentContextView(agent_id="agent-1"),
        SignalSet(event_refs=[OSRuntimeEventRef("evt-2", EventSource.SYSTEM)]),
        LifeState(
            energy=0.8,
            fatigue=0.1,
            health=0.95,
            wakefulness=0.9,
            curiosity=0.4,
            boredom=0.1,
            creative_pressure=0.5,
            social_hunger=0.2,
            silence_pressure=0.3,
            restraint=0.7,
            life_cycle="active",
            recovery_cycle="normal",
            generated_intent_count=2,
        ),
        LifeStateDelta(
            previous={"energy": 1.0},
            current=LifeState(energy=0.8),
            changes={"energy": {"before": 1.0, "after": 0.8, "delta": -0.2}},
            reasons=["test transition"],
            evidence=["evt-1"],
        ),
        TensionExplanation(
            event_id="evt-1",
            detected_conflicts=["value-vs-risk"],
            operation_reasons=["test reason"],
            evidence=["evt-1"],
            summary="test explanation",
        ),
        TensionInterpretation(
            event_id="evt-1",
            detected_conflicts=["value-vs-risk"],
            operations=[tension_op],
            explanation="需要保留证据",
        ),
        tension_op,
        tension,
        TensionSet(core_tensions=[tension], dynamic_tensions=[tension]),
        TensionNetworkDelta(
            operations=[tension_op],
            propagation_edges=[{"from": "tension-1", "to": "tension-2", "weight": 0.4}],
            eliminated_tensions=["tension-3"],
        ),
        ActionPotential(
            intent_id="intent-1",
            value_potential=0.9,
            mutual_benefit_potential=0.6,
            learning_potential=0.7,
            risk_cost=0.2,
            overall_score=0.75,
        ),
        SelfPrompt(
            prompt_id="prompt-1",
            state_summary="生命状态摘要",
            tension_summary="张力摘要",
            potential_summary="势能摘要",
        ),
        OpenSpace(
            space_id="space-1",
            available_action_families=[OpenActionFamily.REPLY, OpenActionFamily.PLAN],
        ),
        TargetDirection(
            direction_id="direction-1",
            success_condition="测试通过",
            stop_condition="风险升高",
        ),
        OpenIntent(
            intent_id="intent-1",
            action_family=OpenActionFamily.DRAFT,
            action_type="draft_response",
            why_now="低风险建议",
            tools_needed=["none"],
            success_condition="用户可审阅",
            stop_condition="需要审批",
            risk_level=RiskLevel.LOW,
        ),
        ArbitrationResult(
            intent_id="intent-1",
            decision=ArbitrationDecision.REPORT_ONLY,
            risk_level=RiskLevel.MEDIUM,
            bo_score=0.8,
            yue_score=0.7,
            harmony_score=0.75,
        ),
        PermissionTicket(
            ticket_id="ticket-1",
            intent_id="intent-1",
            decision=ArbitrationDecision.SANDBOX_EXECUTE,
            issued_at="2026-05-12T00:00:00Z",
        ),
        ExecutionReceipt(
            receipt_id="receipt-1",
            ticket_id="ticket-1",
            intent_id="intent-1",
            status="completed",
            completed_at="2026-05-12T00:01:00Z",
        ),
        BubbleSpec(
            bubble_id="bubble-1",
            title="协作泡泡",
            lifecycle=BubbleLifecycle.ACTIVE,
            required_capabilities=["planning"],
        ),
        EvidencePackage(
            evidence_id="evidence-1",
            trace_id="trace-1",
            event_ids=["evt-1"],
            receipt_ids=["receipt-1"],
            summary="证据包",
            evidence=[{"kind": "event", "text": "中文证据"}],
        ),
        RuleCrystal(
            rule_id="rule-1",
            maturity=RuleMaturity.R1,
            title="低风险先报告",
            evidence_ids=["evidence-1"],
            created_at="2026-05-12T00:00:00Z",
        ),
    ]

    for instance in instances:
        _round_trip(instance)
