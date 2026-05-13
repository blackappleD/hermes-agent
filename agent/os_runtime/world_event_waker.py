"""Wake autonomous runtime from persisted and deduped Linz World events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.autonomous_inbox import AutonomousInbox
from agent.os_runtime.autonomous_loop import AutonomousRuntimeLoop, AutonomousRunResult
from agent.os_runtime.autonomous_scheduler import AutonomousScheduler
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config


@dataclass
class WorldEventWakeResult:
    queued: bool
    woke: bool
    reason: str
    item_id: str = ""
    run_result: AutonomousRunResult | None = None


class WorldEventWaker:
    def __init__(
        self,
        session_id: str,
        *,
        profile_id: str = "",
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        repository: RuntimeQueueRepository | None = None,
        inbox: AutonomousInbox | None = None,
        scheduler: AutonomousScheduler | None = None,
        loop: AutonomousRuntimeLoop | None = None,
    ) -> None:
        self.session_id = session_id
        self.profile_id = profile_id
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.repository = repository or RuntimeQueueRepository(enabled=self.config.enabled)
        self.inbox = inbox or AutonomousInbox(self.repository)
        self.scheduler = scheduler or AutonomousScheduler(
            session_id,
            profile_id=profile_id,
            config=self.config,
            repository=self.repository,
        )
        self.loop = loop or AutonomousRuntimeLoop(
            session_id,
            profile_id=profile_id,
            config=self.config,
            queue_repository=self.repository,
            scheduler=self.scheduler,
        )

    def handle_persisted_event(self, event_ref: Any) -> WorldEventWakeResult:
        if not self.config.enabled or not self.config.autonomous.enabled:
            return WorldEventWakeResult(False, False, "autonomous runtime disabled")
        if not self.config.autonomous.respond_to_world_events:
            return WorldEventWakeResult(False, False, "respond_to_world_events=false")
        if not _is_persisted(event_ref):
            return WorldEventWakeResult(False, False, "world event must be persisted before wake")

        item, inserted = self.inbox.enqueue(
            session_id=self.session_id,
            profile_id=self.profile_id,
            event_ref=event_ref,
            wake_reason="world_event",
        )
        if not inserted:
            return WorldEventWakeResult(False, False, "duplicate world event", item.item_id)

        run_result = self.loop.run_once(wake_reason="world_event", event_ref=event_ref)
        if run_result.ran:
            self.inbox.mark_handled(item.item_id)
        elif run_result.status == "skipped":
            self.inbox.mark_skipped(item.item_id, run_result.reason)
        else:
            self.inbox.mark_failed(item.item_id, run_result.reason)
        return WorldEventWakeResult(True, run_result.ran, run_result.reason, item.item_id, run_result)


def _is_persisted(event_ref: Any) -> bool:
    if event_ref is None:
        return False
    if isinstance(event_ref, dict):
        status = str(event_ref.get("status") or "")
        event_id = str(event_ref.get("event_id") or "")
        content_ref = str(event_ref.get("content_ref") or "")
        return bool(event_id and (status in {"recorded", "persisted"} or content_ref))
    event_id = str(getattr(event_ref, "event_id", "") or "")
    status = str(getattr(event_ref, "status", "") or "")
    content_ref = str(getattr(event_ref, "content_ref", "") or "")
    return bool(event_id and (status in {"recorded", "persisted"} or content_ref))


__all__ = ["WorldEventWakeResult", "WorldEventWaker"]
