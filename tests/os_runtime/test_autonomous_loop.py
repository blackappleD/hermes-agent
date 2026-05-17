from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent.linz_world.models import AuthState, AuthorizationMap, LoginState
from agent.os_runtime.adapters.context import ContextSnapshot
from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEvent, OSRuntimeEventRepository
from agent.os_runtime.autonomous_loop import AutonomousRuntimeLoop
from agent.os_runtime.autonomous_scheduler import AutonomousScheduler
from agent.os_runtime.autonomous_state import AutonomousRuntimeState, AutonomousRuntimeStatus
from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.domain import AgentContextView, EventSource, TaskContextView
from agent.os_runtime.engine.signals import SignalInterpreter


def _config(**autonomous):
    intent_generation = autonomous.pop("intent_generation", "llm")
    defaults = {
        "enabled": True,
        "idle_cooldown_seconds": 60,
        "max_wakes_per_hour": 2,
        "max_turns_per_wake": 1,
    }
    defaults.update(autonomous)
    return OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "intent_generation": intent_generation,
            "autonomous": defaults,
        }
    )


def test_autonomous_state_round_trip_and_safe_defaults():
    state = AutonomousRuntimeState(
        status=AutonomousRuntimeStatus.IDLE.value,
        loop_id="loop-1",
        session_id="session-1",
        max_wakes_per_hour=5,
    )

    restored = AutonomousRuntimeState.from_json(state.to_json())

    assert restored.status == "idle"
    assert restored.loop_id == "loop-1"
    assert restored.session_id == "session-1"
    assert restored.max_wakes_per_hour == 5
    assert restored.last_arbitration == {}


def test_scheduler_start_pause_resume_stop_cooldown_and_budget(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repo = RuntimeQueueRepository(root=tmp_path)
    scheduler = AutonomousScheduler(
        "session-1",
        config=_config(idle_cooldown_seconds=30, max_wakes_per_hour=1),
        repository=repo,
        now=lambda: now,
    )

    try:
        state = scheduler.start()
        assert state.status == "idle"

        first = scheduler.wake(reason="manual_tick")
        assert first.allowed is True
        assert first.max_turns == 1

        scheduler.finish_wake(action_summary="report_only")
        blocked_by_cooldown = scheduler.wake(reason="manual_tick")
        assert blocked_by_cooldown.allowed is False
        assert "cooldown" in blocked_by_cooldown.reason

        now = now + timedelta(seconds=31)
        blocked_by_budget = scheduler.wake(reason="manual_tick")
        assert blocked_by_budget.allowed is False
        assert "budget" in blocked_by_budget.reason

        assert scheduler.pause().status == "paused"
        assert scheduler.wake(reason="manual_tick").allowed is False
        assert scheduler.resume().status == "idle"
        assert scheduler.stop().status == "stopped"
    finally:
        repo.close()


def test_autonomous_loop_tick_generates_low_risk_evidence_without_goal(tmp_path):
    cfg = _config(idle_cooldown_seconds=0)
    queue_repo = RuntimeQueueRepository(root=tmp_path)
    event_repo = OSRuntimeEventRepository(root=tmp_path)
    loop = AutonomousRuntimeLoop(
        "session-1",
        config=cfg,
        queue_repository=queue_repo,
        event_repository=event_repo,
    )

    try:
        loop.scheduler.start()
        result = loop.run_once(wake_reason="manual_tick")

        assert result.ran is True
        assert result.status == "completed"
        assert result.evidence["open_intent"]["intent_id"]
        assert result.evidence["arbitration"]["decision"] in {"report_only", "require_approval", "reject"}
        assert result.evidence["execution"]["status"] in {"completed", "approval_required", "rejected", "blocked"}
        assert result.evidence["evidence_package"]["evidence_id"]
        assert "world_publish" not in result.evidence["action_summary"]
        state = queue_repo.load_state("session-1")
        assert state is not None
        assert state.last_intent_id
        assert state.last_action_summary
        assert event_repo.list_by_session("session-1")
    finally:
        event_repo.close()
        queue_repo.close()


def test_autonomous_world_wake_uses_current_event_for_signals_not_stale_history(tmp_path):
    cfg = _config(idle_cooldown_seconds=0, intent_generation="rule")
    queue_repo = RuntimeQueueRepository(root=tmp_path)
    event_repo = OSRuntimeEventRepository(root=tmp_path)
    captured = {}

    class CapturingSignalInterpreter:
        def __init__(self):
            self.delegate = SignalInterpreter(config=cfg)

        def interpret(self, **kwargs):
            captured["event_ids"] = [getattr(event, "event_id", "") for event in kwargs.get("events") or []]
            return self.delegate.interpret(**kwargs)

    class ContextWithStaleHistory:
        def build_context(self, **kwargs):
            current_events = list(kwargs.get("recent_events") or [])
            stale_event = OSRuntimeEvent(
                event_id="old-local-change",
                event_type="human_request",
                source=EventSource.HERMES_CONVERSATION,
                session_id="session-1",
                timestamp="2026-01-01T00:00:00Z",
                summary="please apply_patch code and run pytest",
            )
            auth = {
                "state": AuthState.CURRENT.value,
                "login_state": LoginState.LOGGED_IN.value,
                "allowed_capabilities": ["publish"],
                "allowed_publish_subjects": ["wsp.agent_b"],
                "allowed_publish_event_types": ["wsp.chat.message.sent"],
            }
            auth_map = AuthorizationMap(
                state=AuthState.CURRENT,
                allowed_capabilities=["publish"],
                allowed_publish_subjects=["wsp.agent_b"],
                allowed_publish_event_types=["wsp.chat.message.sent"],
            )
            return ContextSnapshot(
                task_context=TaskContextView(
                    task_id="autonomous:session-1:world_event",
                    session_id="session-1",
                    recent_event_ids=[stale_event.event_id, *[event.event_id for event in current_events]],
                    metadata={"authorization": auth, "resource_state": {}},
                ),
                agent_context=AgentContextView(
                    profile_name="test",
                    capabilities=["publish"],
                    metadata={"authorization": auth},
                ),
                recent_events=[stale_event, *current_events],
                authorization_map=auth_map,
            )

    loop = AutonomousRuntimeLoop(
        "session-1",
        config=cfg,
        queue_repository=queue_repo,
        event_repository=event_repo,
        context_adapter=ContextWithStaleHistory(),
        signal_interpreter=CapturingSignalInterpreter(),
    )

    try:
        loop.scheduler.start()
        result = loop.run_once(
            wake_reason="world_event",
            event_ref={
                "event_id": "evt-current-chat",
                "event_type": "world_event",
                "source": EventSource.LINZ_WORLD.value,
                "session_id": "session-1",
                "summary": "你好",
                "metadata": {
                    "subject": "wsp.agent_b",
                    "event_type": "wsp.chat.message.sent",
                    "os_id": "peer-1",
                },
            },
        )

        assert captured["event_ids"] == ["evt-current-chat"]
        assert result.evidence["self_prompt"]["target_direction"]["metadata"]["event_id"] == "evt-current-chat"
        assert result.evidence["arbitration"]["decision"] == "report_only"
        risk_evidence = result.evidence["action_potential"]["metadata"]["score_evidence"]["risk_cost"]
        assert not any("old-local-change" in item for item in risk_evidence)
    finally:
        event_repo.close()
        queue_repo.close()
