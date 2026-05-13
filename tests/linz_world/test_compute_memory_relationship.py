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


def test_relationship_mutation_without_confirmed_route_fails_closed(linz_home, FakeLinzService):
    svc = FakeLinzService()
    repo = _ready_repo(linz_home, svc)
    result = add_active_relationship("actor_2", "trusted collaborator", repo, svc)
    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_relationship_mutation"
