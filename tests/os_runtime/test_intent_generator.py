import json
from types import SimpleNamespace

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
        "metadata": {"execution_permitted": False},
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
    assert intent.metadata["llm_response"]["parse_status"] == "accepted"
    assert '"intent_id": "intent-llm"' in intent.metadata["llm_response"]["raw"]


def test_world_chat_event_enriches_communicate_intent_with_reply_draft():
    prompt = _self_prompt()
    payload = {
        "intent_id": "intent-chat",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "social response tension is present",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "draft is auditable",
        "stop_condition": "no external side effects",
        "risk_level": "low",
        "metadata": {"reply": {"draft_text": "你好，我在。"}},
    }

    intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        action_potential=ActionPotential(intent_id="ap-1"),
        llm_json=payload,
        prefer_llm=True,
        event_content=[
            {
                "event_id": "evt-chat",
                "event_type": "world_event",
                "source": "linz_world",
                "summary": "你好",
                "metadata": {
                    "subject": "wsp.my-inbox",
                    "event_type": "wsp.chat.message.sent",
                    "os_id": "peer-os",
                    "chat_id": "chat-1",
                },
            }
        ],
    )

    assert intent.action_type == "reply_chat_message"
    assert intent.tools_needed == []
    assert intent.metadata["reply"]["target_os_id"] == "peer-os"
    assert intent.metadata["reply"]["conversation_id"] == "chat-1"
    assert intent.metadata["reply"]["source_event_id"] == "evt-chat"
    assert intent.metadata["reply"]["draft_text"] == "你好，我在。"
    assert intent.metadata["reply"]["send_requested"] is False


def test_rule_path_does_not_synthesize_chat_reply_draft_text():
    prompt = _self_prompt()
    prompt.open_space = OpenSpace(
        space_id="space-chat",
        available_action_families=[OpenActionFamily.COMMUNICATE],
    )

    intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        action_potential=ActionPotential(intent_id="ap-chat"),
        event_content=[
            {
                "event_id": "evt-chat",
                "event_type": "world_event",
                "source": "linz_world",
                "summary": "你好，在吗？",
                "metadata": {
                    "subject": "wsp.my-inbox",
                    "event_type": "wsp.chat.message.sent",
                    "os_id": "peer-os",
                    "chat_id": "chat-1",
                },
            }
        ],
    )

    assert intent.metadata["source"] == "rule"
    assert intent.action_type == "reply_chat_message"
    assert intent.metadata["reply"]["target_os_id"] == "peer-os"
    assert intent.metadata["reply"]["incoming_summary"] == "你好，在吗？"
    assert "draft_text" not in intent.metadata["reply"]
    assert intent.metadata["reply"]["send_requested"] is False


def test_llm_path_calls_auxiliary_task_with_runtime_payload():
    prompt = _self_prompt()
    llm_payload = {
        "intent_id": "intent-llm-call",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "event pressure and target direction align",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "user can review",
        "stop_condition": "approval is needed",
        "risk_level": "low",
        "metadata": {"execution_permitted": False},
    }
    calls = {}

    def caller(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(llm_payload))
                )
            ]
        )

    intent = OpenIntentGenerator(llm_caller=caller).generate(
        self_prompt=prompt,
        action_potential=ActionPotential(intent_id="ap-1"),
        event_content={"summary": "new world event"},
        tension_field={"top": "goal tension"},
        prefer_llm=True,
    )

    assert intent.intent_id == "intent-llm-call"
    assert intent.metadata["source"] == "llm_candidate"
    assert intent.metadata["execution_permitted"] is False
    assert calls["task"] == "os_runtime_intent"
    assert calls["temperature"] == 0.0
    assert calls["tools"][0]["function"]["name"] == "emit_open_intent"
    assert calls["tool_choice"] == {
        "type": "function",
        "function": {"name": "emit_open_intent"},
    }
    payload = json.loads(calls["messages"][1]["content"])
    assert payload["event_content"]["summary"] == "new world event"
    assert payload["tension_field"]["top"] == "goal tension"
    assert payload["action_potential"]["intent_id"] == "ap-1"
    assert payload["self_prompt"]["prompt_id"] == "prompt-1"


def test_llm_path_retries_text_json_when_tool_calling_is_unsupported():
    prompt = _self_prompt()
    llm_payload = {
        "intent_id": "intent-text-json",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "event pressure and target direction align",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "user can review",
        "stop_condition": "approval is needed",
        "risk_level": "low",
        "metadata": {"execution_permitted": False},
    }
    calls = []

    def caller(**kwargs):
        calls.append(kwargs)
        if "tools" in kwargs:
            raise RuntimeError("unsupported parameter: tool_choice")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(llm_payload))
                )
            ]
        )

    intent = OpenIntentGenerator(llm_caller=caller).generate(
        self_prompt=prompt,
        action_potential=ActionPotential(intent_id="ap-1"),
        prefer_llm=True,
    )

    assert intent.intent_id == "intent-text-json"
    assert intent.metadata["source"] == "llm_candidate"
    assert len(calls) == 2
    assert "tools" in calls[0]
    assert "tool_choice" in calls[0]
    assert "tools" not in calls[1]
    assert "tool_choice" not in calls[1]


def test_llm_path_extracts_open_intent_tool_call_arguments():
    prompt = _self_prompt()
    llm_payload = {
        "intent_id": "intent-tool-call",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "social response tension is present",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "draft is auditable",
        "stop_condition": "no external side effects",
        "risk_level": "low",
        "metadata": {"execution_permitted": False},
    }

    def caller(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="emit_open_intent",
                                    arguments=json.dumps(llm_payload),
                                )
                            )
                        ],
                    )
                )
            ]
        )

    intent = OpenIntentGenerator(llm_caller=caller).generate(
        self_prompt=prompt,
        action_potential=ActionPotential(intent_id="ap-1"),
        prefer_llm=True,
    )

    assert intent.intent_id == "intent-tool-call"
    assert intent.action_family == OpenActionFamily.COMMUNICATE
    assert intent.metadata["source"] == "llm_candidate"
    assert intent.metadata["llm_response"]["parse_status"] == "accepted"


def test_llm_call_failure_falls_back_to_rule_path_without_execution_permission():
    def caller(**kwargs):
        raise RuntimeError("network unavailable")

    intent = OpenIntentGenerator(llm_caller=caller).generate(
        self_prompt=_self_prompt(),
        action_potential=ActionPotential(intent_id="ap-1", risk_cost=0.1),
        prefer_llm=True,
    )

    assert intent.metadata["source"] == "rule"
    assert intent.metadata["fallback_reason"] == "llm_call_failed:RuntimeError"
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
    assert intent.metadata["llm_response"] == {
        "parse_status": "invalid_json",
        "raw": "{not json",
    }
    assert intent.risk_level == RiskLevel.CRITICAL


def test_unknown_action_family_and_missing_fields_fall_back():
    prompt = _self_prompt()
    unknown = {
        "intent_id": "intent-unknown-family",
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
        "risk_level": "low",
        "metadata": {},
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


def test_communicate_intent_with_tools_falls_back_to_rule_path():
    prompt = _self_prompt()
    payload = {
        "intent_id": "intent-bad-tools",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "casual chat",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": ["draft_file"],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "draft",
        "stop_condition": "stop",
        "risk_level": "low",
        "metadata": {},
    }

    intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        llm_json=payload,
        prefer_llm=True,
    )

    assert intent.metadata["source"] == "rule"
    assert intent.metadata["fallback_reason"] == "tools_not_allowed_for_communicate"


def test_invalid_metadata_falls_back_to_rule_path():
    prompt = _self_prompt()
    payload = {
        "intent_id": "intent-bad-metadata",
        "action_family": "communicate",
        "action_type": "draft_message",
        "why_now": "casual chat",
        "open_space": prompt.open_space.to_dict(),
        "target_direction": prompt.target_direction.to_dict(),
        "tools_needed": [],
        "proposed_new_tools": [],
        "proposed_new_skills": [],
        "success_condition": "draft",
        "stop_condition": "stop",
        "risk_level": "low",
        "metadata": "not-an-object",
    }

    intent = OpenIntentGenerator().generate(
        self_prompt=prompt,
        llm_json=payload,
        prefer_llm=True,
    )

    assert intent.metadata["source"] == "rule"
    assert intent.metadata["fallback_reason"] == "invalid_metadata"


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
        "risk_level": "low",
        "metadata": {},
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
