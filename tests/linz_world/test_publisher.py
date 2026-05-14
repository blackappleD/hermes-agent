from agent.linz_world import auth
from agent.linz_world.chat import send_chat_message
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity
from agent.linz_world.publisher import publish_event


_CONFIG = {"linz_world": {"persona_seed": "stable persona seed"}}


def test_publish_success_records_receipt(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = publish_event("wsp.agent_b", "wsp.chat.message.sent", {"content": "hi"}, repo, svc)

    assert receipt.status.value == "published"
    assert receipt.world_event_id == "evt_published"
    assert svc.publish_calls == 1


def test_chat_send_publishes_to_recipient_inbox(linz_home, FakeLinzService):
    class CapturingService(FakeLinzService):
        def publish_event(self, token_ref, subject, event_type, payload):
            self.last_publish = (subject, event_type, payload)
            return super().publish_event(token_ref, subject, event_type, payload)

    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = CapturingService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = send_chat_message("agent_b", "hello", to_os_name="Beta", repository=repo, service=svc)

    assert receipt.status.value == "published"
    subject, event_type, payload = svc.last_publish
    assert subject == "wsp.agent_b"
    assert event_type == "wsp.chat.message.sent"
    assert payload["to"] == "agent_b"
    assert payload["to_os_name"] == "Beta"
    assert payload["content"] == "hello"
    assert payload["from"]
    assert payload["message_id"].startswith("msg_")


def test_chat_send_rejects_missing_content_without_publish(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = send_chat_message("agent_b", "", repository=repo, service=svc)

    assert receipt.status.value == "rejected"
    assert receipt.governance_code == "content_missing"
    assert svc.publish_calls == 0


def test_publish_rejects_forbidden_event_before_service_call(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = publish_event("wsp.mrk.settlement.completed", "settlement.completed", {"amount": 1}, repo, svc)

    assert receipt.status.value == "rejected"
    assert svc.publish_calls == 0


def test_publish_success_with_receipt_persistence_failure_returns_uncertain(linz_home, FakeLinzService):
    class FailingReceiptRepository(LinzStateRepository):
        def append_list(self, key, value):
            if key == "receipts":
                raise OSError("disk full")
            return super().append_list(key, value)

    repo = FailingReceiptRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = publish_event("wsp.agent_b", "wsp.chat.message.sent", {"content": "hi"}, repo, svc)

    assert receipt.status.value == "uncertain"
    assert receipt.world_event_id == "evt_published"
    assert "receipt persistence failed" in receipt.message
