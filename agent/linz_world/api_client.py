"""Fake-friendly Linz World service boundary."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import utc_now_iso


class LinzWorldServiceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_RUNTIME_SECRETS: dict[str, str] = {}


def store_runtime_secret(kind: str, value: str) -> str:
    secret = str(value or "").strip()
    if not secret:
        return ""
    digest = hashlib.sha256(f"{kind}:{secret}".encode("utf-8")).hexdigest()[:16]
    ref = f"linz_secret:{kind}:{digest}"
    _RUNTIME_SECRETS[ref] = secret
    return ref


def resolve_secret_ref(ref: str) -> str:
    ref = str(ref or "").strip()
    if not ref:
        return ""
    if ref.startswith("env:"):
        return os.getenv(ref[4:].strip(), "").strip()
    return _RUNTIME_SECRETS.get(ref, "")


def _resolve_bearer_value(ref: str, *, code: str, message: str) -> str:
    value = resolve_secret_ref(ref)
    if value:
        return value
    if str(ref or "").startswith(("linz_secret:", "env:")):
        raise LinzWorldServiceError(code, message)
    return str(ref or "").strip()


def normalize_api_base_url(service_url: str) -> str:
    raw = str(service_url or "").strip().rstrip("/")
    if not raw:
        return ""
    parts = urlsplit(raw)
    path = parts.path.rstrip("/")
    if path.endswith("/api/v1"):
        normalized_path = path
    else:
        normalized_path = f"{path}/api/v1" if path else "/api/v1"
    return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))


class LinzWorldService(Protocol):
    def register_original_spirit(self, hermes_profile: str, os_name: str) -> dict[str, Any]: ...
    def login(self, identity: dict[str, Any]) -> dict[str, Any]: ...
    def logout(self, token_ref: str) -> dict[str, Any]: ...
    def refresh_authorization_map(self, identity: dict[str, Any], token_ref: str) -> dict[str, Any]: ...
    def publish_event(self, token_ref: str, subject: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def invoke_compute(self, token_ref: str, task: str, input_data: dict[str, Any]) -> dict[str, Any]: ...
    def write_memory(self, identity: dict[str, Any], token_ref: str, artifact_ref: str, sink_reason: str, summary: str) -> dict[str, Any]: ...
    def read_relationships(self, identity: dict[str, Any], token_ref: str, counterparty_id: str = "") -> dict[str, Any]: ...
    def add_active_relationship(self, token_ref: str, counterparty_id: str, summary: str = "") -> dict[str, Any]: ...


class LocalLinzWorldService:
    """Deterministic local service used when no remote service URL is configured."""

    def register_original_spirit(self, hermes_profile: str, os_name: str) -> dict[str, Any]:
        digest = hashlib.sha256(hermes_profile.encode("utf-8")).hexdigest()[:12]
        return {
            "agentId": f"agent_{digest}",
            "soulId": f"soul_{digest}",
            "soulHash": f"hash_{digest}",
            "accessToken": f"local_access_{digest}",
            "expiresIn": 86400,
            "registeredAt": utc_now_iso(),
            "os_name": os_name,
        }

    def login(self, identity: dict[str, Any]) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id") or "unknown"
        return {
            "token": f"local_session_{agent_id}",
            "expiresAt": "2099-01-01T00:00:00Z",
            "subjectClaims": ["wsp.chat.message.sent"],
            "credentialId": f"cred_{agent_id}",
        }

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
        digest = hashlib.sha256(task.encode("utf-8")).hexdigest()[:12]
        return {
            "request_id": f"req_{digest}",
            "os_id": "local",
            "provider": "local-linz-world",
            "model": str(input_data.get("model") or "mock"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"queued: {task}"}}],
            "reservation": {},
            "usage": {},
        }

    def write_memory(self, identity: dict[str, Any], token_ref: str, artifact_ref: str, sink_reason: str, summary: str) -> dict[str, Any]:
        return {"receipt": f"memory_{hashlib.sha256(artifact_ref.encode('utf-8')).hexdigest()[:12]}"}

    def read_relationships(self, identity: dict[str, Any], token_ref: str, counterparty_id: str = "") -> dict[str, Any]:
        return {"relationships": []}

    def add_active_relationship(self, token_ref: str, counterparty_id: str, summary: str = "") -> dict[str, Any]:
        digest = hashlib.sha256(counterparty_id.encode("utf-8")).hexdigest()[:12]
        return {"relationship_id": f"rel_{digest}", "counterparty_id": counterparty_id, "state": "ACTIVE", "summary": summary}


class HttpLinzWorldService(LocalLinzWorldService):
    """Small HTTP boundary matching the approved service contract."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = normalize_api_base_url(base_url)
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        require_object_data: bool = True,
    ) -> Any:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                json=payload if method.upper() != "GET" else None,
                headers=headers,
                timeout=self.timeout,
            )
            envelope = response.json()
        except Exception as exc:
            raise LinzWorldServiceError("service_unavailable", f"Linz World service unavailable: {exc}") from exc
        if not isinstance(envelope, dict):
            raise LinzWorldServiceError("invalid_response", "Linz World service returned an invalid response.")
        if response.status_code >= 400:
            raise LinzWorldServiceError(str(envelope.get("code") or response.status_code), str(envelope.get("message") or response.reason_phrase))
        if envelope.get("code") != 0:
            raise LinzWorldServiceError(str(envelope.get("code") or "service_error"), str(envelope.get("message") or "Linz World service error"))
        data = envelope.get("data")
        if require_object_data and not isinstance(data, dict):
            raise LinzWorldServiceError("invalid_response", "Linz World service response missing object data.")
        return data

    def _post(self, path: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        return self._request("POST", path, payload, headers=headers)

    def _get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        require_object_data: bool = True,
    ) -> Any:
        return self._request("GET", path, headers=headers, require_object_data=require_object_data)

    def register_original_spirit(self, hermes_profile: str, os_name: str) -> dict[str, Any]:
        fingerprint = hashlib.sha256(hermes_profile.encode("utf-8")).hexdigest()
        return self._post(
            "/auth/register",
            {
                "publicKey": f"hermes-profile:{hermes_profile}",
                "publicKeyType": "RSA",
                "fingerprint": fingerprint,
                "metadata": {
                    "hermes_profile": hermes_profile,
                    "os_name": os_name,
                    "runtime_type": "hermes-agent",
                },
            },
        )

    def login(self, identity: dict[str, Any]) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id")
        if not agent_id:
            raise LinzWorldServiceError("identity_missing", "Linz World agentId is missing.")
        signed_nonce = hashlib.sha256(f"hermes-login:{agent_id}".encode("utf-8")).hexdigest()
        return self._post("/event/agents/login", {"agentId": agent_id, "signedNonce": signed_nonce})

    def refresh_authorization_map(self, identity: dict[str, Any], token_ref: str) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id")
        token = _resolve_bearer_value(
            token_ref,
            code="login_secret_missing",
            message="Linz World login token secret is unavailable.",
        )
        if not agent_id or not token:
            raise LinzWorldServiceError("login_missing", "Linz World login token is missing.")
        headers = {"Authorization": f"Bearer {token}"}
        refreshed = self._post("/event/agents/refresh", {"token": token}, headers=headers)
        credential = self._post(
            "/event/agents/credentials",
            {"agentId": agent_id, "requestedPurpose": "hermes-runtime"},
            headers=headers,
        )
        subjects = self._get("/event/subjects", headers=headers, require_object_data=False)
        return derive_authorization_summary(refreshed, credential, subjects)

    def publish_event(self, token_ref: str, subject: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise LinzWorldServiceError(
            "unsupported_publish_contract",
            "Linz World HTTP publish is currently a placeholder contract; publish is blocked.",
        )

    def invoke_compute(self, token_ref: str, task: str, input_data: dict[str, Any]) -> dict[str, Any]:
        api_key = _resolve_bearer_value(
            token_ref,
            code="compute_key_missing",
            message="Linz World compute API key secret is unavailable.",
        )
        if not api_key:
            raise LinzWorldServiceError("compute_key_missing", "Linz World compute API key is missing.")
        payload = {
            "model": str(input_data.get("model") or "default"),
            "messages": input_data.get("messages") if isinstance(input_data.get("messages"), list) else [{"role": "user", "content": task}],
            "stream": bool(input_data.get("stream", False)),
            "temperature": float(input_data.get("temperature", 0.2)),
            "metadata": input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {},
        }
        data = self._post("/compute/chat", payload, headers={"Authorization": f"Bearer {api_key}"})
        required = ("request_id", "os_id", "provider", "model", "choices", "reservation", "usage")
        missing = [name for name in required if name not in data]
        if missing:
            raise LinzWorldServiceError("invalid_response", f"Linz World compute response missing: {', '.join(missing)}")
        return data

    def write_memory(self, identity: dict[str, Any], token_ref: str, artifact_ref: str, sink_reason: str, summary: str) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id")
        if not agent_id:
            raise LinzWorldServiceError("identity_missing", "Linz World agentId is missing.")
        token = _resolve_bearer_value(
            token_ref,
            code="login_secret_missing",
            message="Linz World login token secret is unavailable.",
        )
        return self._post(
            "/memory/events",
            {
                "agent_id": agent_id,
                "external_event_id": artifact_ref,
                "event_type": "hermes.memory.sink",
                "event_time": utc_now_iso(),
                "payload": {"summary": summary, "sink_reason": sink_reason},
                "claim": {"sink_reason": sink_reason},
                "evidence_refs": [artifact_ref],
                "importance_score": 0.5,
                "operator_id": "hermes-agent",
            },
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )

    def read_relationships(self, identity: dict[str, Any], token_ref: str, counterparty_id: str = "") -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id")
        token = _resolve_bearer_value(
            token_ref,
            code="login_secret_missing",
            message="Linz World login token secret is unavailable.",
        )
        if not agent_id:
            raise LinzWorldServiceError("identity_missing", "Linz World agentId is missing.")
        data = self._get(
            f"/memory/projections/{agent_id}/relationships",
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )
        relationships = data.get("relationships") or []
        if counterparty_id and isinstance(relationships, list):
            relationships = [
                item for item in relationships
                if isinstance(item, dict) and str(item.get("counterparty_id") or "") == counterparty_id
            ]
        return {"relationships": relationships}

    def add_active_relationship(self, token_ref: str, counterparty_id: str, summary: str = "") -> dict[str, Any]:
        raise LinzWorldServiceError("unsupported_relationship_mutation", "No confirmed Linz World ACTIVE relationship mutation route exists.")


def derive_authorization_summary(
    refreshed: dict[str, Any],
    credential: dict[str, Any],
    subjects: Any,
) -> dict[str, Any]:
    publish_scope = _string_list(credential.get("publishScopeSnapshot"))
    subscribe_scope = _string_list(credential.get("subscribeScopeSnapshot"))
    subject_claims = _string_list(refreshed.get("subjectClaims"))
    if isinstance(subjects, list):
        subject_defs = subjects
    elif isinstance(subjects, dict):
        subject_defs = subjects.get("subjects") or subjects.get("items") or subjects.get("definitions") or []
    else:
        subject_defs = []
    event_types = set()
    if isinstance(subject_defs, list):
        for item in subject_defs:
            if not isinstance(item, dict):
                continue
            event_types.update(_string_list(item.get("eventTypes") or item.get("event_types")))
            for key in ("eventType", "event_type", "type", "name"):
                if item.get(key):
                    event_types.add(str(item[key]))
    return {
        "map_version": str(credential.get("id") or credential.get("permissionProfileId") or refreshed.get("credentialId") or "current"),
        "allowed_subjects": sorted(set(publish_scope + subscribe_scope + subject_claims)),
        "allowed_event_types": sorted(event_types),
        "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"],
        "credential_id": str(credential.get("id") or refreshed.get("credentialId") or ""),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def default_service(config=None) -> LinzWorldService:
    from .config import load_linz_world_config

    cfg = load_linz_world_config(config)
    if cfg.service_url:
        return HttpLinzWorldService(cfg.service_url)
    raise LinzWorldServiceError(
        "missing_service_config",
        "Linz World service_url is not configured. Set linz_world.service_url before using native Linz World runtime.",
    )
