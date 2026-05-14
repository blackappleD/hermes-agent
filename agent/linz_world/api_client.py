"""Fake-friendly Linz World service boundary."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import time
from json import JSONDecodeError
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from hermes_constants import get_hermes_home

from .config import load_linz_world_config
from .models import utc_now_iso
from .nats_transport import NatsPublishError, publish_linz_event


class LinzWorldServiceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_RUNTIME_SECRETS: dict[str, str] = {}
_SECRETS_FILE = "secrets.json"


def _persistent_secrets_path():
    return get_hermes_home() / "linz_world" / _SECRETS_FILE


def _load_persistent_secrets() -> dict[str, Any]:
    path = _persistent_secrets_path()
    if not path.exists():
        return {"secrets": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, JSONDecodeError, ValueError):
        return {"secrets": {}}
    if not isinstance(data, dict):
        return {"secrets": {}}
    secrets = data.get("secrets")
    if not isinstance(secrets, dict):
        data["secrets"] = {}
    return data


def _save_persistent_secrets(data: dict[str, Any]) -> None:
    path = _persistent_secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def store_runtime_secret(kind: str, value: str) -> str:
    secret = str(value or "").strip()
    if not secret:
        return ""
    digest = hashlib.sha256(f"{kind}:{secret}".encode("utf-8")).hexdigest()[:16]
    ref = f"linz_secret:{kind}:{digest}"
    _RUNTIME_SECRETS[ref] = secret
    data = _load_persistent_secrets()
    data.setdefault("secrets", {})[ref] = {
        "kind": kind,
        "value": secret,
        "updated_at": utc_now_iso(),
    }
    _save_persistent_secrets(data)
    return ref


def resolve_secret_ref(ref: str) -> str:
    ref = str(ref or "").strip()
    if not ref:
        return ""
    if ref.startswith("env:"):
        return os.getenv(ref[4:].strip(), "").strip()
    if ref in _RUNTIME_SECRETS:
        return _RUNTIME_SECRETS[ref]
    if ref.startswith("linz_secret:"):
        entry = _load_persistent_secrets().get("secrets", {}).get(ref)
        if isinstance(entry, dict):
            value = str(entry.get("value") or "")
        else:
            value = str(entry or "")
        if value:
            _RUNTIME_SECRETS[ref] = value
            return value
    return ""


def delete_runtime_secret(ref: str) -> None:
    ref = str(ref or "").strip()
    if not ref:
        return
    _RUNTIME_SECRETS.pop(ref, None)
    if not ref.startswith("linz_secret:"):
        return
    data = _load_persistent_secrets()
    secrets = data.get("secrets")
    if isinstance(secrets, dict) and ref in secrets:
        secrets.pop(ref, None)
        _save_persistent_secrets(data)


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


def _should_bypass_env_proxy(service_url: str) -> bool:
    host = (urlsplit(str(service_url or "")).hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address in ipaddress.ip_network("198.18.0.0/15")
    )


class LinzWorldService(Protocol):
    def register_original_spirit(
        self,
        hermes_profile: str,
        os_name: str,
        persona_seed: str = "",
        os_type: str = "USER",
        runtime_type: str = "Hermes",
        public_key: str = "",
        public_key_type: str = "RSA",
        fingerprint: str = "",
    ) -> dict[str, Any]: ...
    def login(self, identity: dict[str, Any]) -> dict[str, Any]: ...
    def logout(self, token_ref: str) -> dict[str, Any]: ...
    def refresh_authorization_map(self, identity: dict[str, Any], token_ref: str) -> dict[str, Any]: ...
    def publish_event(self, token_ref: str, subject: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def invoke_compute(self, token_ref: str, task: str, input_data: dict[str, Any]) -> dict[str, Any]: ...
    def write_memory(self, identity: dict[str, Any], token_ref: str, artifact_ref: str, sink_reason: str, summary: str) -> dict[str, Any]: ...
    def read_relationships(self, identity: dict[str, Any], token_ref: str, counterparty_id: str = "") -> dict[str, Any]: ...
    def add_active_relationship(
        self,
        identity: dict[str, Any],
        token_ref: str,
        counterparty_id: str,
        summary: str = "",
        relation_type: str = "OTHER",
    ) -> dict[str, Any]: ...


class LocalLinzWorldService:
    """Deterministic local service used when no remote service URL is configured."""

    def register_original_spirit(
        self,
        hermes_profile: str,
        os_name: str,
        persona_seed: str = "",
        os_type: str = "USER",
        runtime_type: str = "Hermes",
        public_key: str = "",
        public_key_type: str = "RSA",
        fingerprint: str = "",
    ) -> dict[str, Any]:
        digest = hashlib.sha256(hermes_profile.encode("utf-8")).hexdigest()[:12]
        return {
            "agentId": f"agent_{digest}",
            "soulId": f"soul_{digest}",
            "soulHash": f"hash_{digest}",
            "accessToken": f"local_access_{digest}",
            "expiresIn": 86400,
            "registeredAt": utc_now_iso(),
            "os_name": os_name,
            "type": os_type,
            "runtime_type": runtime_type,
        }

    def login(self, identity: dict[str, Any]) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id") or "unknown"
        return {
            "token": f"local_session_{agent_id}",
            "expiresAt": "2099-01-01T00:00:00Z",
            "subjectClaims": ["wsp.*"],
            "credentialId": f"cred_{agent_id}",
        }

    def logout(self, token_ref: str) -> dict[str, Any]:
        return {"ok": True}

    def refresh_authorization_map(self, identity: dict[str, Any], token_ref: str) -> dict[str, Any]:
        return {
            "map_version": "local-default",
            "allowed_publish_subjects": ["wsp.*", "wsp.governance.notice"],
            "allowed_publish_event_types": ["wsp.chat.message.sent", "wsp.chat.message.read", "governance.notice"],
            "allowed_subscribe_subjects": ["wsp.*", "wsp.governance.notice"],
            "allowed_subscribe_event_types": ["wsp.chat.message.sent", "wsp.chat.message.read", "governance.notice"],
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

    def add_active_relationship(
        self,
        identity: dict[str, Any],
        token_ref: str,
        counterparty_id: str,
        summary: str = "",
        relation_type: str = "OTHER",
    ) -> dict[str, Any]:
        digest = hashlib.sha256(counterparty_id.encode("utf-8")).hexdigest()[:12]
        return {
            "relationship_id": f"rel_{digest}",
            "counterparty_id": counterparty_id,
            "relation_type": relation_type or "OTHER",
            "state": "ACTIVE",
            "summary": summary,
        }


class HttpLinzWorldService(LocalLinzWorldService):
    """Small HTTP boundary matching the approved service contract."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = normalize_api_base_url(base_url)
        self.timeout = timeout
        self.trust_env = not _should_bypass_env_proxy(self.base_url)

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
            request_kwargs = {
                "json": payload if method.upper() != "GET" else None,
                "headers": headers,
                "timeout": self.timeout,
            }
            if not self.trust_env:
                request_kwargs["trust_env"] = False
            response = httpx.request(method, f"{self.base_url}{path}", **request_kwargs)
        except httpx.RequestError as exc:
            raise LinzWorldServiceError("service_unavailable", f"Linz World service unavailable: {exc}") from exc
        try:
            envelope = response.json()
        except (JSONDecodeError, ValueError) as exc:
            body = _response_text_preview(response)
            raise LinzWorldServiceError(
                "invalid_response",
                (
                    f"Linz World service returned non-JSON response for "
                    f"{method.upper()} {path} (HTTP {response.status_code}): {body}"
                ),
            ) from exc
        if not isinstance(envelope, dict):
            raise LinzWorldServiceError("invalid_response", "Linz World service returned an invalid response.")
        if response.status_code >= 400:
            raise LinzWorldServiceError(
                str(envelope.get("code") or response.status_code),
                str(envelope.get("message") or response.reason_phrase),
            )
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

    def register_original_spirit(
        self,
        hermes_profile: str,
        os_name: str,
        persona_seed: str = "",
        os_type: str = "USER",
        runtime_type: str = "Hermes",
        public_key: str = "",
        public_key_type: str = "RSA",
        fingerprint: str = "",
    ) -> dict[str, Any]:
        public_key = str(public_key or "")
        fingerprint = str(fingerprint or "").strip()
        if not public_key.strip() or not fingerprint:
            raise LinzWorldServiceError(
                "key_material_missing",
                "Linz World registration requires profile-local public key material.",
            )
        seed = str(persona_seed or "").strip()
        return self._post(
            "/auth/register",
            {
                "publicKey": public_key,
                "publicKeyType": public_key_type or "RSA",
                "fingerprint": fingerprint,
                "agent_name": os_name,
                "persona_seed": seed,
                "type": os_type,
                "runtime_type": runtime_type,
                "metadata": {
                    "hermes_profile": hermes_profile,
                    "os_name": os_name,
                    "runtime_type": runtime_type,
                    "persona_seed": seed,
                    "type": os_type,
                },
            },
        )

    def login(self, identity: dict[str, Any]) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id")
        if not agent_id:
            raise LinzWorldServiceError("identity_missing", "Linz World agentId is missing.")
        private_key_path = str(identity.get("private_key_path") or "").strip()
        if not private_key_path:
            raise LinzWorldServiceError(
                "key_material_missing",
                "Linz World login signing key is missing; re-run identity registration.",
            )
        timestamp = _epoch_millis()
        from .key_material import sign_with_private_key

        signed_nonce = sign_with_private_key(private_key_path, f"{agent_id}.{timestamp}")
        return self._post(
            "/auth/login",
            {"osId": agent_id, "signedNonce": signed_nonce, "timestamp": timestamp},
        )

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
        view = self._post("/event/agents/listener/bootstrap", {}, headers=headers)
        return derive_listener_authorization_summary(agent_id, view)

    def publish_event(self, token_ref: str, subject: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = load_linz_world_config()
        try:
            return publish_linz_event(
                nats_url=cfg.nats_url,
                subject=subject,
                event_type=event_type,
                payload=payload,
            )
        except NatsPublishError as exc:
            raise LinzWorldServiceError(exc.code, exc.message) from exc

    def invoke_compute(self, token_ref: str, task: str, input_data: dict[str, Any]) -> dict[str, Any]:
        token = _resolve_bearer_value(
            token_ref,
            code="login_secret_missing",
            message="Linz World login token secret is unavailable.",
        )
        if not token:
            raise LinzWorldServiceError("login_missing", "Linz World login token is missing.")
        payload = {
            "model": str(input_data.get("model") or "default"),
            "messages": input_data.get("messages") if isinstance(input_data.get("messages"), list) else [{"role": "user", "content": task}],
            "stream": bool(input_data.get("stream", False)),
            "temperature": float(input_data.get("temperature", 0.2)),
            "metadata": input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {},
        }
        data = self._post("/compute/chat", payload, headers={"Authorization": f"Bearer {token}"})
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
        return _relationship_projection_summary(data, counterparty_id)

    def add_active_relationship(
        self,
        identity: dict[str, Any],
        token_ref: str,
        counterparty_id: str,
        summary: str = "",
        relation_type: str = "OTHER",
    ) -> dict[str, Any]:
        agent_id = identity.get("agent_id") or identity.get("agentId") or identity.get("os_id")
        token = _resolve_bearer_value(
            token_ref,
            code="login_secret_missing",
            message="Linz World login token secret is unavailable.",
        )
        if not agent_id:
            raise LinzWorldServiceError("identity_missing", "Linz World agentId is missing.")
        return self._post(
            f"/memory/relationships/{agent_id}",
            {
                "target_os_id": counterparty_id,
                "relation_type": relation_type or "OTHER",
                "status": "ACTIVE",
                "summary": summary or "手动添加关系",
                "operator_id": agent_id,
            },
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )


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
        "allowed_publish_subjects": sorted(set(publish_scope + subject_claims)),
        "allowed_publish_event_types": sorted(event_types),
        "allowed_subscribe_subjects": sorted(set(subscribe_scope)),
        "allowed_subscribe_event_types": [],
        "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"],
        "credential_id": str(credential.get("id") or refreshed.get("credentialId") or ""),
    }


def derive_listener_authorization_summary(agent_id: str, view: dict[str, Any]) -> dict[str, Any]:
    publish_subjects = _string_list(view.get("allowedPublishSubjects"))
    publish_event_types = _string_list(view.get("allowedPublishEventTypes"))
    subscribe_subjects = _string_list(view.get("allowedSubscribeSubjects"))
    subscribe_event_types = _string_list(view.get("allowedSubscribeEventTypes"))
    return {
        "map_version": str(view.get("viewVersion") or view.get("view_version") or view.get("osId") or view.get("os_id") or "listener-bootstrap"),
        "allowed_publish_subjects": sorted(set(publish_subjects)),
        "allowed_publish_event_types": sorted(set(publish_event_types)),
        "allowed_subscribe_subjects": sorted(set(subscribe_subjects)),
        "allowed_subscribe_event_types": sorted(set(subscribe_event_types)),
        "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"],
    }


def _relationship_projection_summary(data: Any, counterparty_id: str = "") -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LinzWorldServiceError("invalid_response", "Linz World relationship projection response missing object data.")
    content = data.get("content") if isinstance(data.get("content"), (dict, list)) else {}
    if isinstance(content, dict):
        raw_relationships = content.get("relationships") or content.get("items") or data.get("relationships") or []
    elif isinstance(content, list):
        raw_relationships = content
    else:
        raw_relationships = data.get("relationships") or []
    relationships = raw_relationships if isinstance(raw_relationships, list) else []
    if counterparty_id:
        relationships = [
            item for item in relationships
            if isinstance(item, dict) and str(item.get("counterparty_id") or "") == counterparty_id
        ]
    projection = {
        key: data.get(key)
        for key in (
            "projection_id",
            "agent_id",
            "projection_type",
            "source_version",
            "content",
            "generated_at",
            "generated_by",
        )
        if key in data
    }
    return {"relationships": relationships, "projection": projection}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _response_text_preview(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:
        return "<unreadable response body>"
    text = " ".join(text.split())
    if not text:
        return "<empty response body>"
    return text[:200]


def _epoch_millis() -> int:
    return int(time.time() * 1000)


def default_service(config=None) -> LinzWorldService:
    from .config import load_linz_world_config

    cfg = load_linz_world_config(config)
    if cfg.service_url:
        return HttpLinzWorldService(cfg.service_url)
    raise LinzWorldServiceError(
        "missing_service_config",
        "Linz World service_url is not configured. Set linz_world.service_url before using native Linz World runtime.",
    )
