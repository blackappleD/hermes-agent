from __future__ import annotations

import pytest


@pytest.fixture
def linz_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


class FakeLinzService:
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
            "os_id": f"os_{hermes_profile}",
            "soul_id": f"soul_{hermes_profile}",
            "os_name": os_name,
            "account_id": f"acct_{hermes_profile}",
        }

    def login(self, identity):
        return {"token_ref": "linz_session:test", "expires_at": "2099-01-01T00:00:00Z"}

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
        return {"result": {"ok": True}, "provider_summary": "fake/model", "receipt": "compute_1"}

    def write_memory(self, token_ref, artifact_ref, sink_reason, summary):
        return {"receipt": "memory_1"}

    def read_relationships(self, token_ref, counterparty_id=""):
        return {"relationships": []}

    def add_active_relationship(self, token_ref, counterparty_id, summary=""):
        return {"relationship_id": "rel_1", "counterparty_id": counterparty_id, "state": "ACTIVE", "summary": summary}
