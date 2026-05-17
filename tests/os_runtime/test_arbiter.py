from agent.os_runtime.domain import (
    ActionPotential,
    ArbitrationDecision,
    OpenActionFamily,
    OpenIntent,
    OpenSpace,
    RiskLevel,
    TargetDirection,
)
from agent.os_runtime.engine.arbiter import BoYueArbiter, pre_tool_call


def _intent(
    *,
    family: OpenActionFamily = OpenActionFamily.COMMUNICATE,
    action_type: str = "draft_message",
    tools: list[str] | None = None,
    risk: RiskLevel = RiskLevel.LOW,
) -> OpenIntent:
    return OpenIntent(
        intent_id="intent-1",
        action_family=family,
        action_type=action_type,
        why_now="goal tension is active",
        open_space=OpenSpace(
            space_id="space-1",
            available_action_families=[family],
            metadata={"available_tools": tools or []},
        ),
        target_direction=TargetDirection(
            direction_id="direction-1",
            success_condition="done",
            stop_condition="stop before risk",
        ),
        tools_needed=tools or [],
        success_condition="done",
        stop_condition="stop before risk",
        risk_level=risk,
    )


def test_arbiter_outputs_five_new_decision_values_and_boyue_scores():
    result = BoYueArbiter().arbitrate(
        intent=_intent(),
        action_potential=ActionPotential(
            value_potential=0.7,
            mutual_benefit_potential=0.6,
            learning_potential=0.5,
            risk_cost=0.1,
            overall_score=0.65,
        ),
    )

    assert [item.value for item in ArbitrationDecision] == [
        "auto_execute",
        "sandbox_execute",
        "require_approval",
        "report_only",
        "reject",
    ]
    assert result.decision == ArbitrationDecision.REPORT_ONLY
    assert result.innovation_score > 0
    assert result.opportunity_score > 0
    assert result.expansion_value > 0
    assert result.risk_score >= 0
    assert result.permission_level == 1.0
    assert result.compliance_fit == 1.0
    assert result.trust_impact > 0
    assert result.mutual_benefit_score > 0
    assert result.long_term_net_value > 0
    assert result.ecosystem_gain > 0
    assert "allow_reply" in result.metadata["legacy_decision_aliases"]
    assert result.decision.value not in {"allow_reply", "allow_draft", "allow_tool"}


def test_low_risk_allowed_tool_can_sandbox_or_auto_execute():
    sandbox = BoYueArbiter().arbitrate(
        intent=_intent(family=OpenActionFamily.CREATE, action_type="draft_artifact", tools=["draft_file"]),
        available_tools=["draft_file"],
        policy_preflight={"decision": "allow"},
        action_potential=ActionPotential(risk_cost=0.2, overall_score=0.8),
    )
    auto = BoYueArbiter().arbitrate(
        intent=_intent(family=OpenActionFamily.CREATE, action_type="draft_artifact", tools=["draft_file"]),
        available_tools=["draft_file"],
        policy_preflight={"decision": "allow"},
        action_potential=ActionPotential(risk_cost=0.1, overall_score=0.9),
        allow_auto_execute=True,
    )

    assert sandbox.decision == ArbitrationDecision.SANDBOX_EXECUTE
    assert auto.decision == ArbitrationDecision.AUTO_EXECUTE


def test_high_risk_intent_requires_approval_not_direct_tool_execution():
    result = BoYueArbiter().arbitrate(
        intent=_intent(
            family=OpenActionFamily.CREATE,
            action_type="write_file",
            tools=["write_file"],
            risk=RiskLevel.HIGH,
        ),
        available_tools=["write_file"],
        policy_preflight={"decision": "allow"},
        action_potential=ActionPotential(risk_cost=0.75),
    )

    assert result.decision == ArbitrationDecision.REQUIRE_APPROVAL
    assert result.required_approvals == ["human_approval"]


def test_unknown_tool_is_rejected():
    result = BoYueArbiter().arbitrate(
        intent=_intent(family=OpenActionFamily.CREATE, action_type="write_file", tools=["unknown_tool"]),
        available_tools=["safe_tool"],
        policy_preflight={"decision": "allow"},
    )

    assert result.decision == ArbitrationDecision.REJECT
    assert "unknown tools" in result.rationale


def test_linz_world_publish_fails_closed_without_policy_catalog_and_authorization():
    publish = _intent(
        family=OpenActionFamily.CREATE,
        action_type="linz_world.publish",
        tools=["linz_world.publish"],
    )

    missing = BoYueArbiter().arbitrate(
        intent=publish,
        available_tools=["linz_world.publish"],
    )
    bad_catalog = BoYueArbiter().arbitrate(
        intent=publish,
        available_tools=["linz_world.publish"],
        policy_preflight={"decision": "allow"},
        event_catalog_preflight={"subject_confirmed": True, "event_type_confirmed": False},
        authorization_summary={"decision": "allow"},
    )
    allowed = BoYueArbiter().arbitrate(
        intent=publish,
        available_tools=["linz_world.publish"],
        policy_preflight={"decision": "allow"},
        event_catalog_preflight={"subject_confirmed": True, "event_type_confirmed": True},
        authorization_summary={"decision": "allow"},
        action_potential=ActionPotential(risk_cost=0.1),
    )

    assert missing.decision == ArbitrationDecision.REJECT
    assert bad_catalog.decision == ArbitrationDecision.REJECT
    assert allowed.decision == ArbitrationDecision.AUTO_EXECUTE


def test_chat_reply_is_report_only_until_send_is_requested():
    draft = _intent(action_type="reply_chat_message")
    draft.metadata = {
        "reply": {
            "target_os_id": "peer-os",
            "draft_text": "你好，我在。",
            "send_requested": False,
        }
    }
    send = OpenIntent.from_dict(
        {
            **draft.to_dict(),
            "metadata": {
                "reply": {
                    "target_os_id": "peer-os",
                    "draft_text": "你好，我在。",
                    "send_requested": True,
                }
            },
        }
    )

    draft_result = BoYueArbiter().arbitrate(intent=draft)
    approval_result = BoYueArbiter().arbitrate(
        intent=send,
        policy_preflight={"decision": "allow", "requires_approval": True},
        event_catalog_preflight={"subject_confirmed": True, "event_type_confirmed": True},
        authorization_summary={"decision": "allow"},
    )
    auto_result = BoYueArbiter().arbitrate(
        intent=send,
        policy_preflight={"decision": "allow", "requires_approval": False},
        event_catalog_preflight={"subject_confirmed": True, "event_type_confirmed": True},
        authorization_summary={"decision": "allow"},
    )

    assert draft_result.decision == ArbitrationDecision.REPORT_ONLY
    assert approval_result.decision == ArbitrationDecision.REQUIRE_APPROVAL
    assert approval_result.required_approvals == ["linz_world_chat_reply_approval"]
    assert auto_result.decision == ArbitrationDecision.AUTO_EXECUTE


def test_pre_tool_call_blocks_report_only_and_missing_preflight():
    result = pre_tool_call(
        intent=_intent(family=OpenActionFamily.CREATE, action_type="draft_artifact", tools=["draft_file"]),
        tool_name="draft_file",
        available_tools=["draft_file"],
    )

    assert result["allowed"] is False
    assert result["decision"] == "reject"
    assert "policy preflight" in result["reason"]
