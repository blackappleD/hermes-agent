from agent.os_runtime.domain import (
    ActionPotential,
    AgentContextView,
    LifeState,
    OpenActionFamily,
    TaskContextView,
    Tension,
    TensionExplanation,
    TensionSet,
    TensionType,
)
from agent.os_runtime.engine.prompt_compiler import SelfPromptCompiler, pre_llm_call


def test_compiler_outputs_required_self_prompt_fields_and_evidence_refs():
    prompt = SelfPromptCompiler().compile(
        task_context=TaskContextView(
            task_id="task-1",
            session_id="session-1",
            active_goal="ship module 5",
            recent_event_ids=["evt-1"],
            memory_refs=["mem-1"],
            tool_names=["pytest"],
            constraints=["authorization unknown"],
        ),
        agent_context=AgentContextView(
            active_tools=["python"],
            memory_summary="previous module context",
            context_summary="workspace branch is ready",
        ),
        life_state=LifeState(
            energy=0.8,
            fatigue=0.2,
            wakefulness=0.9,
            restraint=0.4,
            life_cycle="active",
            recovery_cycle="stable",
        ),
        tension_set=TensionSet(
            dynamic_tensions=[
                Tension(
                    tension_id="goal:module-5",
                    tension_type=TensionType.UNSATISFIED_GOAL,
                    activation=0.82,
                    summary="module 5 remains unimplemented",
                    evidence=["evt-1"],
                )
            ]
        ),
        tension_explanation=TensionExplanation(
            event_id="evt-1",
            evidence=["evt-1"],
            summary="goal tension is active",
        ),
        action_potential=ActionPotential(
            intent_id="ap-1",
            value_potential=0.9,
            mutual_benefit_potential=0.7,
            learning_potential=0.6,
            risk_cost=0.2,
            overall_score=0.8,
            rationale="valuable and low risk",
        ),
        environment_state={"event_catalog": "missing"},
    )

    payload = prompt.to_dict()
    assert payload["state_summary"]
    assert payload["tension_summary"]
    assert payload["potential_summary"]
    assert payload["memory_scope"] == ["mem-1", "agent_context:memory_summary"]
    assert "fail-closed: authorization is not confirmed" in payload["constraint_scope"]
    assert "fail-closed: linz_world.event_catalog is not confirmed" in payload["constraint_scope"]
    assert payload["open_space"]["available_action_families"]
    assert payload["target_direction"]["description"] == "ship module 5"
    assert "event:evt-1" in prompt.metadata["evidence_refs"]
    assert "tension:goal:module-5" in prompt.metadata["evidence_refs"]
    assert "action_potential:ap-1" in prompt.metadata["evidence_refs"]


def test_compiler_uses_defaults_when_tension_or_action_potential_is_missing():
    prompt = SelfPromptCompiler().compile(
        task_context=TaskContextView(task_id="task-2"),
        life_state=LifeState(),
    )

    assert prompt.open_space is not None
    assert prompt.target_direction is not None
    assert "action potential unavailable: using neutral defaults" in prompt.constraint_scope
    assert prompt.metadata["diagnostics"] == [
        "missing_tension_explanation",
        "missing_action_potential",
    ]


def test_open_space_uses_new_action_family_schema_only():
    prompt = SelfPromptCompiler().compile(
        task_context=TaskContextView(task_id="task-3"),
        action_potential=ActionPotential(learning_potential=0.9, risk_cost=0.1),
    )

    values = {item.value for item in prompt.open_space.available_action_families}
    assert {OpenActionFamily.COMMUNICATE.value, OpenActionFamily.LEARN.value, OpenActionFamily.NEW_SKILL.value} <= values
    assert values.isdisjoint({"reply", "draft", "use_tool"})


def test_compiler_includes_authoritative_linz_rule_context_in_constraints():
    prompt = SelfPromptCompiler().compile(
        task_context=TaskContextView(
            task_id="task-linz",
            metadata={
                "linz_rule_context": {
                    "authoritative": True,
                    "phase": "chat_response",
                    "confidence": "high",
                    "summary": "Chat can be drafted freely, but sending is an external side effect.",
                    "matched_sections": [{"section_id": "LW-CHAT"}],
                    "required_fields": ["to_os_id", "content"],
                    "missing_fields": ["to_os_id"],
                    "forbidden": ["send_empty_message"],
                    "next_steps": ["Draft a reply first"],
                    "approval_required": True,
                }
            },
        ),
        action_potential=ActionPotential(),
    )

    assert any("phase=chat_response" in item for item in prompt.constraint_scope)
    assert "linz_rule_missing_fields: to_os_id" in prompt.constraint_scope
    assert "linz_rule_forbidden: send_empty_message" in prompt.constraint_scope
    assert "linz_rule_approval_required: true" in prompt.constraint_scope


def test_pre_llm_call_injects_ephemeral_context_without_mutating_system_prompt():
    prompt = SelfPromptCompiler().compile(task_context=TaskContextView(task_id="task-4"))
    request = {
        "messages": [
            {"role": "system", "content": "stable system prompt"},
            {"role": "user", "content": "current request"},
        ]
    }

    updated = pre_llm_call(request, prompt)

    assert request["messages"][0]["content"] == "stable system prompt"
    assert "metadata" not in request["messages"][1]
    assert updated["messages"][0]["content"] == "stable system prompt"
    context = updated["messages"][1]["metadata"]["ephemeral_context"]
    assert context["os_runtime_self_prompt"]["prompt_id"] == "self-prompt:task-4"
