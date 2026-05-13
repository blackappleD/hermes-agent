import json

from tools import linz_world_tools


def test_linz_publish_tool_redacts_rejection_output(linz_home):
    output = json.loads(
        linz_world_tools.linz_publish(
            {
                "subject": "wsp.chat.message.sent",
                "event_type": "message.sent",
                "payload": {"text": "hi", "token": "secret"},
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
        "linz_publish",
        "linz_compute",
        "linz_memory_sink",
        "linz_relationship",
    ]:
        assert registry.get_entry(name) is not None
