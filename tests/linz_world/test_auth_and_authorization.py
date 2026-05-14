from agent.linz_world import auth
from agent.linz_world.api_client import LinzWorldServiceError
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity
from agent.linz_world.models import LoginSession, LoginState
from agent.linz_world.publisher import publish_event
from agent.linz_world.status import status_summary


_CONFIG = {"linz_world": {"persona_seed": "stable persona seed"}}


def test_publish_rejects_without_login(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)

    receipt = publish_event("wsp.agent_b", "wsp.chat.message.sent", {"content": "hi"}, repo, svc)

    assert receipt.status.value == "rejected"
    assert receipt.governance_code == "login_missing"
    assert svc.publish_calls == 0


def test_authorization_refresh_failure_blocks_side_effect(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService(fail_auth=True)
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)

    receipt = publish_event("wsp.agent_b", "wsp.chat.message.sent", {"content": "hi"}, repo, svc)

    assert receipt.status.value == "rejected"
    assert receipt.governance_code == "authorization_refresh_failed"
    assert svc.publish_calls == 0


def test_ensure_login_session_logs_in_when_session_is_missing(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)

    session = auth.ensure_login_session(repo, svc)

    assert session.state == LoginState.LOGGED_IN
    assert session.token_ref
    assert svc.login_calls == 1
    assert svc.refresh_calls == 1


def test_ensure_login_session_preserves_valid_logged_in_session(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)
    svc.login_calls = 0
    svc.refresh_calls = 0

    session = auth.ensure_login_session(repo, svc)

    assert session.state == LoginState.LOGGED_IN
    assert svc.login_calls == 0
    assert svc.refresh_calls == 1


def test_ensure_login_session_relogs_expired_session(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    session = auth.login(repo, svc)
    repo.save_login(
        LoginSession(
            state=LoginState.LOGGED_IN,
            token_ref=session.token_ref,
            expires_at="2000-01-01T00:00:00Z",
        )
    )
    svc.login_calls = 0

    refreshed = auth.ensure_login_session(repo, svc)

    assert refreshed.state == LoginState.LOGGED_IN
    assert refreshed.token_ref
    assert svc.login_calls == 1


def test_status_verifies_login_instead_of_trusting_cached_state(linz_home, FakeLinzService):
    class MissingRuntimeSecretService(FakeLinzService):
        def refresh_authorization_map(self, identity, token_ref):
            raise LinzWorldServiceError("login_secret_missing", "Linz World login token secret is unavailable.")

    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    ensure_original_spirit_identity(repo, FakeLinzService(), config=_CONFIG)
    repo.save_login(
        LoginSession(
            state=LoginState.LOGGED_IN,
            token_ref="linz_secret:event_token:missing",
            server_checked_at="2026-05-12T00:00:00Z",
        )
    )

    summary = status_summary(repo, MissingRuntimeSecretService())

    assert summary["login_state"] == "expired"
    assert summary["login_verified"] is False
    assert repo.get_login().token_ref == ""


def test_listener_pid_is_rechecked_before_reporting_online(linz_home, FakeLinzService, monkeypatch):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    session = auth.login(repo, svc)
    session.online = True
    session.listener_pid = 424242
    session.listener_started_at = "2026-05-12T00:00:00Z"
    repo.save_login(session)
    monkeypatch.setattr("gateway.status._pid_exists", lambda pid: False)

    checked = auth.validate_login_session(repo, check_server=False)

    assert checked.state == LoginState.LOGGED_IN
    assert checked.online is False
    assert checked.listener_pid == 0
