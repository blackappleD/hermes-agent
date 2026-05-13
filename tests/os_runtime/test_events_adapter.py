from agent.linz_world.event_bus import project_to_message_event
from agent.linz_world.event_state import LinzStateRepository
from agent.os_runtime.adapters.events import (
    EventProjectionAdapter,
    project_goal_continuation,
    project_post_llm_call,
)
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.config import OSRuntimeConfig


def _adapter(tmp_path, *, enabled=True, max_summary_chars=128):
    repo = OSRuntimeEventRepository(root=tmp_path / "profile")
    return repo, EventProjectionAdapter(
        repo,
        OSRuntimeConfig(enabled=enabled, mode="passive"),
        max_summary_chars=max_summary_chars,
    )


def _write_config(home, *, enabled):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(
        "os_runtime:\n"
        f"  enabled: {'true' if enabled else 'false'}\n"
        "  mode: passive\n",
        encoding="utf-8",
    )


def test_projection_covers_conversation_tool_continuation_publish_and_error(tmp_path):
    repo, adapter = _adapter(tmp_path)
    try:
        results = [
            adapter.human_request("hello", session_id="session_1", trace_id="trace_1"),
            adapter.conversation_turn("turn summary", session_id="session_1", trace_id="trace_1"),
            adapter.assistant_response("answer", session_id="session_1", trace_id="trace_1"),
            adapter.tool_called("search", {"q": "linz"}, session_id="session_1", trace_id="trace_1"),
            adapter.tool_result("search", {"ok": True}, session_id="session_1", trace_id="trace_1"),
            adapter.os_runtime_continuation("continue goal", session_id="session_1", trace_id="trace_1"),
            adapter.world_event_published(
                {
                    "request_id": "req_1",
                    "subject": "wsp.chat.message.sent",
                    "event_type": "message.sent",
                    "status": "published",
                    "world_event_id": "evt_world",
                },
                session_id="session_1",
            ),
            adapter.runtime_feedback("projection failed", session_id="session_1", trace_id="trace_1"),
        ]

        assert all(result.written for result in results)
        event_types = {event.event_type for event in repo.list_by_session("session_1", limit=20)}
        assert {
            "human_request",
            "conversation_turn",
            "assistant_response",
            "tool_called",
            "tool_result",
            "os_runtime_continuation",
            "world_event_published",
            "runtime_feedback",
        } <= event_types
    finally:
        repo.close()


def test_world_message_event_projection_preserves_correlation_fields(tmp_path):
    linz_repo = LinzStateRepository(root=tmp_path / "linz_world", profile_id="test-profile")
    record, _ = linz_repo.persist_world_event(
        {
            "event_id": "evt_1",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello", "token": "secret"},
            "source": {"room_id": "room_1", "actor_id": "actor_1", "os_id": "os_1", "soul_id": "soul_1"},
            "sequence": {"stream": "events", "consumer": "agent", "nats_sequence": 42},
        }
    )
    message = project_to_message_event(record)
    repo, adapter = _adapter(tmp_path)
    try:
        result = adapter.world_event(message, session_id="session_1")

        assert result.written
        assert result.event.event_type == "world_event"
        assert result.event.metadata["subject"] == "wsp.chat.message.sent"
        assert result.event.metadata["event_type"] == "message.sent"
        assert result.event.metadata["nats_sequence"] == "42"
        assert result.event.metadata["os_id"] == "os_1"
        assert result.event.metadata["soul_id"] == "soul_1"
        assert "secret" not in result.event.summary
    finally:
        repo.close()


def test_disabled_projection_is_noop(tmp_path):
    repo, adapter = _adapter(tmp_path, enabled=False)
    try:
        result = adapter.human_request("hello", session_id="session_1")

        assert result.status == "skipped"
        assert repo.list_recent() == []
    finally:
        repo.close()


def test_tool_result_summary_is_bounded_and_referenced(tmp_path):
    repo, adapter = _adapter(tmp_path, max_summary_chars=96)
    long_result = "A" * 400
    try:
        result = adapter.tool_result("big_tool", long_result, session_id="session_1", trace_id="trace_1")

        assert result.written
        assert len(result.event.summary) <= 120
        assert result.event.content_ref.startswith("tool_result:big_tool:")
        assert result.event.payload_hash
        assert long_result not in result.event.summary
    finally:
        repo.close()


def test_tool_result_redacts_sensitive_fields(tmp_path):
    repo, adapter = _adapter(tmp_path, max_summary_chars=160)
    try:
        result = adapter.tool_result(
            "secret_tool",
            {"token": "secret123", "nested": {"api_key": "key123"}, "ok": True},
            session_id="session_1",
        )

        assert result.written
        assert "secret123" not in result.event.summary
        assert "key123" not in result.event.summary
        assert "[REDACTED]" in result.event.summary
        assert result.event.payload_hash
        assert result.event.content_ref.startswith("tool_result:secret_tool:")
    finally:
        repo.close()


def test_tool_result_redacts_sensitive_json_string(tmp_path):
    repo, adapter = _adapter(tmp_path, max_summary_chars=160)
    try:
        result = adapter.tool_result(
            "json_tool",
            '{"token":"secret123","ok":true}',
            session_id="session_1",
        )

        assert result.written
        assert "secret123" not in result.event.summary
        assert "[REDACTED]" in result.event.summary
        assert '"ok": true' in result.event.summary
    finally:
        repo.close()


def test_tool_result_redacts_authorization_bearer_string(tmp_path):
    repo, adapter = _adapter(tmp_path, max_summary_chars=160)
    try:
        result = adapter.tool_result(
            "header_tool",
            "Authorization: Bearer abc123",
            session_id="session_1",
        )

        assert result.written
        assert "abc123" not in result.event.summary
        assert "Bearer [REDACTED]" in result.event.summary
    finally:
        repo.close()


def test_post_llm_runtime_hook_writes_when_enabled_and_skips_when_disabled(tmp_path, monkeypatch):
    enabled_home = tmp_path / "enabled_home"
    _write_config(enabled_home, enabled=True)
    monkeypatch.setenv("HERMES_HOME", str(enabled_home))

    results = project_post_llm_call(
        session_id="session_1",
        user_message="hello",
        assistant_response="answer",
        conversation_history=[],
        model="model",
        platform="cli",
    )
    repo = OSRuntimeEventRepository(root=enabled_home)
    try:
        assert [result.status for result in results] == ["written", "written"]
        event_types = {event.event_type for event in repo.list_by_session("session_1")}
        assert {"human_request", "assistant_response"} <= event_types
    finally:
        repo.close()

    disabled_home = tmp_path / "disabled_home"
    _write_config(disabled_home, enabled=False)
    monkeypatch.setenv("HERMES_HOME", str(disabled_home))
    prompt = "unchanged prompt"

    skipped = project_post_llm_call(
        session_id="session_2",
        user_message=prompt,
        assistant_response="answer",
        conversation_history=[],
    )

    assert prompt == "unchanged prompt"
    assert skipped[0].status == "skipped"
    assert not (disabled_home / "state.db").exists()


def test_goal_continuation_runtime_hook_writes_when_enabled(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _write_config(home, enabled=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    result = project_goal_continuation(
        session_id="session_goal",
        continuation_prompt="continue toward goal",
        goal="ship module",
        reason="needs more work",
        turns_used=1,
        max_turns=8,
    )
    repo = OSRuntimeEventRepository(root=home)
    try:
        assert result.written
        event = repo.list_by_session("session_goal")[0]
        assert event.event_type == "os_runtime_continuation"
        assert event.metadata["goal"] == "ship module"
    finally:
        repo.close()


def test_goal_manager_continuation_path_writes_event_when_enabled(tmp_path, monkeypatch):
    from hermes_cli.goals import GoalManager

    home = tmp_path / "home"
    _write_config(home, enabled=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(
        "hermes_cli.goals.judge_goal",
        lambda goal, last_response: ("continue", "needs next step", False),
    )
    manager = GoalManager(session_id="session_goal_manager", default_max_turns=3)
    manager.set("finish module")

    decision = manager.evaluate_after_turn("made progress", user_initiated=True)
    repo = OSRuntimeEventRepository(root=home)
    try:
        assert decision["should_continue"] is True
        event = repo.list_by_session("session_goal_manager")[0]
        assert event.event_type == "os_runtime_continuation"
        assert event.metadata["goal"] == "finish module"
        assert event.metadata["reason"] == "needs next step"
    finally:
        repo.close()


def test_model_tools_post_tool_path_writes_redacted_events(tmp_path, monkeypatch):
    import model_tools
    from tools.registry import registry

    home = tmp_path / "home"
    _write_config(home, enabled=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(model_tools, "_READ_SEARCH_TOOLS", frozenset())
    monkeypatch.setattr(
        registry,
        "dispatch",
        lambda name, args, **kw: {"token": "secret123", "ok": True},
    )

    out = model_tools.handle_function_call(
        "secret_tool",
        {"api_key": "key123"},
        task_id="task_1",
        session_id="session_tool",
        tool_call_id="call_1",
        skip_pre_tool_call_hook=True,
    )
    repo = OSRuntimeEventRepository(root=home)
    try:
        assert out == {"token": "secret123", "ok": True}
        events = repo.list_by_session("session_tool")
        event_types = {event.event_type for event in events}
        assert {"tool_called", "tool_result"} <= event_types
        result_event = next(event for event in events if event.event_type == "tool_result")
        called_event = next(event for event in events if event.event_type == "tool_called")
        assert "secret123" not in result_event.summary
        assert "key123" not in called_event.metadata["arguments_hash"]
        assert result_event.metadata["task_id"] == "task_1"
        assert result_event.metadata["tool_call_id"] == "call_1"
    finally:
        repo.close()


def test_projection_failure_is_isolated(tmp_path):
    class BrokenRepo:
        def append(self, event):
            raise RuntimeError("db down")

    adapter = EventProjectionAdapter(BrokenRepo(), OSRuntimeConfig(enabled=True))

    result = adapter.assistant_response("answer", session_id="session_1")

    assert result.status == "error"
    assert "db down" in result.error
