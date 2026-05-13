"""Serializable state for the resident autonomous os_runtime loop."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from agent.linz_world.models import utc_now_iso


class AutonomousRuntimeStatus(str, Enum):
    INACTIVE = "inactive"
    IDLE = "idle"
    SLEEPING = "sleeping"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class AutonomousWakeRecord:
    wake_id: str
    session_id: str = ""
    profile_id: str = ""
    wake_reason: str = ""
    event_id: str = ""
    status: str = "started"
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = ""
    turns_used: int = 0
    stop_reason: str = ""
    intent_id: str = ""
    arbitration: dict[str, Any] = field(default_factory=dict)
    action_summary: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutonomousWakeRecord":
        if not isinstance(data, dict):
            raise TypeError("AutonomousWakeRecord.from_dict() requires a dict")
        return cls(
            wake_id=str(data.get("wake_id") or ""),
            session_id=str(data.get("session_id") or ""),
            profile_id=str(data.get("profile_id") or ""),
            wake_reason=str(data.get("wake_reason") or ""),
            event_id=str(data.get("event_id") or ""),
            status=str(data.get("status") or "started"),
            started_at=str(data.get("started_at") or utc_now_iso()),
            finished_at=str(data.get("finished_at") or ""),
            turns_used=int(data.get("turns_used") or 0),
            stop_reason=str(data.get("stop_reason") or ""),
            intent_id=str(data.get("intent_id") or ""),
            arbitration=dict(data.get("arbitration") or {}),
            action_summary=str(data.get("action_summary") or ""),
            evidence=dict(data.get("evidence") or {}),
        )


@dataclass
class AutonomousRuntimeState:
    status: str = AutonomousRuntimeStatus.INACTIVE.value
    loop_id: str = ""
    profile_id: str = ""
    session_id: str = ""
    level: str = "tension-driven"
    last_wake_reason: str = ""
    last_wake_event_id: str = ""
    last_turn_event_id: str = ""
    last_tick_at: str = ""
    wake_window_started_at: str = ""
    wakes_used: int = 0
    max_wakes_per_hour: int = 20
    cooldown_until: str = ""
    last_intent_id: str = ""
    last_arbitration: dict[str, Any] = field(default_factory=dict)
    last_action_summary: str = ""
    paused_reason: str = ""
    life_state: dict[str, Any] = field(default_factory=dict)
    tension_set: dict[str, Any] = field(default_factory=dict)
    action_potential: dict[str, Any] = field(default_factory=dict)
    self_prompt: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = str(self.status)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutonomousRuntimeState":
        if not isinstance(data, dict):
            raise TypeError("AutonomousRuntimeState.from_dict() requires a dict")
        return cls(
            status=str(data.get("status") or AutonomousRuntimeStatus.INACTIVE.value),
            loop_id=str(data.get("loop_id") or ""),
            profile_id=str(data.get("profile_id") or ""),
            session_id=str(data.get("session_id") or ""),
            level=str(data.get("level") or "tension-driven"),
            last_wake_reason=str(data.get("last_wake_reason") or ""),
            last_wake_event_id=str(data.get("last_wake_event_id") or ""),
            last_turn_event_id=str(data.get("last_turn_event_id") or ""),
            last_tick_at=str(data.get("last_tick_at") or ""),
            wake_window_started_at=str(data.get("wake_window_started_at") or ""),
            wakes_used=int(data.get("wakes_used") or 0),
            max_wakes_per_hour=int(data.get("max_wakes_per_hour") or 20),
            cooldown_until=str(data.get("cooldown_until") or ""),
            last_intent_id=str(data.get("last_intent_id") or ""),
            last_arbitration=dict(data.get("last_arbitration") or {}),
            last_action_summary=str(data.get("last_action_summary") or ""),
            paused_reason=str(data.get("paused_reason") or ""),
            life_state=dict(data.get("life_state") or {}),
            tension_set=dict(data.get("tension_set") or {}),
            action_potential=dict(data.get("action_potential") or {}),
            self_prompt=dict(data.get("self_prompt") or {}),
            evidence=dict(data.get("evidence") or {}),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )

    @classmethod
    def from_json(cls, raw: str) -> "AutonomousRuntimeState":
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("AutonomousRuntimeState JSON must decode to an object")
        return cls.from_dict(data)


__all__ = [
    "AutonomousRuntimeState",
    "AutonomousRuntimeStatus",
    "AutonomousWakeRecord",
]
