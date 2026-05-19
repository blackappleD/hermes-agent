import json

from tools import linz_world_bubble_tools, linz_world_tools


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
        "linz_bubble_snapshot",
        "linz_bubble_create_task",
        "linz_bubble_request_mount",
        "linz_bubble_submit_artifact",
    ]:
        assert registry.get_entry(name) is not None
    assert registry.get_entry("linz_message_read") is None
    relationship_schema = registry.get_entry("linz_relationship").schema["parameters"]
    assert "add" in relationship_schema["properties"]["action"]["enum"]
    assert "relation_type" in relationship_schema["properties"]


def test_linz_bubble_mutation_tool_respects_disabled_config(linz_home):
    (linz_home / "config.yaml").write_text(
        "\n".join(
            [
                "linz_world:",
                "  bubble:",
                "    read_only: true",
                "    allow_mutations: false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    output = json.loads(
        linz_world_bubble_tools.linz_bubble_create_task(
            {
                "parent_bubble_id": "bub_demand_1",
                "name": "Implement adapter",
                "goal": "Wire Hermes to BPS",
                "confirm_mutation": True,
            }
        )
    )

    assert output["success"] is False
    assert output["receipt"]["governance_code"] == "bubble_mutations_disabled"


def test_linz_bubble_snapshot_tool_returns_redacted_summary(monkeypatch, linz_home):
    from agent.linz_world.models import LoginSession, LoginState, RegistrationStatus, WorldIdentity
    from agent.linz_world.bubble_models import BubbleRecord, BubbleSnapshot

    identity = WorldIdentity(
        profile_id="test-profile",
        agent_id="agent_test",
        os_id="agent_test",
        os_name="Hermes",
        soul_id="soul_test",
        soul_hash="hash_test",
        account_id="agent_test",
        registration_state=RegistrationStatus.REGISTERED,
        private_key_path="key",
        public_key_fingerprint="fingerprint",
    )

    class FakeClient:
        def get_snapshot(self, bubble_id, *, token_ref=""):
            assert bubble_id == "bub_task_1"
            assert token_ref == "token-ref"
            return BubbleSnapshot(
                bubble=BubbleRecord(
                    bubble_id="bub_task_1",
                    bubble_type="task",
                    name="Task",
                    lifecycle_state="active",
                    spec={"secret_payload": "not returned by summary"},
                )
            )

    monkeypatch.setattr(linz_world_bubble_tools.identity, "ensure_original_spirit_identity", lambda repo: identity)
    monkeypatch.setattr(
        linz_world_bubble_tools.auth,
        "ensure_login_session",
        lambda repo: LoginSession(state=LoginState.LOGGED_IN, token_ref="token-ref"),
    )
    monkeypatch.setattr(linz_world_bubble_tools, "default_bubble_client", lambda: FakeClient())

    output = json.loads(linz_world_bubble_tools.linz_bubble_snapshot({"bubble_id": "bub_task_1"}))

    assert output["success"] is True
    assert output["bubble_id"] == "bub_task_1"
    assert output["snapshot"]["bubble"]["lifecycle_state"] == "active"
    assert "secret_payload" not in json.dumps(output)
