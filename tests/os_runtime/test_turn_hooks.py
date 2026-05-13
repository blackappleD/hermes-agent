from __future__ import annotations

from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.domain import (
    OpenActionFamily,
    OpenSpace,
    SelfPrompt,
    TargetDirection,
)
from agent.os_runtime.self_prompt_injector import SelfPromptInjector
from agent.os_runtime.turn_hooks import TurnTensionHook


def _config(**autonomous):
    defaults = {
        "enabled": True,
        "apply_to_all_turns": True,
        "inject_self_prompt": False,
    }
    defaults.update(autonomous)
    return OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": defaults,
        }
    )


def _request():
    return {
        "messages": [
            {"role": "system", "content": "stable system prompt"},
            {"role": "user", "content": "hello"},
        ],
        "prompt_cache_prefix": "stable-prefix",
    }


def test_apply_to_all_turns_false_does_not_touch_request(tmp_path):
    cfg = _config(apply_to_all_turns=False)
    hook = TurnTensionHook(
        "session-1",
        config=cfg,
        event_repository=OSRuntimeEventRepository(root=tmp_path),
        queue_repository=RuntimeQueueRepository(root=tmp_path),
    )
    request = _request()

    result = hook.before_turn(request, message="hello")

    assert result.applied is False
    assert result.request is request
    assert result.request == request


def test_before_turn_observes_without_injection_when_disabled(tmp_path):
    event_repo = OSRuntimeEventRepository(root=tmp_path)
    queue_repo = RuntimeQueueRepository(root=tmp_path)
    hook = TurnTensionHook(
        "session-1",
        config=_config(inject_self_prompt=False),
        event_repository=event_repo,
        queue_repository=queue_repo,
    )
    request = _request()

    try:
        result = hook.before_turn(request, message="hello")

        assert result.applied is True
        assert result.injected is False
        assert result.request == request
        assert event_repo.list_by_session("session-1")[0].event_type == "human_request"
        assert queue_repo.load_state("session-1").last_turn_event_id == result.event_id
    finally:
        event_repo.close()
        queue_repo.close()


def test_before_turn_injects_only_current_user_context(tmp_path):
    hook = TurnTensionHook(
        "session-1",
        config=_config(inject_self_prompt=True),
        event_repository=OSRuntimeEventRepository(root=tmp_path),
        queue_repository=RuntimeQueueRepository(root=tmp_path),
    )
    request = _request()

    result = hook.before_turn(request, message="hello")

    assert result.applied is True
    assert result.injected is True
    assert request["messages"][0]["content"] == "stable system prompt"
    assert request["prompt_cache_prefix"] == "stable-prefix"
    assert result.request["messages"][0]["content"] == "stable system prompt"
    assert result.request["prompt_cache_prefix"] == "stable-prefix"
    user = result.request["messages"][-1]
    assert "os_runtime_self_prompt" in user["metadata"]["ephemeral_context"]


def test_hook_error_fails_open_and_blocks_side_effect(tmp_path):
    class BrokenSignals:
        def interpret(self, **kwargs):
            raise RuntimeError("boom")

    hook = TurnTensionHook(
        "session-1",
        config=_config(),
        event_repository=OSRuntimeEventRepository(root=tmp_path),
        queue_repository=RuntimeQueueRepository(root=tmp_path),
        signal_interpreter=BrokenSignals(),
    )
    request = _request()

    result = hook.before_turn(request, message="hello", external_side_effect=True)

    assert result.applied is False
    assert result.request is request
    assert result.should_block_side_effect is True


def test_self_prompt_injector_redacts_sensitive_fields():
    prompt = SelfPrompt(
        prompt_id="prompt-1",
        state_summary="token=secret",
        tension_summary="raw_payload should not leak",
        potential_summary="Authorization: Bearer abc",
        constraint_scope=["private_key=abc", "no tools"],
        open_space=OpenSpace(
            description="safe",
            available_action_families=[OpenActionFamily.COMMUNICATE],
            constraints=["secret=value"],
        ),
        target_direction=TargetDirection(
            description="draft",
            success_condition="respond",
            stop_condition="stop",
        ),
        metadata={
            "evidence_refs": ["evt-1"],
            "restricted_audit_content": "nope",
            "raw_payload": {"token": "secret"},
        },
    )

    result = SelfPromptInjector().inject(_request(), prompt)
    injected = result.payload

    assert "secret" not in str(injected).lower()
    assert "raw_payload" not in str(injected)
    assert "restricted_audit_content" not in str(injected)
    assert injected["evidence_refs"] == ["evt-1"]
