"""Fake-friendly Linz World service boundary."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

import httpx

from .models import utc_now_iso


class LinzWorldServiceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class LinzWorldService(Protocol):
    def register_original_spirit(self, hermes_profile: str, os_name: str) -> dict[str, Any]: ...
    def login(self, identity: dict[str, Any]) -> dict[str, Any]: ...
    def logout(self, token_ref: str) -> dict[str, Any]: ...
    def refresh_authorization_map(self, identity: dict[str, Any], token_ref: str) -> dict[str, Any]: ...
    def publish_event(self, token_ref: str, subject: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def invoke_compute(self, token_ref: str, task: str, input_data: dict[str, Any]) -> dict[str, Any]: ...
    def write_memory(self, token_ref: str, artifact_ref: str, sink_reason: str, summary: str) -> dict[str, Any]: ...
    def read_relationships(self, token_ref: str, counterparty_id: str = "") -> dict[str, Any]: ...
    def add_active_relationship(self, token_ref: str, counterparty_id: str, summary: str = "") -> dict[str, Any]: ...


class LocalLinzWorldService:
    """Deterministic local service used when no remote service URL is configured."""

    def register_original_spirit(self, hermes_profile: str, os_name: str) -> dict[str, Any]:
        digest = hashlib.sha256(hermes_profile.encode("utf-8")).hexdigest()[:12]
        return {
            "os_id": f"os_{digest}",
            "soul_id": f"soul_{digest}",
            "os_name": os_name,
            "account_id": f"acct_{digest}",
        }

    def login(self, identity: dict[str, Any]) -> dict[str, Any]:
        os_id = identity.get("os_id") or "unknown"
        return {"token_ref": f"linz_session:{os_id}", "expires_at": "2099-01-01T00:00:00Z"}

    def logout(self, token_ref: str) -> dict[str, Any]:
        return {"ok": True}

    def refresh_authorization_map(self, identity: dict[str, Any], token_ref: str) -> dict[str, Any]:
        return {
            "map_version": "local-default",
            "allowed_subjects": ["wsp.chat.message.sent", "wsp.governance.notice"],
            "allowed_event_types": ["message.sent", "governance.notice"],
            "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"],
        }

    def publish_event(self, token_ref: str, subject: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        seed = f"{subject}:{event_type}:{utc_now_iso()}".encode("utf-8")
        return {"world_event_id": f"evt_{hashlib.sha256(seed).hexdigest()[:12]}", "published_at": utc_now_iso()}

    def invoke_compute(self, token_ref: str, task: str, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "result": {"summary": f"queued: {task}"},
            "provider_summary": "local-linz-world/mock",
            "receipt": f"compute_{hashlib.sha256(task.encode('utf-8')).hexdigest()[:12]}",
        }

    def write_memory(self, token_ref: str, artifact_ref: str, sink_reason: str, summary: str) -> dict[str, Any]:
        return {"receipt": f"memory_{hashlib.sha256(artifact_ref.encode('utf-8')).hexdigest()[:12]}"}

    def read_relationships(self, token_ref: str, counterparty_id: str = "") -> dict[str, Any]:
        return {"relationships": []}

    def add_active_relationship(self, token_ref: str, counterparty_id: str, summary: str = "") -> dict[str, Any]:
        digest = hashlib.sha256(counterparty_id.encode("utf-8")).hexdigest()[:12]
        return {"relationship_id": f"rel_{digest}", "counterparty_id": counterparty_id, "state": "ACTIVE", "summary": summary}


class HttpLinzWorldService(LocalLinzWorldService):
    """Small HTTP boundary matching the approved service contract."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(f"{self.base_url}{path}", json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise LinzWorldServiceError("service_unavailable", f"Linz World service unavailable: {exc}") from exc
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            err = data["error"]
            raise LinzWorldServiceError(str(err.get("code") or "service_error"), str(err.get("message") or "Linz World service error"))
        if not isinstance(data, dict):
            raise LinzWorldServiceError("invalid_response", "Linz World service returned an invalid response.")
        return data

    def register_original_spirit(self, hermes_profile: str, os_name: str) -> dict[str, Any]:
        return self._post("/identity/original-spirit", {"hermes_profile": hermes_profile, "os_name": os_name})


def default_service(config=None) -> LinzWorldService:
    from .config import load_linz_world_config

    cfg = load_linz_world_config(config)
    if cfg.service_url:
        return HttpLinzWorldService(cfg.service_url)
    return LocalLinzWorldService()
