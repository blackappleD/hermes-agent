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
            extra=extra,
        )


def default_os_runtime_config() -> OSRuntimeConfig:
    return OSRuntimeConfig()


def load_os_runtime_config(data: Mapping[str, Any] | None) -> OSRuntimeConfig:
    return OSRuntimeConfig.from_dict(data)


DEFAULT_OS_RUNTIME_CONFIG = default_os_runtime_config().to_dict(include_extra=False)


__all__ = [
    "DEFAULT_OS_RUNTIME_CONFIG",
    "OSRuntimeConfig",
    "OSRuntimeRiskConfig",
    "default_os_runtime_config",
    "load_os_runtime_config",
]
