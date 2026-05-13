from agent.linz_world.event_bus import project_to_message_event
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.gateway_adapter import persist_world_event_for_gateway
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
