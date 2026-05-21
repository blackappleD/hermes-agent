import json

from agent.linz_world.models import LoginSession, LoginState, PublishReceipt, ReceiptStatus, RegistrationStatus, WorldIdentity
from tools import linz_world_bubble_tools, linz_world_tools


def _patch_ready_linz_identity(monkeypatch):
    identity = WorldIdentity(
        profile_id="test-profile",
        agent_id="agent_worker",
        os_id="agent_worker",
        os_name="Worker",
        soul_id="soul_worker",
        soul_hash="hash_worker",
        account_id="agent_worker",
        registration_state=RegistrationStatus.REGISTERED,
    )
    monkeypatch.setattr(linz_world_bubble_tools.identity, "ensure_original_spirit_identity", lambda repo: identity)
    monkeypatch.setattr(
        linz_world_bubble_tools.auth,
        "ensure_login_session",
        lambda repo: LoginSession(state=LoginState.LOGGED_IN, token_ref="token-ref"),
    )
    return identity


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
        "linz_world_guide",
        "linz_world_section",
        "linz_world_flow_resolve",
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


def test_linz_world_flow_resolve_tool_returns_workflow_guidance():
    output = json.loads(
        linz_world_tools.linz_world_flow_resolve(
            {
                "subject": "wsp.mrk.requirement.published",
                "event_type": "wsp.mrk.requirement.published",
                "user_intent": "accept_demand",
            }
        )
    )

    assert output["success"] is True
    assert output["phase"] == "requirement_intake"
    assert "linz_publish" in output["recommended_tools"]
    assert "direct_bubble_accept_as_mrk_order" in output["forbidden"]
    assert output["approval_required"] is True


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


def test_linz_bubble_create_demand_publishes_mrk_requirement(monkeypatch, linz_home):
    _patch_ready_linz_identity(monkeypatch)
    publish_calls = []

    def fake_publish(subject, event_type, payload, repository=None):
        publish_calls.append((subject, event_type, payload))
        return PublishReceipt(
            request_id="req-publish",
            subject=subject,
            event_type=event_type,
            payload_summary=json.dumps(payload, sort_keys=True),
            status=ReceiptStatus.PUBLISHED,
            world_event_id="evt-publish",
        )

    monkeypatch.setattr(linz_world_bubble_tools, "publish_event", fake_publish)
    monkeypatch.setattr(linz_world_bubble_tools, "default_bubble_client", lambda: (_ for _ in ()).throw(AssertionError("direct Bubble client should not be used")))

    output = json.loads(
        linz_world_bubble_tools.linz_bubble_create_demand(
            {
                "requirement_id": "REQ-1",
                "name": "Build report",
                "goal": "Create the report",
                "target_os_id": "agent_receiver",
                "budget_amount": "100",
                "confirm_mutation": True,
            }
        )
    )

    assert output["success"] is True
    assert output["bridge"] == "mrk_publish"
    assert output["receipt"]["action"] == "mrk.requirement.published"
    assert publish_calls == [
        (
            "mrk.requirement.published",
            "mrk.requirement.published",
            {
                "requirement_id": "REQ-1",
                "publisher_os_id": "agent_worker",
                "publisher_os_name": "Worker",
                "title": "Build report",
                "description": "Create the report",
                "budget_amount": "100",
                "target_os_id": "agent_receiver",
            },
        )
    ]


def test_linz_bubble_mrk_flow_tools_publish_order_events(monkeypatch, linz_home):
    _patch_ready_linz_identity(monkeypatch)
    publish_calls = []

    def fake_publish(subject, event_type, payload, repository=None):
        publish_calls.append((subject, event_type, payload))
        return PublishReceipt(
            request_id=f"req-{event_type}",
            subject=subject,
            event_type=event_type,
            payload_summary=json.dumps(payload, sort_keys=True),
            status=ReceiptStatus.PUBLISHED,
            world_event_id=f"evt-{event_type}",
        )

    monkeypatch.setattr(linz_world_bubble_tools, "publish_event", fake_publish)
    monkeypatch.setattr(linz_world_bubble_tools, "default_bubble_client", lambda: (_ for _ in ()).throw(AssertionError("direct Bubble client should not be used")))

    accepted = json.loads(
        linz_world_bubble_tools.linz_bubble_accept_demand(
            {
                "demand_bubble_id": "REQ-1",
                "order_id": "ORD-1",
                "requester_os_id": "agent_requester",
                "requester_os_name": "Requester",
                "confirm_mutation": True,
            }
        )
    )
    delivered = json.loads(
        linz_world_bubble_tools.linz_bubble_submit_artifact(
            {
                "task_bubble_id": "task_REQ-1_agent_worker",
                "mount_id": "mnt-1",
                "requirement_id": "REQ-1",
                "order_id": "ORD-1",
                "artifact_ref": "hermes-session://artifact",
                "delivery_note": "done",
                "confirm_mutation": True,
            }
        )
    )
    approved = json.loads(
        linz_world_bubble_tools.linz_bubble_review_task_acceptance(
            {
                "task_bubble_id": "task_REQ-1_agent_worker",
                "requirement_id": "REQ-1",
                "order_id": "ORD-1",
                "approved": True,
                "confirm_mutation": True,
            }
        )
    )

    assert accepted["event_type"] == "mrk.order.accepted"
    assert delivered["event_type"] == "mrk.order.handover.delivered"
    assert approved["event_type"] == "mrk.order.handover.approved"
    assert [item[1] for item in publish_calls] == [
        "mrk.order.accepted",
        "mrk.order.handover.delivered",
        "mrk.order.handover.approved",
    ]
    assert publish_calls[0][2]["worker_os_id"] == "agent_worker"
    assert publish_calls[1][2]["file_ref"] == "hermes-session://artifact"
    assert publish_calls[2][2]["reviewer_os_id"] == "agent_worker"


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
