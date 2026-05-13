"""Budgeted scheduler for the resident autonomous os_runtime loop."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.autonomous_state import (
    AutonomousRuntimeState,
    AutonomousRuntimeStatus,
)
from agent.os_runtime.config import AutonomousRuntimeConfig, OSRuntimeConfig, default_os_runtime_config


@dataclass
class WakeDecision:
    allowed: bool
    reason: str = ""
    state: AutonomousRuntimeState | None = None
    max_turns: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)


class AutonomousScheduler:
    def __init__(
        self,
        session_id: str,
        *,
        profile_id: str = "",
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        repository: RuntimeQueueRepository | None = None,
        now: Any = None,
    ) -> None:
        self.session_id = session_id
        self.profile_id = profile_id
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.autonomous_config: AutonomousRuntimeConfig = self.config.autonomous
        self.repository = repository or RuntimeQueueRepository(enabled=self.config.enabled)
        self._now = now

    def start(self) -> AutonomousRuntimeState:
        state = self._state()
        if not self.config.enabled or not self.autonomous_config.enabled:
            state.status = AutonomousRuntimeStatus.INACTIVE.value
            state.paused_reason = "autonomous runtime disabled"
        elif state.status not in {AutonomousRuntimeStatus.PAUSED.value, AutonomousRuntimeStatus.STOPPED.value}:
            state.status = AutonomousRuntimeStatus.IDLE.value
            state.paused_reason = ""
        state.max_wakes_per_hour = self.autonomous_config.max_wakes_per_hour
        return self.repository.save_state(state)

    def pause(self, reason: str = "user-paused") -> AutonomousRuntimeState:
        state = self._state()
        state.status = AutonomousRuntimeStatus.PAUSED.value
        state.paused_reason = reason
        return self.repository.save_state(state)

    def resume(self) -> AutonomousRuntimeState:
        state = self._state()
        if self.config.enabled and self.autonomous_config.enabled:
            state.status = AutonomousRuntimeStatus.IDLE.value
            state.paused_reason = ""
        return self.repository.save_state(state)

    def stop(self, reason: str = "user-stopped") -> AutonomousRuntimeState:
        state = self._state()
        state.status = AutonomousRuntimeStatus.STOPPED.value
        state.paused_reason = reason
        return self.repository.save_state(state)

    def tick(self, *, reason: str = "tick", event_id: str = "") -> WakeDecision:
        return self.wake(reason=reason, event_id=event_id)

    def wake(self, *, reason: str, event_id: str = "") -> WakeDecision:
        state = self._state()
        if not self.config.enabled:
            state.status = AutonomousRuntimeStatus.INACTIVE.value
            state.paused_reason = "os_runtime.enabled=false"
            self.repository.save_state(state)
            return WakeDecision(False, state.paused_reason, state)
        if not self.autonomous_config.enabled:
            state.status = AutonomousRuntimeStatus.INACTIVE.value
            state.paused_reason = "os_runtime.autonomous.enabled=false"
            self.repository.save_state(state)
            return WakeDecision(False, state.paused_reason, state)
        if state.status == AutonomousRuntimeStatus.STOPPED.value:
            return WakeDecision(False, "autonomous runtime stopped", state)
        if state.status == AutonomousRuntimeStatus.PAUSED.value:
            return WakeDecision(False, state.paused_reason or "autonomous runtime paused", state)

        now = self._datetime()
        self._reset_budget_window(state, now)
        cooldown_until = _parse_utc(state.cooldown_until)
        if cooldown_until is not None and now < cooldown_until:
            return WakeDecision(
                False,
                "idle cooldown active",
                state,
                diagnostics={"cooldown_until": state.cooldown_until},
            )
        if state.wakes_used >= self.autonomous_config.max_wakes_per_hour:
            return WakeDecision(
                False,
                "hourly wake budget exhausted",
                state,
                diagnostics={
                    "wakes_used": state.wakes_used,
                    "max_wakes_per_hour": self.autonomous_config.max_wakes_per_hour,
                },
            )

        state.status = AutonomousRuntimeStatus.RUNNING.value
        state.last_wake_reason = reason
        state.last_wake_event_id = event_id
        if reason in {"tick", "manual_tick"}:
            state.last_tick_at = _iso(now)
        state.wakes_used += 1
        state.max_wakes_per_hour = self.autonomous_config.max_wakes_per_hour
        self.repository.save_state(state)
        return WakeDecision(
            True,
            "wake accepted",
            state,
            max_turns=self.autonomous_config.max_turns_per_wake,
        )

    def finish_wake(
        self,
        *,
        status: str = AutonomousRuntimeStatus.SLEEPING.value,
        action_summary: str = "",
        cooldown: bool = True,
    ) -> AutonomousRuntimeState:
        state = self._state()
        state.status = status
        state.last_action_summary = action_summary
        if cooldown and self.autonomous_config.idle_cooldown_seconds > 0:
            state.cooldown_until = _iso(
                self._datetime() + timedelta(seconds=self.autonomous_config.idle_cooldown_seconds)
            )
        return self.repository.save_state(state)

    def _state(self) -> AutonomousRuntimeState:
        state = self.repository.load_state(self.session_id)
        if state is not None:
            return state
        return AutonomousRuntimeState(
            status=AutonomousRuntimeStatus.INACTIVE.value,
            loop_id=f"aloop-{uuid.uuid4().hex}",
            profile_id=self.profile_id,
            session_id=self.session_id,
            max_wakes_per_hour=self.autonomous_config.max_wakes_per_hour,
        )

    def _reset_budget_window(self, state: AutonomousRuntimeState, now: datetime) -> None:
        window_start = _parse_utc(state.wake_window_started_at)
        if window_start is None or now - window_start >= timedelta(hours=1):
            state.wake_window_started_at = _iso(now)
            state.wakes_used = 0

    def _datetime(self) -> datetime:
        if self._now is None:
            return datetime.now(timezone.utc)
        value = self._now()
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return _parse_utc(str(value)) or datetime.now(timezone.utc)


def _parse_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = ["AutonomousScheduler", "WakeDecision", "utc_now_iso"]
