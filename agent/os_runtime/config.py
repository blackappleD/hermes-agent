"""Configuration contract for the os_runtime protocol layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agent.os_runtime.domain import RiskLevel


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass
class AutonomousRuntimeConfig:
    enabled: bool = False
    start_on_agent_load: bool = False
    start_with_gateway: bool = False
    apply_to_all_turns: bool = False
    pre_turn_evaluation: bool = True
    post_turn_evaluation: bool = True
    inject_self_prompt: bool = False
    respond_to_world_events: bool = False
    tick_interval_seconds: int = 30
    idle_cooldown_seconds: int = 60
    max_turns_per_wake: int = 3
    max_wakes_per_hour: int = 20
    allow_tool_execution: bool = False
    allow_world_publish: bool = False
    require_approval_for_world_publish: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_extra: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "enabled": self.enabled,
            "start_on_agent_load": self.start_on_agent_load,
            "start_with_gateway": self.start_with_gateway,
            "apply_to_all_turns": self.apply_to_all_turns,
            "pre_turn_evaluation": self.pre_turn_evaluation,
            "post_turn_evaluation": self.post_turn_evaluation,
            "inject_self_prompt": self.inject_self_prompt,
            "respond_to_world_events": self.respond_to_world_events,
            "tick_interval_seconds": self.tick_interval_seconds,
            "idle_cooldown_seconds": self.idle_cooldown_seconds,
            "max_turns_per_wake": self.max_turns_per_wake,
            "max_wakes_per_hour": self.max_wakes_per_hour,
            "allow_tool_execution": self.allow_tool_execution,
            "allow_world_publish": self.allow_world_publish,
            "require_approval_for_world_publish": self.require_approval_for_world_publish,
        }
        if include_extra:
            data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "AutonomousRuntimeConfig":
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise TypeError("os_runtime.autonomous must be a mapping")

        known = {
            "enabled",
            "start_on_agent_load",
            "start_with_gateway",
            "apply_to_all_turns",
            "pre_turn_evaluation",
            "post_turn_evaluation",
            "inject_self_prompt",
            "respond_to_world_events",
            "tick_interval_seconds",
            "idle_cooldown_seconds",
            "max_turns_per_wake",
            "max_wakes_per_hour",
            "allow_tool_execution",
            "allow_world_publish",
            "require_approval_for_world_publish",
        }
        extra = {key: value for key, value in data.items() if key not in known}
        return cls(
            enabled=_coerce_bool(data.get("enabled"), False),
            start_on_agent_load=_coerce_bool(data.get("start_on_agent_load"), False),
            start_with_gateway=_coerce_bool(data.get("start_with_gateway"), False),
            apply_to_all_turns=_coerce_bool(data.get("apply_to_all_turns"), False),
            pre_turn_evaluation=_coerce_bool(data.get("pre_turn_evaluation"), True),
            post_turn_evaluation=_coerce_bool(data.get("post_turn_evaluation"), True),
            inject_self_prompt=_coerce_bool(data.get("inject_self_prompt"), False),
            respond_to_world_events=_coerce_bool(data.get("respond_to_world_events"), False),
            tick_interval_seconds=max(1, int(data.get("tick_interval_seconds", 30))),
            idle_cooldown_seconds=max(0, int(data.get("idle_cooldown_seconds", 60))),
            max_turns_per_wake=max(1, int(data.get("max_turns_per_wake", 3))),
            max_wakes_per_hour=max(1, int(data.get("max_wakes_per_hour", 20))),
            allow_tool_execution=_coerce_bool(data.get("allow_tool_execution"), False),
            allow_world_publish=_coerce_bool(data.get("allow_world_publish"), False),
            require_approval_for_world_publish=_coerce_bool(
                data.get("require_approval_for_world_publish"),
                True,
            ),
            extra=extra,
        )


@dataclass
class OSRuntimeRiskConfig:
    require_approval_at: RiskLevel = RiskLevel.MEDIUM

    def to_dict(self) -> dict[str, Any]:
        return {"require_approval_at": self.require_approval_at.value}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "OSRuntimeRiskConfig":
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise TypeError("os_runtime.risk must be a mapping")
        value = data.get("require_approval_at", RiskLevel.MEDIUM.value)
        return cls(require_approval_at=RiskLevel(value))


@dataclass
class OSRuntimeConfig:
    enabled: bool = False
    mode: str = "passive"
    max_continuation_turns: int = 8
    tick_interval_seconds: int = 0
    allow_tool_execution: bool = False
    allow_auto_continuation: bool = False
    event_store: str = "sessiondb_side_tables"
    model_task: str = "os_runtime_intent"
    risk: OSRuntimeRiskConfig = field(default_factory=OSRuntimeRiskConfig)
    autonomous: AutonomousRuntimeConfig = field(default_factory=AutonomousRuntimeConfig)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_extra: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "enabled": self.enabled,
            "mode": self.mode,
            "max_continuation_turns": self.max_continuation_turns,
            "tick_interval_seconds": self.tick_interval_seconds,
            "allow_tool_execution": self.allow_tool_execution,
            "allow_auto_continuation": self.allow_auto_continuation,
            "event_store": self.event_store,
            "model_task": self.model_task,
            "risk": self.risk.to_dict(),
            "autonomous": self.autonomous.to_dict(include_extra=include_extra),
        }
        if include_extra:
            data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "OSRuntimeConfig":
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise TypeError("os_runtime config must be a mapping")

        known = {
            "enabled",
            "mode",
            "max_continuation_turns",
            "tick_interval_seconds",
            "allow_tool_execution",
            "allow_auto_continuation",
            "event_store",
            "model_task",
            "risk",
            "autonomous",
        }
        extra = {key: value for key, value in data.items() if key not in known}
        return cls(
            enabled=_coerce_bool(data.get("enabled"), False),
            mode=str(data.get("mode", "passive")),
            max_continuation_turns=int(data.get("max_continuation_turns", 8)),
            tick_interval_seconds=int(data.get("tick_interval_seconds", 0)),
            allow_tool_execution=_coerce_bool(data.get("allow_tool_execution"), False),
            allow_auto_continuation=_coerce_bool(
                data.get("allow_auto_continuation"),
                False,
            ),
            event_store=str(data.get("event_store", "sessiondb_side_tables")),
            model_task=str(data.get("model_task", "os_runtime_intent")),
            risk=OSRuntimeRiskConfig.from_dict(data.get("risk")),
            autonomous=AutonomousRuntimeConfig.from_dict(data.get("autonomous")),
            extra=extra,
        )


def default_os_runtime_config() -> OSRuntimeConfig:
    return OSRuntimeConfig()


def load_os_runtime_config(data: Mapping[str, Any] | None) -> OSRuntimeConfig:
    return OSRuntimeConfig.from_dict(data)


DEFAULT_OS_RUNTIME_CONFIG = default_os_runtime_config().to_dict(include_extra=False)


__all__ = [
    "AutonomousRuntimeConfig",
    "DEFAULT_OS_RUNTIME_CONFIG",
    "OSRuntimeConfig",
    "OSRuntimeRiskConfig",
    "default_os_runtime_config",
    "load_os_runtime_config",
]
