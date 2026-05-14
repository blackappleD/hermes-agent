from agent.linz_world import auth
from agent.linz_world.compute import invoke_compute
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity
from agent.linz_world.memory import write_memory
from agent.linz_world.relationship import add_active_relationship


_CONFIG = {"linz_world": {"persona_seed": "stable persona seed"}}


def _ready_repo(linz_home, svc):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    ensure_original_spirit_identity(repo, svc, config=_CONFIG)
    auth.login(repo, svc)
    return repo


def test_compute_rejects_explicit_credentials(linz_home, FakeLinzService):
    repo = _ready_repo(linz_home, FakeLinzService())
    receipt = invoke_compute("do work", {"api_key": "secret"}, repo)
    assert receipt.status.value == "rejected"
    assert "secret" not in receipt.message


def test_compute_uses_login_token(linz_home, FakeLinzService):
    class CapturingService(FakeLinzService):
        def invoke_compute(self, token_ref, task, input_data):
            self.compute_token_ref = token_ref
            return super().invoke_compute(token_ref, task, input_data)

    svc = CapturingService()
    repo = _ready_repo(linz_home, svc)

    receipt = invoke_compute("do work", {}, repo, svc)

    assert receipt.status.value == "published"
    assert svc.compute_token_ref == repo.get_login().token_ref


def test_memory_requires_artifact_ref_and_sink_reason(linz_home, FakeLinzService):
    repo = _ready_repo(linz_home, FakeLinzService())
    entry = write_memory("", "reason", "summary", repo)
    assert entry.status.value == "rejected"


def test_relationship_add_uses_login_identity_and_records_active_projection(linz_home, FakeLinzService):
    svc = FakeLinzService()
    repo = _ready_repo(linz_home, svc)
    result = add_active_relationship("actor_2", "trusted collaborator", repo, svc, relation_type="COLLABORATOR")
    assert result["success"] is True
    assert result["relationship"]["counterparty_id"] == "actor_2"
    assert result["relationship"]["state"] == "ACTIVE"
    assert result["relationship"]["summary"] == "trusted collaborator"
    assert result["relationship"]["relation_type"] == "COLLABORATOR"
    assert svc.relationship_calls == 1
    assert svc.last_relationship["identity"]["agent_id"] == repo.get_identity().agent_id
    assert svc.last_relationship["token_ref"] == repo.get_login().token_ref
    assert repo.relationships()[0]["counterparty_id"] == "actor_2"


def test_relationship_add_fails_closed_when_authorization_refresh_fails(linz_home, FakeLinzService):
    svc = FakeLinzService(fail_auth=True)
    repo = _ready_repo(linz_home, svc)
    result = add_active_relationship("actor_2", "trusted collaborator", repo, svc, relation_type="COLLABORATOR")
    assert result["success"] is False
    assert result["error"]["code"] == "authorization_refresh_failed"
    assert svc.relationship_calls == 0
    assert repo.relationships() == []
