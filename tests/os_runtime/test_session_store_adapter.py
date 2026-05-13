import sqlite3

from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.domain import EventSource, OSRuntimeEventRef


def test_repository_append_get_and_list_queries(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path / "profile_a")
    try:
        first = repo.append(
            {
                "event_id": "evt_1",
                "event_type": "human_request",
                "source": EventSource.HERMES_CONVERSATION.value,
                "trace_id": "trace_1",
                "session_id": "session_1",
                "timestamp": "2026-05-13T00:00:00Z",
                "summary": "hello",
                "metadata": {"channel": "cli"},
            }
        )
        second = repo.append(
            OSRuntimeEventRef(
                event_id="evt_2",
                source=EventSource.HERMES_CONVERSATION,
                trace_id="trace_1",
                session_id="session_1",
                timestamp="2026-05-13T00:00:01Z",
                summary="assistant response",
            )
        )

        assert first.event_type == "human_request"
        assert repo.get("evt_1").metadata == {"channel": "cli"}
        assert [event.event_id for event in repo.list_recent()] == ["evt_2", "evt_1"]
        assert [event.event_id for event in repo.list_by_session("session_1")] == ["evt_2", "evt_1"]
        assert [event.event_id for event in repo.list_by_trace("trace_1")] == ["evt_2", "evt_1"]
        assert second.event_type == "runtime_feedback"
    finally:
        repo.close()


def test_repository_is_profile_scoped_and_uses_state_db_side_table(tmp_path):
    profile_a = tmp_path / "profile_a"
    profile_b = tmp_path / "profile_b"
    repo_a = OSRuntimeEventRepository(root=profile_a)
    repo_b = OSRuntimeEventRepository(root=profile_b)
    try:
        repo_a.append(
            {
                "event_id": "evt_a",
                "event_type": "assistant_response",
                "source": "hermes_conversation",
                "summary": "only profile a",
            }
        )

        assert repo_a.get("evt_a") is not None
        assert repo_b.get("evt_a") is None
        assert (profile_a / "state.db").exists()
        with sqlite3.connect(profile_a / "state.db") as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'os_runtime_events'"
            ).fetchone()
        assert row == ("os_runtime_events",)
    finally:
        repo_a.close()
        repo_b.close()


def test_duplicate_event_id_is_idempotent(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path / "profile")
    try:
        repo.append(
            {
                "event_id": "evt_same",
                "event_type": "tool_called",
                "source": "hermes_conversation",
                "summary": "first",
            }
        )
        duplicate = repo.append(
            {
                "event_id": "evt_same",
                "event_type": "tool_called",
                "source": "hermes_conversation",
                "summary": "second",
            }
        )

        assert duplicate.summary == "first"
        assert len(repo.list_recent()) == 1
    finally:
        repo.close()


def test_disabled_repository_does_not_write(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path / "profile", enabled=False)
    try:
        assert repo.append({"event_id": "evt_1", "source": "system"}) is None
        assert repo.list_recent() == []
    finally:
        repo.close()
