from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.autonomous_loop import AutonomousRuntimeLoop
from agent.os_runtime.autonomous_scheduler import AutonomousScheduler
from agent.os_runtime.autonomous_state import AutonomousRuntimeState, AutonomousRuntimeStatus
from agent.os_runtime.config import OSRuntimeConfig


def _config(**autonomous):
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
        assert "world_publish" not in result.evidence["action_summary"]
        state = queue_repo.load_state("session-1")
        assert state is not None
        assert state.last_intent_id
        assert state.last_action_summary
        assert event_repo.list_by_session("session-1")
    finally:
        event_repo.close()
        queue_repo.close()
