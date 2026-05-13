"""Configuration helpers for native Linz World support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_LINZ_WORLD_SERVICE_URL = "http://8.156.84.202:17878"
DEFAULT_LINZ_WORLD_NATS_URL = "nats://8.156.84.202:16331"

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
}


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

    @property
    def has_service_config(self) -> bool:
        return bool(self.service_url)


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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
    )


def validate_no_automatic_behaviors(config: LinzWorldConfig) -> list[str]:
    enabled = []
    for name in ("auto_listen", "auto_respond", "auto_publish", "self_drive"):
        if getattr(config, name):
            enabled.append(name)
    return enabled
