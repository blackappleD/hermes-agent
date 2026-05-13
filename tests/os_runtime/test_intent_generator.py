from agent.os_runtime.domain import (
    ActionPotential,
    OpenActionFamily,
    OpenSpace,
    RiskLevel,
    SelfPrompt,
    TargetDirection,
)
from agent.os_runtime.engine.intent_generator import OpenIntentGenerator


def _self_prompt() -> SelfPrompt:
    return SelfPrompt(
        prompt_id="prompt-1",
        state_summary="active",
        tension_summary="goal tension",
        potential_summary="valuable",
        open_space=OpenSpace(
            space_id="space-1",
            available_action_families=[
                OpenActionFamily.COMMUNICATE,
                OpenActionFamily.LEARN,
                OpenActionFamily.CREATE,
                OpenActionFamily.REST,
            ],
            metadata={"available_tools": ["draft_file"]},
        ),
        target_direction=TargetDirection(
            direction_id="direction-1",
            description="finish the module",
            success_condition="tests pass",
            stop_condition="risk rises",
        ),
        metadata={"evidence_refs": ["event:evt-1", "action_potential:ap-1"]},
    )


def test_rule_path_generates_fixed_schema_intent():
    intent = OpenIntentGenerator().generate(
        self_prompt=_self_prompt(),
        action_potential=ActionPotential(
            intent_id="ap-1",
            value_potential=0.9,
            learning_potential=0.3,
            mutual_benefit_potential=0.7,
            risk_cost=0.1,
            overall_score=0.8,
        ),
    )

    assert intent.action_family == OpenActionFamily.CREATE
    assert intent.action_type == "draft_artifact"
    assert "finish the module" in intent.why_now
    assert intent.open_space.space_id == "space-1"
    assert intent.target_direction.direction_id == "direction-1"
    assert intent.tools_needed == ["draft_file"]
    assert intent.proposed_new_tools == []
    assert intent.proposed_new_skills == []
    assert intent.success_condition == "tests pass"
    assert intent.stop_condition == "risk rises"
    assert intent.metadata["execution_permitted"] is False


def test_llm_json_success_is_schema_validated_and_not_permission():
    prompt = _self_prompt()
    llm_payload = {
        "intent_id": "intent-llm",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "goal tension is active",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "user can review",
        "stop_condition": "approval is needed",
        "risk_level": "low",
    }

    intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        action_potential=ActionPotential(intent_id="ap-1"),
        llm_json=llm_payload,
        prefer_llm=True,
    )

    assert intent.intent_id == "intent-llm"
    assert intent.action_family == OpenActionFamily.COMMUNICATE
    assert intent.risk_level == RiskLevel.LOW
    assert intent.metadata["source"] == "llm_candidate"
    assert intent.metadata["execution_permitted"] is False


def test_invalid_json_falls_back_to_rule_path_without_execution_permission():
    intent = OpenIntentGenerator().generate(
        self_prompt=_self_prompt(),
        action_potential=ActionPotential(intent_id="ap-1", risk_cost=0.8),
        llm_json="{not json",
        prefer_llm=True,
    )

    assert intent.action_family == OpenActionFamily.REST
    assert intent.metadata["source"] == "rule"
    assert intent.metadata["fallback_reason"] == "invalid_json"
    assert intent.metadata["execution_permitted"] is False
    assert intent.risk_level == RiskLevel.CRITICAL


def test_unknown_action_family_and_missing_fields_fall_back():
    prompt = _self_prompt()
    unknown = {
        "action_family": "unsafe_side_effect",
        "action_type": "unsafe",
        "why_now": "because",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "done",
        "stop_condition": "stop",
    }
    missing = {"action_family": "communicate"}

    unknown_intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        llm_json=unknown,
        prefer_llm=True,
    )
    missing_intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        llm_json=missing,
        prefer_llm=True,
    )

    assert unknown_intent.metadata["fallback_reason"] == "unknown_action_family:unsafe_side_effect"
    assert missing_intent.metadata["fallback_reason"].startswith("missing_required_fields:")


def test_llm_cannot_trust_fabricated_linz_world_subject_or_event_type():
    prompt = _self_prompt()
    payload = {
        "intent_id": "intent-publish",
        "action_family": "communicate",
        "action_type": "linz_world.publish",
        "why_now": "publish would help",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "published",
        "stop_condition": "catalog missing",
        "subject": "fabricated-subject",
        "event_type": "fabricated.event",
    }

    intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        llm_json=payload,
        prefer_llm=True,
    )

    assert "subject" not in intent.metadata
    assert "event_type" not in intent.metadata
    assert intent.metadata["catalog_validation_required"] is True
    assert intent.metadata["untrusted_linz_world_candidate"] == {
        "subject": "fabricated-subject",
        "event_type": "fabricated.event",
    }
