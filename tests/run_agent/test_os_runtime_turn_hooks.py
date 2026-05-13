from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.os_runtime.config import OSRuntimeConfig
from run_agent import AIAgent


def _tool_defs():
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "search",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def _response(content: str = "done"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=None, reasoning=None),
                finish_reason="stop",
            )
        ],
        model="test/model",
        usage=None,
    )


def test_os_runtime_self_prompt_reaches_current_user_api_message(monkeypatch, tmp_path):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr("run_agent._hermes_home", home)
    cfg = OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": {
                "enabled": True,
                "apply_to_all_turns": True,
                "inject_self_prompt": True,
            },
        }
    )
    before_calls = []
    after_calls = []

    class _FakeTurnHook:
        def __init__(self, session_id, *, config=None, **kwargs):
            self.session_id = session_id
            self.config = config

        def before_turn(self, request, *, message=None, **kwargs):
            before_calls.append((request, message))
            return SimpleNamespace(
                injected=True,
                self_prompt={
                    "state_summary": "active",
                    "tension_summary": "top tension",
                    "potential_summary": "report only",
                    "open_space": {"description": "reply safely", "constraints": ["no tools"]},
                    "target_direction": {
                        "description": "draft an answer",
                        "success_condition": "answer is useful",
                        "stop_condition": "stop before tools",
                    },
                    "constraints": ["no tool execution"],
                    "evidence_refs": ["evt-1"],
                },
            )

        def after_turn(self, *, assistant_response="", **kwargs):
            after_calls.append(assistant_response)
            return SimpleNamespace(applied=True)

    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: cfg)
    monkeypatch.setattr("agent.os_runtime.turn_hooks.TurnTensionHook", _FakeTurnHook)

    with (
        patch("run_agent.get_tool_definitions", return_value=_tool_defs()),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("agent.linz_world.bootstrap.ensure_linz_identity_for_persona", return_value=None),
        patch("run_agent.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            provider="openrouter",
            api_mode="chat_completions",
            model="test/model",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_id="session-1",
        )
        agent.client = MagicMock()

    captured = {}

    def _fake_api_call(api_kwargs):
        captured["api_kwargs"] = api_kwargs
        return _response("ok")

    agent._interruptible_api_call = _fake_api_call
    agent._persist_session = lambda *args, **kwargs: None
    agent._save_trajectory = lambda *args, **kwargs: None
    agent._save_session_log = lambda *args, **kwargs: None
    agent._cleanup_task_resources = lambda *args, **kwargs: None

    result = agent.run_conversation("hello")

    assert result["final_response"] == "ok"
    assert before_calls
    assert after_calls == ["ok"]
    api_messages = captured["api_kwargs"]["messages"]
    user_messages = [msg for msg in api_messages if msg.get("role") == "user"]
    assert user_messages
    assert "hello" in user_messages[-1]["content"]
    assert "<os-runtime-self-prompt>" in user_messages[-1]["content"]
    assert "top tension" in user_messages[-1]["content"]
    assert "evt-1" in user_messages[-1]["content"]
    assert all("<os-runtime-self-prompt>" not in str(msg.get("content")) for msg in api_messages if msg.get("role") == "system")
    assert "<os-runtime-self-prompt>" not in str(result["messages"][0]["content"])
