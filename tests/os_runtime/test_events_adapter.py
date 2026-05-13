from agent.linz_world.event_bus import project_to_message_event
from agent.linz_world.event_state import LinzStateRepository
from agent.os_runtime.adapters.events import EventProjectionAdapter
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.config import OSRuntimeConfig


def _adapter(tmp_path, *, enabled=True, max_summary_chars=128):
    repo = OSRuntimeEventRepository(root=tmp_path / "profile")
    return repo, EventProjectionAdapter(
        repo,
        OSRuntimeConfig(enabled=enabled, mode="passive"),
        max_summary_chars=max_summary_chars,
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


def test_projection_failure_is_isolated(tmp_path):
    class BrokenRepo:
        def append(self, event):
            raise RuntimeError("db down")

    adapter = EventProjectionAdapter(BrokenRepo(), OSRuntimeConfig(enabled=True))

    result = adapter.assistant_response("answer", session_id="session_1")

    assert result.status == "error"
    assert "db down" in result.error
