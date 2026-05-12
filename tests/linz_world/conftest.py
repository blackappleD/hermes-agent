from __future__ import annotations

import pytest

from agent.linz_world.api_client import LinzWorldServiceError


@pytest.fixture
def linz_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


class _FakeLinzService:
    def __init__(self, *, fail_register: bool = False, fail_auth: bool = False):
        self.fail_register = fail_register
        self.fail_auth = fail_auth
        self.register_calls = 0
        self.publish_calls = 0

    def register_original_spirit(self, hermes_profile: str, os_name: str):
        self.register_calls += 1
        if self.fail_register:
            raise RuntimeError("registry down")
        return {
            "agentId": f"agent_{hermes_profile}",
            "soulId": f"soul_{hermes_profile}",
            "soulHash": f"hash_{hermes_profile}",
            "accessToken": "access-token-secret",
            "expiresIn": 86400,
            "registeredAt": "2026-05-12T00:00:00Z",
            "os_name": os_name,
        }

    def login(self, identity):
        return {
            "token": "event-token-secret",
            "expiresAt": "2099-01-01T00:00:00Z",
            "subjectClaims": ["wsp.chat.message.sent"],
            "credentialId": "cred_1",
        }

    def logout(self, token_ref):
        return {"ok": True}

    def refresh_authorization_map(self, identity, token_ref):
        if self.fail_auth:
            raise RuntimeError("auth down")
        return {
            "map_version": "v1",
            "allowed_subjects": ["wsp.chat.message.sent"],
            "allowed_event_types": ["message.sent"],
            "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"],
        }

    def publish_event(self, token_ref, subject, event_type, payload):
        self.publish_calls += 1
        return {"world_event_id": "evt_published", "published_at": "2026-05-12T00:00:00Z"}

    def invoke_compute(self, token_ref, task, input_data):
        return {
            "request_id": "req_1",
            "os_id": "agent_test",
            "provider": "fake",
            "model": "model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "reservation": {"status": "settled"},
            "usage": {"total_tokens": 1},
        }

    def write_memory(self, identity, token_ref, artifact_ref, sink_reason, summary):
        return {"receipt": "memory_1"}

    def read_relationships(self, identity, token_ref, counterparty_id=""):
        return {"relationships": []}

    def add_active_relationship(self, token_ref, counterparty_id, summary=""):
        raise LinzWorldServiceError(
            "unsupported_relationship_mutation",
            "No confirmed Linz World ACTIVE relationship mutation route exists.",
        )


@pytest.fixture
def FakeLinzService():
    return _FakeLinzService
