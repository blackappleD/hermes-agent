import pytest
from types import SimpleNamespace

from agent.linz_world.bootstrap import LinzBootstrapError, ensure_linz_identity_for_persona
from agent.linz_world.config import DEFAULT_LINZ_WORLD_SERVICE_URL
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity


_CONFIG = {"linz_world": {"persona_seed": "stable persona seed"}}


def test_identity_registration_is_profile_idempotent(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()

    first = ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    second = ensure_original_spirit_identity(repo, svc, config=_CONFIG)

    assert first.os_id == second.os_id
    assert svc.register_calls == 1


def test_failed_registration_blocks_persona(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")

    with pytest.raises(LinzBootstrapError):
        ensure_linz_identity_for_persona(repo, FakeLinzService(fail_register=True), config=_CONFIG)

    saved = repo.get_identity()
    assert saved.registration_state.value == "failed"
    assert "registry down" in saved.last_error


def test_partial_identity_fails_closed(linz_home):
    class PartialService:
        def register_original_spirit(
            self,
            hermes_profile,
            os_name,
            persona_seed="",
            os_type="USER",
            runtime_type="Hermes",
            public_key="",
            public_key_type="RSA",
            fingerprint="",
        ):
            return {"os_id": "os_1", "os_name": os_name}

    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    identity = ensure_original_spirit_identity(repo, PartialService(), config=_CONFIG)
    assert identity.registration_state.value == "failed"
    assert "missing" in identity.last_error


def test_run_agent_default_identity_gate_blocks_persona_load(monkeypatch):
    from run_agent import AIAgent

    monkeypatch.setattr(
        "agent.linz_world.config.load_linz_world_config",
        lambda: SimpleNamespace(identity_required_on_agent_load=True),
    )

    def _blocked():
        raise RuntimeError("linz identity blocked")

    monkeypatch.setattr(
        "agent.linz_world.runtime_bridge.ensure_linz_identity_for_persona",
        _blocked,
    )

    with pytest.raises(RuntimeError, match="linz identity blocked"):
        AIAgent(model="test", skip_context_files=True, skip_memory=True)


def test_blank_service_url_uses_default_http_endpoint_for_identity(linz_home, monkeypatch):
    calls = []

    class Response:
        status_code = 200
        reason_phrase = "OK"
        text = ""

        def json(self):
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "agentId": "agent-1",
                    "soulId": "soul-1",
                    "soulHash": "hash-1",
                    "accessToken": "access-token",
                    "expiresIn": 3600,
                    "registeredAt": "2026-05-13T00:00:00Z",
                },
            }

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return Response()

    monkeypatch.setattr("httpx.request", fake_request)
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    identity = ensure_original_spirit_identity(
        repo,
        service=None,
        config={"linz_world": {"service_url": "", "persona_seed": "stable persona seed"}},
    )

    assert identity.registration_state.value == "registered"
    assert calls[0][1] == f"{DEFAULT_LINZ_WORLD_SERVICE_URL}/api/v1/auth/register"

    saved = repo.get_identity()
    assert saved is not None
    assert saved.registration_state.value == "registered"


def test_missing_persona_seed_blocks_registration_before_service_call(linz_home, FakeLinzService):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    svc = FakeLinzService()

    identity = ensure_original_spirit_identity(
        repo,
        service=svc,
        config={"linz_world": {"persona_seed": ""}},
    )

    assert identity.registration_state.value == "failed"
    assert "persona_seed" in identity.last_error
    assert svc.register_calls == 0
