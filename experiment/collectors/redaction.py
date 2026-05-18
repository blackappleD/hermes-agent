from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from agent.linz_world.redaction import audit_ref_for_payload, redact_value
except Exception:  # pragma: no cover - defensive fallback for package extraction.
    audit_ref_for_payload = None
    redact_value = None

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "session_token",
    "token",
}

RESTRICTED_MARKERS = {"restricted", "private", "secret"}


def stable_hash(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def audit_ref(value: Any) -> str:
    if audit_ref_for_payload is not None:
        return audit_ref_for_payload(value)
    return f"experiment_audit:{stable_hash(value)}"


def redact(value: Any) -> Any:
    if redact_value is not None:
        value = redact_value(value)
    return _redact_fallback(value)


def _redact_fallback(value: Any) -> Any:
    if isinstance(value, dict):
        lowered = {str(key).lower(): item for key, item in value.items()}
        classification = str(lowered.get("classification", lowered.get("visibility", ""))).lower()
        if lowered.get("restricted_raw_payload") is True or classification in RESTRICTED_MARKERS:
            return {"redacted": True, "audit_ref": audit_ref(value), "sha256": stable_hash(value)}
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                out[key] = "[REDACTED]"
            else:
                out[key] = _redact_fallback(item)
        return out
    if isinstance(value, list):
        return [_redact_fallback(item) for item in value[:50]]
    if isinstance(value, bytes):
        return {"content_ref": f"bytes:{hashlib.sha256(value).hexdigest()[:16]}", "length": len(value)}
    return value


def redact_event(event: dict[str, Any]) -> dict[str, Any]:
    redacted = {
        "subject": event.get("subject"),
        "event_type": event.get("event_type"),
        "event_id": event.get("event_id"),
        "payload": redact(event.get("payload", {})),
        "raw_input_ref": audit_ref(event),
    }
    if "tags" in event:
        redacted["tags"] = list(event.get("tags") or [])
    return redacted
