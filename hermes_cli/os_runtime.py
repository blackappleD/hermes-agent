"""Shared `/os_runtime` command surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.driver import OSRuntimeDriver, OSRuntimeState


@dataclass
class OSRuntimeCommandResult:
    output: str
    send_message: str | None = None
    clear_pending: bool = False
    decision: dict[str, Any] | None = None


def load_runtime_config() -> OSRuntimeConfig:
    try:
        from hermes_cli.config import load_config

        raw = (load_config() or {}).get("os_runtime") or {}
    except Exception:
        raw = {}
    try:
        return OSRuntimeConfig.from_dict(raw)
    except Exception:
        return default_os_runtime_config()


def handle_os_runtime_command(
    arg: str,
    *,
    session_id: str,
    config: OSRuntimeConfig | dict[str, Any] | None = None,
    driver: OSRuntimeDriver | None = None,
) -> OSRuntimeCommandResult:
    if not session_id:
        return OSRuntimeCommandResult("OS Runtime unavailable: missing session.")

    cfg = _coerce_config(config)
    runtime = driver or OSRuntimeDriver(session_id=session_id, config=cfg)
    text = (arg or "").strip()
    parts = text.split(maxsplit=1)
    subcommand = (parts[0].lower() if parts else "status") or "status"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if subcommand == "status":
        return OSRuntimeCommandResult(_status_line(runtime.state, cfg))

    if not cfg.enabled and subcommand in {"passive", "goal", "pause", "resume", "clear", "tick"}:
        return OSRuntimeCommandResult("OS Runtime is disabled by config (`os_runtime.enabled=false`).")

    if subcommand == "passive":
        state = runtime.set_passive()
        return OSRuntimeCommandResult(
            f"OS Runtime passive mode enabled ({state.turns_used}/{state.max_turns} turns used)."
        )

    if subcommand == "goal":
        if not rest:
            return OSRuntimeCommandResult("Usage: /os_runtime goal <text>")
        try:
            state = runtime.set_goal(rest)
        except ValueError as exc:
            return OSRuntimeCommandResult(f"Invalid OS Runtime goal: {exc}")
        return OSRuntimeCommandResult(
            (
                f"OS Runtime assisted goal set ({state.max_turns}-turn budget): {state.goal}\n"
                "Continuation is limited to low-risk natural-language or draft steps."
            ),
            send_message=state.goal,
        )

    if subcommand == "pause":
        state = runtime.pause()
        if state is None:
            return OSRuntimeCommandResult("No OS Runtime goal or passive state is active.", clear_pending=True)
        return OSRuntimeCommandResult(f"OS Runtime paused: {state.goal or state.status}", clear_pending=True)

    if subcommand == "resume":
        state = runtime.resume()
        if state is None:
            return OSRuntimeCommandResult("No OS Runtime goal to resume.")
        return OSRuntimeCommandResult(f"OS Runtime resumed: {state.goal}")

    if subcommand == "clear":
        had_state = runtime.state is not None
        runtime.clear()
        return OSRuntimeCommandResult(
            "OS Runtime cleared." if had_state else "No OS Runtime state is active.",
            clear_pending=True,
        )

    if subcommand == "tick":
        decision = runtime.evaluate_after_turn(
            "manual tick",
            source="manual_tick",
            recent_event={
                "event_id": f"os-runtime-tick:{session_id}",
                "event_type": "manual_tick",
                "source": "runtime_feedback",
                "session_id": session_id,
                "summary": "manual os_runtime tick",
                "metadata": {"manual": True},
            },
        )
        return OSRuntimeCommandResult(
            decision.message or f"OS Runtime tick: {decision.reason}",
            send_message=decision.continuation_prompt if decision.should_continue else None,
            decision=decision.to_dict(),
        )

    return OSRuntimeCommandResult(
        "Usage: /os_runtime status|passive|goal <text>|pause|resume|clear|tick"
    )


def _coerce_config(config: OSRuntimeConfig | dict[str, Any] | None) -> OSRuntimeConfig:
    if isinstance(config, OSRuntimeConfig):
        return config
    if isinstance(config, dict):
        return OSRuntimeConfig.from_dict(config)
    return load_runtime_config()


def _status_line(state: OSRuntimeState | None, config: OSRuntimeConfig) -> str:
    if not config.enabled:
        return "OS Runtime disabled (`os_runtime.enabled=false`)."
    if state is None or state.status in {"inactive", "cleared"}:
        return "No active OS Runtime state. Use /os_runtime passive or /os_runtime goal <text>."
    turns = f"{state.turns_used}/{state.max_turns} turns"
    if state.status == "passive":
        return f"OS Runtime passive ({turns}). Last reason: {state.last_decision_reason or 'none'}"
    if state.status == "assisted":
        arbitration = state.last_arbitration.get("decision") or "none"
        return f"OS Runtime assisted ({turns}): {state.goal} | arbitration={arbitration}"
    if state.status == "paused":
        return f"OS Runtime paused ({turns}): {state.goal or '(no goal)'} | {state.paused_reason or 'paused'}"
    return f"OS Runtime {state.status} ({turns}): {state.goal}"


__all__ = [
    "OSRuntimeCommandResult",
    "handle_os_runtime_command",
    "load_runtime_config",
]
