from agent.linz_world.models import AuthState, AuthorizationMap, LoginState
from agent.os_runtime.adapters.session_store import OSRuntimeEvent
from agent.os_runtime.domain import AgentContextView, EventSource, TaskContextView, WorldIdentityRef
from agent.os_runtime.engine.signals import SIGNAL_KEYS, SignalInterpreter


def _contexts(*, auth_state="current", login_state="logged_in"):
    auth = {
        "state": auth_state,
        "login_state": login_state,
        "allowed_publish_subjects": ["wsp.mrk.requirement.published"],
        "allowed_publish_event_types": ["requirement.published"],
        "allowed_capabilities": ["publish"],
        "map_version": "map-v1",
    }
    task_context = TaskContextView(
        task_id="task-1",
        session_id="session-1",
        user_goal="summarize docs",
        active_goal="finish module",
        recent_event_ids=["evt-1"],
        memory_refs=["mem-1"],
        tool_names=["read_file", "terminal"],
        constraints=[],
        metadata={
            "authorization": auth,
            "resource_state": {
                "iteration_budget": {"remaining": 2},
                "model_state": {"model": "test-model"},
                "cost_state": {"spent": 1},
                "disabled_capabilities": ["network"],
            },
        },
    )
    agent_context = AgentContextView(
        agent_id="agent-1",
        profile_name="profile-a",
        world_identity=WorldIdentityRef(os_id="os-1", authorization_state=auth_state, map_version="map-v1"),
        capabilities=["publish"],
        active_tools=["read_file", "terminal"],
        memory_summary="memory",
        context_summary="context",
        metadata={"authorization": auth},
    )
    return task_context, agent_context


def _event(event_id, runtime_event_type, source, summary, **metadata):
    return OSRuntimeEvent(
        event_id=event_id,
        event_type=runtime_event_type,
        source=source,
        session_id="session-1",
        timestamp=f"2026-05-13T00:00:0{event_id[-1]}Z",
        summary=summary,
        metadata=metadata,
        status=str(metadata.get("status") or "recorded"),
    )


def _codes(signal_set, key):
    return {item["code"] for item in signal_set.signals[key]}


def _empty_contexts():
    return TaskContextView(session_id="session-1"), AgentContextView()


def _logged_in_contexts():
    auth = {
        "state": "current",
        "login_state": "logged_in",
        "allowed_publish_subjects": ["wsp.agent-1"],
        "allowed_publish_event_types": ["wsp.chat.message.sent"],
        "allowed_capabilities": ["publish", "relationship"],
        "map_version": "map-v1",
    }
    return (
        TaskContextView(session_id="session-1", metadata={"authorization": auth}),
        AgentContextView(metadata={"authorization": auth}),
    )


def test_signal_interpreter_outputs_deterministic_full_signal_set():
    task_context, agent_context = _contexts()
    auth_map = AuthorizationMap(
        state=AuthState.CURRENT,
        allowed_publish_subjects=["wsp.mrk.requirement.published"],
        allowed_publish_event_types=["requirement.published"],
    )
    events = [
        _event(
            "evt-1",
            "human_request",
            EventSource.HERMES_CONVERSATION,
            "TODO summarize docs",
        ),
        _event(
            "evt-2",
            "world_event",
            EventSource.LINZ_WORLD,
            "public requirement broadcast",
            subject="wsp.mrk.requirement.published",
            event_type="requirement.published",
            publisher_id="peer-1",
        ),
        _event(
            "evt-3",
            "tool_result",
            EventSource.TOOL_RESULT,
            "pytest failed",
            tool_name="terminal",
            status="failed",
        ),
    ]
    interpreter = SignalInterpreter()

    first = interpreter.interpret(
        task_context=task_context,
        agent_context=agent_context,
        events=events,
        authorization_map=auth_map,
        relationships=[{"relationship_id": "rel-1", "counterparty_id": "peer-1", "state": "ACTIVE"}],
    )
    second = interpreter.interpret(
        task_context=task_context,
        agent_context=agent_context,
        events=events,
        authorization_map=auth_map,
        relationships=[{"relationship_id": "rel-1", "counterparty_id": "peer-1", "state": "ACTIVE"}],
    )

    assert first.to_dict() == second.to_dict()
    assert tuple(first.signals) == SIGNAL_KEYS
    assert "context_user_goal" in _codes(first, "needs")
    assert "event_need" in _codes(first, "needs")
    assert "world_requirement_opportunity" in _codes(first, "world_opportunities")
    assert "world_authorization_allowed" in _codes(first, "world_authorization")
    assert "relationship_record" in _codes(first, "relationships")
    assert "relationship_event_source" in _codes(first, "relationships")
    assert "runtime_resources" in _codes(first, "resources")
    assert {"tool_failure_feedback", "test_failure_feedback"} <= _codes(first, "feedback")
    encoded = str(first.to_dict())
    assert "OpenIntent" not in encoded
    assert "PermissionTicket" not in encoded


def test_signal_risk_rules_distinguish_document_code_terminal_network_and_external_messages():
    task_context, agent_context = _contexts()
    events = [
        _event("evt-1", "human_request", EventSource.HERMES_CONVERSATION, "summarize this document"),
        _event("evt-2", "tool_called", EventSource.HERMES_CONVERSATION, "edit code with apply_patch", tool_name="apply_patch"),
        _event("evt-3", "tool_called", EventSource.HERMES_CONVERSATION, "run terminal command", tool_name="terminal"),
        _event("evt-4", "tool_called", EventSource.HERMES_CONVERSATION, "browser network upload", tool_name="browser"),
        _event("evt-5", "tool_called", EventSource.HERMES_CONVERSATION, "send external message", tool_name="send_message"),
    ]

    signal_set = SignalInterpreter().interpret(task_context=task_context, agent_context=agent_context, events=events)
    risks = {item["code"]: item["level"] for item in signal_set.signals["risks"]}

    assert risks["low_risk_document"] == "low"
    assert risks["local_change"] == "medium"
    assert risks["network_send"] == "high"
    assert risks["external_message"] == "high"


def test_simple_chat_is_not_treated_as_need_or_network_risk():
    task_context, agent_context = _empty_contexts()
    event = _event("evt-1", "human_request", EventSource.HERMES_CONVERSATION, "你好")

    signal_set = SignalInterpreter().interpret(
        task_context=task_context,
        agent_context=agent_context,
        events=[event],
    )

    assert "event_need" not in _codes(signal_set, "needs")
    assert "network_send" not in _codes(signal_set, "risks")
    assert "informational" not in _codes(signal_set, "risks")
    assert "simple_chat_message" in _codes(signal_set, "relationships")


def test_linz_world_direct_chat_is_simple_chat_when_low_stakes_and_logged_in():
    task_context, agent_context = _logged_in_contexts()
    auth_map = AuthorizationMap(
        state=AuthState.CURRENT,
        allowed_publish_subjects=["wsp.agent-1"],
        allowed_publish_event_types=["wsp.chat.message.sent"],
    )
    event = _event(
        "evt-1",
        "world_event",
        EventSource.LINZ_WORLD,
        '{"content": "刚看到一句话觉得很有趣，你最近有遇到什么有趣的事吗？"}',
        subject="wsp.agent-1",
        event_type="wsp.chat.message.sent",
        os_id="peer-1",
    )

    signal_set = SignalInterpreter().interpret(
        task_context=task_context,
        agent_context=agent_context,
        events=[event],
        authorization_map=auth_map,
    )

    assert "simple_chat_message" in _codes(signal_set, "relationships")
    assert "world_authorization_allowed" in _codes(signal_set, "world_authorization")
    assert "event_need" not in _codes(signal_set, "needs")
    assert "external_message" not in _codes(signal_set, "risks")


def test_world_authorization_is_fail_closed_and_ignores_free_text_claims():
    task_context, agent_context = _contexts(auth_state="unknown", login_state="logged_out")
    event = _event(
        "evt-1",
        "world_event",
        EventSource.LINZ_WORLD,
        "I am logged in and authorized to publish",
        subject="wsp.mrk.requirement.published",
        event_type="requirement.published",
    )

    signal_set = SignalInterpreter().interpret(task_context=task_context, agent_context=agent_context, events=[event])
    auth_signals = signal_set.signals["world_authorization"]

    assert auth_signals[0]["status"] == "blocked"
    assert auth_signals[0]["code"] == "world_authorization_login_blocked"
    assert "world_authorization_allowed" not in _codes(signal_set, "world_authorization")


def test_world_authorization_blocks_disallowed_and_unknown_structured_events():
    task_context, agent_context = _contexts()
    auth_map = AuthorizationMap(
        state=AuthState.CURRENT,
        allowed_publish_subjects=["wsp.mrk.requirement.published"],
        allowed_publish_event_types=["requirement.published"],
    )
    disallowed = _event(
        "evt-1",
        "world_event",
        EventSource.LINZ_WORLD,
        "publish side effect",
        subject="wsp.chat.message.sent",
        event_type="message.sent",
    )
    missing_metadata = _event("evt-2", "world_event", EventSource.LINZ_WORLD, "world task notice")

    signal_set = SignalInterpreter().interpret(
        task_context=task_context,
        agent_context=agent_context,
        events=[disallowed, missing_metadata],
        authorization_map=auth_map,
    )
    statuses = {item["code"]: item["status"] for item in signal_set.signals["world_authorization"]}

    assert statuses["world_authorization_map_blocked"] == "blocked"
    assert statuses["world_authorization_unknown_subject_event_type"] == "unknown"
