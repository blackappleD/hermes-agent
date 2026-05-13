from __future__ import annotations

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEvent, OSRuntimeEventRepository
from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.domain import EventSource
from agent.os_runtime.world_event_waker import WorldEventWaker


def _config():
    return OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": {
                "enabled": True,
                "respond_to_world_events": True,
                "idle_cooldown_seconds": 0,
                "allow_world_publish": False,
            },
        }
    )


def _event(event_id="world-1"):
    return OSRuntimeEvent(
        event_id=event_id,
        event_type="world_event",
        source=EventSource.LINZ_WORLD,
        session_id="session-1",
        timestamp=utc_now_iso(),
        summary="world message",
        metadata={"sequence_key": f"seq:{event_id}", "event_type": "message"},
        status="recorded",
    )


def test_world_event_waker_requires_persisted_event(tmp_path):
    repo = RuntimeQueueRepository(root=tmp_path)
    waker = WorldEventWaker("session-1", config=_config(), repository=repo)

    try:
        result = waker.handle_persisted_event({"event_id": "world-1", "status": "new"})

        assert result.queued is False
        assert "persisted" in result.reason
    finally:
        repo.close()


def test_world_event_waker_dedupes_and_runs_once_without_publish(tmp_path):
    queue_repo = RuntimeQueueRepository(root=tmp_path)
    event_repo = OSRuntimeEventRepository(root=tmp_path)
    cfg = _config()
    event = event_repo.append(_event())
    waker = WorldEventWaker(
        "session-1",
        config=cfg,
        repository=queue_repo,
    )
    waker.loop.event_repository = event_repo

    try:
        first = waker.handle_persisted_event(event)
        second = waker.handle_persisted_event(event)

        assert first.queued is True
        assert first.woke is True
        assert second.queued is False
        assert "duplicate" in second.reason
        assert len(queue_repo.list_inbox("session-1")) == 1
        wake = queue_repo.list_wakes("session-1")[0]
        assert "world_publish" not in wake.action_summary
        assert wake.arbitration.get("decision") in {"report_only", "require_approval", "reject"}
    finally:
        event_repo.close()
        queue_repo.close()
