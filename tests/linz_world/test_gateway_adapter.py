from agent.linz_world.event_bus import project_to_message_event
from agent.linz_world.event_state import LinzStateRepository
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
