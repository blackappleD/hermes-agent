from agent.linz_world import auth
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity
from agent.linz_world.publisher import publish_event


def test_publish_rejects_without_login(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc)

    receipt = publish_event("wsp.chat.message.sent", "message.sent", {"text": "hi"}, repo, svc)

    assert receipt.status.value == "rejected"
    assert receipt.governance_code == "login_missing"
    assert svc.publish_calls == 0


def test_authorization_refresh_failure_blocks_side_effect(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService(fail_auth=True)
    ensure_original_spirit_identity(repo, svc)
    auth.login(repo, svc)

    receipt = publish_event("wsp.chat.message.sent", "message.sent", {"text": "hi"}, repo, svc)

    assert receipt.status.value == "rejected"
    assert receipt.governance_code == "authorization_refresh_failed"
    assert svc.publish_calls == 0
