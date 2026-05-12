from __future__ import annotations

import pytest

from agent.linz_world.api_client import (
    HttpLinzWorldService,
    LinzWorldServiceError,
    normalize_api_base_url,
    store_runtime_secret,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.reason_phrase = "error"

    def json(self):
        return self._payload


def test_service_url_normalization_supports_origin_and_api_root():
    assert normalize_api_base_url("http://8.156.84.202:17878") == "http://8.156.84.202:17878/api/v1"
    assert normalize_api_base_url("http://8.156.84.202:17878/api/v1") == "http://8.156.84.202:17878/api/v1"


def test_register_uses_linz_world_auth_register_contract(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "agentId": "agent-1",
                    "soulId": "soul-1",
                    "soulHash": "hash-1",
                    "accessToken": "token-secret",
                    "expiresIn": 86400,
                    "registeredAt": "2026-05-12T00:00:00Z",
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)

    result = HttpLinzWorldService("http://linz.test").register_original_spirit("profile-1", "Hermes")

    assert result["agentId"] == "agent-1"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://linz.test/api/v1/auth/register"
    assert set(calls[0][2]) == {"publicKey", "publicKeyType", "fingerprint", "metadata"}
    assert "hermes_profile" not in {k for k in calls[0][2] if k != "metadata"}


def test_envelope_nonzero_and_missing_data_are_errors(monkeypatch):
    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 123, "message": "nope", "data": None}),
    )
    with pytest.raises(LinzWorldServiceError, match="nope"):
        HttpLinzWorldService("http://linz.test").register_original_spirit("profile-1", "Hermes")

    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 0, "message": "success"}),
    )
    with pytest.raises(LinzWorldServiceError, match="missing object data"):
        HttpLinzWorldService("http://linz.test").register_original_spirit("profile-1", "Hermes")


def test_compute_uses_api_key_bearer_and_parses_current_response(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "request_id": "req_1",
                    "os_id": "os-default",
                    "provider": "openai-main",
                    "model": "gpt-4o-mini",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
                    "reservation": {"reservation_id": "res_1", "status": "settled"},
                    "usage": {"total_tokens": 10, "settlement_status": "settled"},
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)
    key_ref = store_runtime_secret("compute_api_key", "test-compute-key")

    result = HttpLinzWorldService("http://linz.test/api/v1").invoke_compute(
        key_ref,
        "do work",
        {"model": "gpt-4o-mini", "temperature": 0.2},
    )

    assert calls[0][1] == "http://linz.test/api/v1/compute/chat"
    assert calls[0][3]["Authorization"] == "Bearer test-compute-key"
    assert result["request_id"] == "req_1"
    assert result["provider"] == "openai-main"
    assert result["usage"]["total_tokens"] == 10


def test_compute_401_envelope_is_diagnostic_failure(monkeypatch):
    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 401, "message": "invalid compute key", "data": None}, status_code=401),
    )

    with pytest.raises(LinzWorldServiceError, match="invalid compute key"):
        HttpLinzWorldService("http://linz.test").invoke_compute("revoked-key", "task", {})
