import json

from tools import linz_world_tools


def test_linz_publish_tool_redacts_rejection_output(linz_home):
    output = json.loads(
        linz_world_tools.linz_publish(
            {
                "subject": "wsp.agent_b",
                "event_type": "wsp.chat.message.sent",
                "payload": {"content": "hi", "token": "secret"},
            }
        )
    )
    assert output["status"] == "rejected"
    assert "secret" not in json.dumps(output)


def test_linz_tool_schemas_are_registered():
    from tools.registry import registry

    for name in [
        "linz_status",
        "linz_map",
        "linz_events_recent",
        "linz_chat_send",
        "linz_publish",
        "linz_compute",
        "linz_memory_sink",
        "linz_relationship",
    ]:
        assert registry.get_entry(name) is not None
    assert registry.get_entry("linz_message_read") is None
    relationship_schema = registry.get_entry("linz_relationship").schema["parameters"]
    assert "add" in relationship_schema["properties"]["action"]["enum"]
    assert "relation_type" in relationship_schema["properties"]
