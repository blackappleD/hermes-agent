"""Redaction helpers for Linz World payloads and user-visible summaries."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "session_token",
    "token",
}


def audit_ref_for_payload(payload: Any) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        encoded = repr(payload)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"linz_audit:{digest}"


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value[:20]]
    return value


def payload_summary(payload: Any, *, max_chars: int = 500) -> str:
    redacted = redact_value(payload)
    try:
        text = json.dumps(redacted, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        text = repr(redacted)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text
