from agent.linz_world.models import AuthState, AuthorizationMap, LoginSession, LoginState
from agent.os_runtime.adapters.context import ContextAdapter, ContextSnapshot
from agent.os_runtime.adapters.linz_rules import LinzRuleContextResolver, constraints_from_rule_context
from agent.os_runtime.adapters.session_store import OSRuntimeEvent
from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.domain import AgentContextView, EventSource, TaskContextView


class FakeRepo:
    profile_id = "profile-test"

    def get_identity(self):
        return None

    def get_login(self):
        return LoginSession(state=LoginState.LOGGED_IN, token_ref="token-ref")

    def get_auth_map(self):
        return AuthorizationMap(
            state=AuthState.CURRENT,
            allowed_capabilities=["publish"],
            allowed_publish_subjects=["wsp.agent_b"],
            allowed_publish_event_types=["wsp.chat.message.sent"],
        )

    def relationships(self):
        return []


class FakeEvents:
    def __init__(self, events):
        self.events = list(events)

    def list_by_session(self, session_id, limit=20):
        return [event for event in self.events if event.session_id == session_id][:limit]


def _world_event(**metadata):
    return OSRuntimeEvent(
        event_id=metadata.pop("event_id", "evt-world"),
        event_type="world_event",
        source=EventSource.LINZ_WORLD,
        session_id="session-1",
        timestamp="2026-05-21T00:00:00Z",
        summary=metadata.pop("summary", "world event"),
        metadata=metadata,
    )


def test_linz_rule_resolver_uses_structured_event_fields_for_authoritative_match():
    event = _world_event(
        subject="wsp.agent_b",
        event_type="wsp.chat.message.sent",
        os_id="peer-1",
    )
    snapshot = ContextSnapshot(
        task_context=TaskContextView(task_id="task-1", session_id="session-1"),
        agent_context=AgentContextView(),
        recent_events=[event],
    )

    result = LinzRuleContextResolver().resolve(snapshot)

    assert result.authoritative is True
    assert result.status == "matched"
    assert result.phase == "chat_response"
    assert result.confidence == "high"
    assert result.matched_sections[0]["section_id"] == "LW-CHAT"
    assert "event_type_exact" in result.matched_sections[0]["reasons"]


def test_linz_rule_resolver_does_not_promote_free_text_keyword_query():
    snapshot = ContextSnapshot(
        task_context=TaskContextView(
            task_id="task-1",
            session_id="session-1",
            user_goal="我要接单，帮我看看规则",
        ),
        agent_context=AgentContextView(),
        recent_events=[],
    )

    result = LinzRuleContextResolver().resolve(snapshot)

    assert result.authoritative is False
    assert result.status == "skipped"
    assert "free_text_query_not_authoritative" in result.diagnostics


def test_linz_rule_resolver_blocks_unknown_structured_routes():
    event = _world_event(subject="unknown.subject", event_type="unknown.event")
    snapshot = ContextSnapshot(
        task_context=TaskContextView(task_id="task-1", session_id="session-1"),
        agent_context=AgentContextView(),
        recent_events=[event],
    )

    result = LinzRuleContextResolver().resolve(snapshot)

    assert result.authoritative is False
    assert result.status == "unmatched"
    assert "structured_match_required" in result.diagnostics
    assert "linz_rule_no_authoritative_match" in constraints_from_rule_context(result.to_dict())


def test_context_adapter_enriches_snapshot_with_structured_linz_rule_context():
    event = _world_event(
        subject="wsp.agent_b",
        event_type="wsp.chat.message.sent",
        os_id="peer-1",
    )
    cfg = OSRuntimeConfig.from_dict({"enabled": True})

    snapshot = ContextAdapter(
        linz_state_repository=FakeRepo(),
        event_repository=FakeEvents([event]),
        config=cfg,
    ).build_context(session_id="session-1", task_id="task-1")

    rule_context = snapshot.task_context.metadata["linz_rule_context"]
    assert rule_context["authoritative"] is True
    assert rule_context["phase"] == "chat_response"
    assert "linz_rule_approval_required" in snapshot.task_context.constraints
    assert "linz_rule_missing_field:content" in snapshot.task_context.constraints
    assert "linz_rule_missing_field:to_os_id" not in snapshot.task_context.constraints
