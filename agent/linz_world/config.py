"""Configuration helpers for native Linz World support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_LINZ_WORLD_SERVICE_URL = "http://8.156.84.202:17878"
DEFAULT_LINZ_WORLD_NATS_URL = "nats://8.156.84.202:16331"

DEFAULT_LINZ_WORLD_BUBBLE_CONFIG: dict[str, Any] = {
    "enabled": True,
    "read_only": False,
    "allow_mutations": True,
    "require_approval_for_mutations": True,
    "allow_autonomous_create_demand": True,
    "allow_autonomous_accept_demand": True,
    "allow_autonomous_create_task": True,
    "allow_autonomous_mount": True,
    "allow_autonomous_submit_artifact": True,
    "allow_autonomous_review": True,
    "default_task_slot_id": "slot.task.coder",
    "artifact_ref_scheme": "hermes-session",
    "snapshot_context_max_events": 20,
    "snapshot_context_max_residues": 20,
}

DEFAULT_LINZ_WORLD_CONFIG: dict[str, Any] = {
    "enabled": True,
    "identity_required_on_agent_load": True,
    "service_url": DEFAULT_LINZ_WORLD_SERVICE_URL,
    "nats_url": DEFAULT_LINZ_WORLD_NATS_URL,
    "os_name": "Hermes",
    "os_type": "USER",
    "runtime_type": "Hermes",
    "persona_seed": "",
    "auto_listen": False,
    "auto_respond": False,
    "auto_publish": False,
    "self_drive": False,
    "event_retry_limit": 3,
    "event_query_limit": 20,
    "bubble": dict(DEFAULT_LINZ_WORLD_BUBBLE_CONFIG),
}


@dataclass(frozen=True)
class LinzWorldBubbleConfig:
    enabled: bool = True
    read_only: bool = False
    allow_mutations: bool = True
    require_approval_for_mutations: bool = True
    allow_autonomous_create_demand: bool = True
    allow_autonomous_accept_demand: bool = True
    allow_autonomous_create_task: bool = True
    allow_autonomous_mount: bool = True
    allow_autonomous_submit_artifact: bool = True
    allow_autonomous_review: bool = True
    default_task_slot_id: str = "slot.task.coder"
    artifact_ref_scheme: str = "hermes-session"
    snapshot_context_max_events: int = 20
    snapshot_context_max_residues: int = 20


@dataclass(frozen=True)
class LinzWorldConfig:
    enabled: bool = True
    identity_required_on_agent_load: bool = True
    service_url: str = DEFAULT_LINZ_WORLD_SERVICE_URL
    nats_url: str = DEFAULT_LINZ_WORLD_NATS_URL
    os_name: str = "Hermes"
    os_type: str = "USER"
    runtime_type: str = "Hermes"
    persona_seed: str = ""
    auto_listen: bool = False
    auto_respond: bool = False
    auto_publish: bool = False
    self_drive: bool = False
    event_retry_limit: int = 3
    event_query_limit: int = 20
    bubble: LinzWorldBubbleConfig = field(default_factory=LinzWorldBubbleConfig)

    @property
    def has_service_config(self) -> bool:
        return bool(self.service_url)


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_value(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _load_bubble_config(raw: dict[str, Any]) -> LinzWorldBubbleConfig:
    bubble_raw = raw.get("bubble") if isinstance(raw.get("bubble"), dict) else {}
    merged = {**DEFAULT_LINZ_WORLD_BUBBLE_CONFIG, **bubble_raw}
    return LinzWorldBubbleConfig(
        enabled=_bool_value(merged.get("enabled"), True),
        read_only=_bool_value(merged.get("read_only"), False),
        allow_mutations=_bool_value(merged.get("allow_mutations"), True),
        require_approval_for_mutations=_bool_value(
            merged.get("require_approval_for_mutations"),
            True,
        ),
        allow_autonomous_create_demand=_bool_value(merged.get("allow_autonomous_create_demand"), True),
        allow_autonomous_accept_demand=_bool_value(merged.get("allow_autonomous_accept_demand"), True),
        allow_autonomous_create_task=_bool_value(merged.get("allow_autonomous_create_task"), True),
        allow_autonomous_mount=_bool_value(merged.get("allow_autonomous_mount"), True),
        allow_autonomous_submit_artifact=_bool_value(merged.get("allow_autonomous_submit_artifact"), True),
        allow_autonomous_review=_bool_value(merged.get("allow_autonomous_review"), True),
        default_task_slot_id=str(merged.get("default_task_slot_id") or "slot.task.coder").strip() or "slot.task.coder",
        artifact_ref_scheme=str(merged.get("artifact_ref_scheme") or "hermes-session").strip() or "hermes-session",
        snapshot_context_max_events=_int_value(merged.get("snapshot_context_max_events"), 20, 1, 200),
        snapshot_context_max_residues=_int_value(merged.get("snapshot_context_max_residues"), 20, 1, 200),
    )


def load_linz_world_config(config: dict[str, Any] | None = None) -> LinzWorldConfig:
    if config is None:
        try:
            from hermes_cli.config import load_config

            config = load_config()
        except Exception:
            config = {}
    raw = {}
    if isinstance(config, dict):
        raw = config.get("linz_world") or {}
    if not isinstance(raw, dict):
        raw = {}
    merged = {**DEFAULT_LINZ_WORLD_CONFIG, **raw}
    service_url = str(raw.get("service_url") or DEFAULT_LINZ_WORLD_SERVICE_URL).strip()
    nats_url = str(merged.get("nats_url") or DEFAULT_LINZ_WORLD_NATS_URL).strip()
    retry_limit = int(merged.get("event_retry_limit") or 3)
    query_limit = int(merged.get("event_query_limit") or 20)
    os_type = str(merged.get("os_type") or merged.get("type") or "USER").strip().upper()
    if os_type not in {"USER", "SEV", "GOV"}:
        os_type = "USER"
    return LinzWorldConfig(
        enabled=_bool_value(merged.get("enabled"), True),
        identity_required_on_agent_load=_bool_value(
            merged.get("identity_required_on_agent_load"), True
        ),
        service_url=service_url,
        nats_url=nats_url,
        os_name=str(merged.get("os_name") or "Hermes").strip() or "Hermes",
        os_type=os_type,
        runtime_type=str(merged.get("runtime_type") or "Hermes").strip() or "Hermes",
        persona_seed=str(merged.get("persona_seed") or "").strip(),
        auto_listen=_bool_value(merged.get("auto_listen")),
        auto_respond=_bool_value(merged.get("auto_respond")),
        auto_publish=_bool_value(merged.get("auto_publish")),
        self_drive=_bool_value(merged.get("self_drive")),
        event_retry_limit=max(1, min(retry_limit, 3)),
        event_query_limit=max(1, min(query_limit, 100)),
        bubble=_load_bubble_config(raw),
    )


def validate_no_automatic_behaviors(config: LinzWorldConfig) -> list[str]:
    enabled = []
    for name in ("auto_listen", "auto_respond", "auto_publish", "self_drive"):
        if getattr(config, name):
            enabled.append(name)
    for name in (
        "allow_autonomous_create_demand",
        "allow_autonomous_accept_demand",
        "allow_autonomous_create_task",
        "allow_autonomous_mount",
        "allow_autonomous_submit_artifact",
        "allow_autonomous_review",
    ):
        if getattr(config.bubble, name):
            enabled.append(f"bubble.{name}")
    return enabled
