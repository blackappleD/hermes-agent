import pytest

from agent.linz_world.event_bus import project_to_message_event
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.gateway_adapter import dispatch_world_event, persist_world_event_for_gateway
from gateway.platform_registry import platform_registry


def test_linz_world_platform_is_registered():
    assert platform_registry.is_registered("linz_world")


def test_world_event_projection_uses_redacted_summary(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    record, _ = repo.persist_world_event(
        {
            "event_id": "evt_1",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello", "token": "secret"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
        }
    )

    message = project_to_message_event(record)

    assert message.source.platform.value == "linz_world"
    assert message.message_id == "evt_1"
    assert "secret" not in message.text
    assert "linz_audit:" in message.raw_message["audit_ref"]
    assert message.raw_message["subject"] == "wsp.chat.message.sent"
    assert message.raw_message["event_type"] == "message.sent"


def test_persist_world_event_for_gateway_builds_message_after_state_write(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    raw = {
        "event_id": "evt_1",
        "subject": "wsp.chat.message.sent",
        "event_type": "message.sent",
        "payload": {"text": "hello", "token": "secret"},
        "source": {"room_id": "room_1", "actor_id": "actor_1", "os_id": "os_1", "soul_id": "soul_1"},
        "sequence": {"stream": "world-events", "consumer": "hermes-profile", "nats_sequence": 9},
    }

    result = persist_world_event_for_gateway(raw, repo)
    duplicate = persist_world_event_for_gateway({**raw, "event_id": "evt_2"}, repo)

    stored = repo.recent_events()[0]
    assert result.created is True
    assert result.ack_ready is True
    assert result.message_event is not None
    assert result.record.dispatch_status.value == "processing"
    assert stored.event_id == "evt_1"
    assert stored.dispatch_status.value == "processing"
    assert result.message_event.raw_message["nats_sequence"] == "9"
    assert result.message_event.raw_message["os_id"] == "os_1"
    assert result.message_event.raw_message["soul_id"] == "soul_1"
    assert "secret" not in result.message_event.text
    assert duplicate.created is False
    assert duplicate.message_event is None


@pytest.mark.asyncio
async def test_dispatch_world_event_marks_handled_after_success(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    seen = []

    async def _handler(message):
        seen.append(message.message_id)

    result = await dispatch_world_event(
        {
            "event_id": "evt_success",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
        },
        _handler,
        repo,
    )

    assert result.persisted.ack_ready is True
    assert result.handled is True
    assert result.record.dispatch_status.value == "handled"
    assert seen == ["evt_success"]


@pytest.mark.asyncio
async def test_dispatch_world_event_records_failure_without_rethrow(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")

    async def _handler(message):
        raise RuntimeError("agent failed")

    result = await dispatch_world_event(
        {
            "event_id": "evt_failure",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
        },
        _handler,
        repo,
        retry_limit=1,
    )

    assert result.persisted.ack_ready is True
    assert result.handled is False
    assert result.record.dispatch_status.value == "failed"
    assert result.record.attempt_count == 1
    assert result.record.requires_manual_handling is True
    assert "agent failed" in result.record.last_error
