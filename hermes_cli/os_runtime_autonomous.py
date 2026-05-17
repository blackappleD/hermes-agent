"""Command service for resident autonomous os_runtime controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.os_runtime.action_executor import AutonomousActionExecutor
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.approval import OSRuntimeApprovalStore
from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.autonomous_loop import AutonomousRuntimeLoop
from agent.os_runtime.autonomous_scheduler import AutonomousScheduler
from agent.os_runtime.config import OSRuntimeConfig


@dataclass
class AutonomousCommandResult:
    output: str
    decision: dict[str, Any] | None = None


def handle_autonomous_command(
    arg: str,
    *,
    session_id: str,
    profile_id: str = "",
    config: OSRuntimeConfig,
    repository: RuntimeQueueRepository | None = None,
) -> AutonomousCommandResult:
    repo = repository or RuntimeQueueRepository(enabled=config.enabled)
    scheduler = AutonomousScheduler(
        session_id,
        profile_id=profile_id,
        config=config,
        repository=repo,
    )
    text = (arg or "").strip()
    parts = text.split(maxsplit=1)
    subcommand = (parts[0].lower() if parts else "status") or "status"

    if subcommand == "status":
        state = scheduler.start() if _autostart_status(config, repo, session_id) else repo.load_state(session_id)
        if state is None:
            return AutonomousCommandResult("Autonomous OS Runtime inactive.")
        return AutonomousCommandResult(
            (
                f"Autonomous OS Runtime {state.status}: loop={state.loop_id or 'none'} "
                f"wake={state.last_wake_reason or 'none'} budget={state.wakes_used}/{state.max_wakes_per_hour} "
                f"cooldown_until={state.cooldown_until or 'none'} arbitration="
                f"{state.last_arbitration.get('decision') or 'none'}"
            )
        )

    if not config.enabled:
        return AutonomousCommandResult("Autonomous OS Runtime disabled (`os_runtime.enabled=false`).")
    if not config.autonomous.enabled:
        return AutonomousCommandResult("Autonomous OS Runtime disabled (`os_runtime.autonomous.enabled=false`).")

    if subcommand == "pause":
        state = scheduler.pause()
        return AutonomousCommandResult(f"Autonomous OS Runtime paused: {state.paused_reason}")
    if subcommand == "resume":
        state = scheduler.resume()
        return AutonomousCommandResult(f"Autonomous OS Runtime resumed: {state.status}")
    if subcommand == "stop":
        state = scheduler.stop()
        return AutonomousCommandResult(f"Autonomous OS Runtime stopped: {state.paused_reason}")
    if subcommand == "tick":
        loop = AutonomousRuntimeLoop(
            session_id,
            profile_id=profile_id,
            config=config,
            queue_repository=repo,
            scheduler=scheduler,
        )
        result = loop.run_once(wake_reason="manual_tick")
        return AutonomousCommandResult(
            f"Autonomous tick {result.status}: {result.reason}",
            decision=result.evidence or None,
        )
    if subcommand == "inbox":
        rows = repo.list_inbox(session_id, limit=10)
        return AutonomousCommandResult(_rows("inbox", [row.to_dict() for row in rows]))
    if subcommand == "events":
        rows = repo.list_wakes(session_id, limit=10)
        return AutonomousCommandResult(_rows("wakes", [row.to_dict() for row in rows]))
    if subcommand == "intents":
        rows = repo.list_wakes(session_id, limit=10)
        payload = [
            {
                "wake_id": row.wake_id,
                "intent_id": row.intent_id,
                "decision": row.arbitration.get("decision"),
                "action_summary": row.action_summary,
            }
            for row in rows
        ]
        return AutonomousCommandResult(_rows("intents", payload))
    if subcommand == "approvals":
        event_repo = OSRuntimeEventRepository(enabled=config.enabled)
        try:
            store = OSRuntimeApprovalStore(event_repo)
            rows = [
                row.to_dict()
                for row in store.list(session_id=session_id, status="pending", limit=10)
            ]
            return AutonomousCommandResult(_rows("approvals", rows))
        finally:
            event_repo.close()
    if subcommand in {"approve", "deny"}:
        approval_id = (parts[1].strip() if len(parts) > 1 else "")
        if not approval_id:
            return AutonomousCommandResult(
                "Usage: /os_runtime autonomous approve <approval_id> | deny <approval_id>"
            )
        event_repo = OSRuntimeEventRepository(enabled=config.enabled)
        try:
            executor = AutonomousActionExecutor(config=config, repository=event_repo)
            if subcommand == "deny":
                resolved = executor.deny_approval(
                    approval_id,
                    session_id=session_id,
                    resolver="os_runtime_command",
                )
                if resolved is None:
                    return AutonomousCommandResult(f"Autonomous approval not found: {approval_id}")
                return AutonomousCommandResult(f"Autonomous approval denied: {approval_id}")
            result = executor.approve_and_execute(
                approval_id,
                session_id=session_id,
                resolver="os_runtime_command",
            )
            return AutonomousCommandResult(
                f"Autonomous approval {result.status}: {result.action_summary}",
                decision=result.to_dict(),
            )
        finally:
            event_repo.close()

    return AutonomousCommandResult(
        "Usage: /os_runtime autonomous status|pause|resume|stop|tick|inbox|events|intents|approvals|approve <id>|deny <id>"
    )


def _autostart_status(config: OSRuntimeConfig, repo: RuntimeQueueRepository, session_id: str) -> bool:
    return (
        config.enabled
        and config.autonomous.enabled
        and repo.load_state(session_id) is None
    )


def _rows(label: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"Autonomous {label}: none."
    lines = [f"Autonomous {label}:"]
    for row in rows:
        lines.append(
            "- "
            + " ".join(
                f"{key}={value}"
                for key, value in row.items()
                if key in {
                    "item_id",
                    "wake_id",
                    "approval_id",
                    "event_id",
                    "wake_reason",
                    "status",
                    "intent_id",
                    "arbitration_id",
                    "decision",
                    "action_summary",
                    "summary",
                }
                and value
            )
        )
    return "\n".join(lines)


__all__ = ["AutonomousCommandResult", "handle_autonomous_command"]
