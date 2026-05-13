from agent.linz_world.models import AuthState, AuthorizationMap, LoginSession, LoginState, RelationshipRecord, RegistrationStatus, WorldIdentity
from agent.os_runtime.adapters.context import ContextAdapter
from agent.os_runtime.adapters.session_store import OSRuntimeEvent
from agent.os_runtime.domain import EventSource


class FakeRepo:
    profile_id = "profile-a"

    def __init__(self, *, identity, login, auth_map, relationships):
        self.identity = identity
        self.login = login
        self.auth_map = auth_map
        self._relationships = relationships

    def get_identity(self):
        return self.identity

    def get_login(self):
        return self.login

    def get_auth_map(self):
        return self.auth_map

    def relationships(self):
        return self._relationships


class FakeEventRepository:
    def __init__(self, events):
        self.events = events

    def list_by_session(self, session_id, limit=20):
        return [event for event in self.events if event.session_id == session_id][:limit]


class FakeRegistry:
    def get_all_tool_names(self):
        return ["terminal", "read_file", "send_message"]


class FakeContextEngine:
    summary = "compressed handoff summary"

    def get_status(self):
        return {
            "compression_count": 2,
            "context_length": 100000,
            "last_prompt_tokens": 1200,
            "threshold_tokens": 75000,
        }


class FailingMemoryManager:
    def prefetch_all(self, query, *, session_id=""):
        raise AssertionError("ContextAdapter must not prefetch unless requested")


def _complete_identity():
    return WorldIdentity(
        profile_id="profile-a",
        agent_id="agent-1",
        os_id="os-1",
        os_name="Hermes OS",
        soul_id="soul-1",
        soul_hash="hash-1",
        account_id="acct-1",
        registration_state=RegistrationStatus.REGISTERED,
        authorization_state=AuthState.CURRENT,
        memory_summary_available=True,
    )


def test_context_adapter_projects_complete_read_only_context():
    auth_map = AuthorizationMap(
        state=AuthState.CURRENT,
        map_version="map-v1",
        allowed_subjects=["wsp.mrk.requirement.published"],
        allowed_event_types=["requirement.published"],
        allowed_capabilities=["publish", "relationship"],
    )
    repo = FakeRepo(
        identity=_complete_identity(),
        login=LoginSession(
            state=LoginState.LOGGED_IN,
            credential_id="cred-1",
            subject_claims=["wsp.mrk.requirement.published"],
        ),
        auth_map=auth_map,
        relationships=[
            RelationshipRecord("rel-2", "peer-2", "ACTIVE", "second"),
            RelationshipRecord("rel-1", "peer-1", "ACTIVE", "first"),
        ],
    )
    events = [
        OSRuntimeEvent(
            event_id="evt-2",
            event_type="tool_result",
            source=EventSource.TOOL_RESULT,
            session_id="session-1",
            timestamp="2026-05-13T00:00:02Z",
            summary="ok",
        ),
        OSRuntimeEvent(
            event_id="evt-1",
            event_type="human_request",
            source=EventSource.HERMES_CONVERSATION,
            session_id="session-1",
            timestamp="2026-05-13T00:00:01Z",
            summary="summarize docs",
        ),
    ]

    snapshot = ContextAdapter(
        linz_state_repository=repo,
        event_repository=FakeEventRepository(events),
        memory_manager=FailingMemoryManager(),
        context_engine=FakeContextEngine(),
        tool_registry=FakeRegistry(),
    ).build_context(
        session_id="session-1",
        task_id="task-1",
        user_goal="summarize design docs",
        active_goal="ship module 2",
        memory_summary="known memories",
        memory_refs=["mem-b", "mem-a"],
        resource_state={
            "iteration_budget": {"remaining": 3},
            "model_state": {"model": "test-model"},
            "cost_state": {"spent": 1},
        },
    )

    assert snapshot.constraints == []
    assert snapshot.task_context.recent_event_ids == ["evt-1", "evt-2"]
    assert snapshot.task_context.memory_refs == ["mem-a", "mem-b"]
    assert snapshot.task_context.tool_names == ["read_file", "send_message", "terminal"]
    assert snapshot.task_context.metadata["authorization"]["state"] == "current"
    assert snapshot.task_context.metadata["authorization"]["map_version"] == "map-v1"
    assert snapshot.task_context.metadata["relationship_ids"] == ["rel-1", "rel-2"]
    assert snapshot.agent_context.agent_id == "agent-1"
    assert snapshot.agent_context.profile_name == "profile-a"
    assert snapshot.agent_context.world_identity.os_id == "os-1"
    assert snapshot.agent_context.world_identity.memory_summary_available is True
    assert snapshot.agent_context.capabilities == ["publish", "relationship"]
    assert snapshot.agent_context.memory_summary == "known memories"
    assert snapshot.agent_context.context_summary == "compressed handoff summary"
    assert snapshot.agent_context.metadata["context_status"]["compression_count"] == 2


def test_context_adapter_fail_closed_without_identity_login_or_auth_map():
    repo = FakeRepo(
        identity=None,
        login=LoginSession(state=LoginState.LOGGED_OUT),
        auth_map=AuthorizationMap(state=AuthState.UNKNOWN),
        relationships=[],
    )

    snapshot = ContextAdapter(linz_state_repository=repo, tool_registry=FakeRegistry()).build_context(session_id="session-1")

    assert "world_identity_missing" in snapshot.constraints
    assert "world_login_not_active" in snapshot.constraints
    assert "world_authorization_unknown" in snapshot.constraints
    assert snapshot.agent_context.world_identity.authorization_state == "unknown"
    assert snapshot.task_context.metadata["authorization"]["login_state"] == "logged_out"


def test_context_adapter_records_failed_and_stale_authorization_constraints():
    for state in (AuthState.FAILED, AuthState.STALE):
        repo = FakeRepo(
            identity=_complete_identity(),
            login=LoginSession(state=LoginState.LOGGED_IN, token_ref="token-ref"),
            auth_map=AuthorizationMap(state=state, last_error="not current"),
            relationships=[],
        )

        snapshot = ContextAdapter(linz_state_repository=repo, tool_registry=FakeRegistry()).build_context()

        assert f"world_authorization_{state.value}" in snapshot.constraints
        assert "world_login_not_active" not in snapshot.constraints
