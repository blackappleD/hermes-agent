from agent.linz_world import auth
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity
from agent.linz_world.publisher import publish_event


_CONFIG = {"linz_world": {"persona_seed": "stable persona seed"}}


def test_publish_success_records_receipt(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = publish_event("wsp.chat.message.sent", "message.sent", {"text": "hi"}, repo, svc)

    assert receipt.status.value == "published"
    assert receipt.world_event_id == "evt_published"
    assert svc.publish_calls == 1


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

    receipt = publish_event("wsp.chat.message.sent", "message.sent", {"text": "hi"}, repo, svc)

    assert receipt.status.value == "uncertain"
    assert receipt.world_event_id == "evt_published"
    assert "receipt persistence failed" in receipt.message
