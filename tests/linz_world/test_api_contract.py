from __future__ import annotations

import pytest

from agent.linz_world.api_client import (
    HttpLinzWorldService,
    LinzWorldServiceError,
    derive_authorization_summary,
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


def test_subjects_array_envelope_derives_authorization_summary(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        if url.endswith("/event/agents/refresh"):
            return _Response(
                {
                    "code": 0,
                    "message": "success",
                    "data": {
                        "token": "event-token",
                        "expiresAt": "2099-01-01T00:00:00Z",
                        "subjectClaims": ["wsp.chat.message.sent"],
                        "credentialId": "cred_1",
                    },
                }
            )
        if url.endswith("/event/agents/credentials"):
            return _Response(
                {
                    "code": 0,
                    "message": "success",
                    "data": {
                        "id": "cred_1",
                        "agentId": "agent-1",
                        "publishScopeSnapshot": ["wsp.chat.message.sent"],
                        "subscribeScopeSnapshot": ["wsp.agent-1.sys"],
                    },
                }
            )
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": [
                    {"subject": "wsp.chat.message.sent", "eventTypes": ["message.sent"]},
                    {"subject": "wsp.agent-1.sys", "event_type": "subject_change"},
                ],
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)
    token_ref = store_runtime_secret("event_token", "event-token")

    result = HttpLinzWorldService("http://linz.test").refresh_authorization_map({"agent_id": "agent-1"}, token_ref)

    assert any(call[1] == "http://linz.test/api/v1/event/subjects" for call in calls)
    assert result["allowed_subjects"] == ["wsp.agent-1.sys", "wsp.chat.message.sent"]
    assert "message.sent" in result["allowed_event_types"]
    assert "subject_change" in result["allowed_event_types"]


def test_derive_authorization_summary_accepts_subjects_array():
    result = derive_authorization_summary(
        {"subjectClaims": ["wsp.chat.message.sent"], "credentialId": "cred_1"},
        {"id": "cred_1", "publishScopeSnapshot": ["wsp.chat.message.sent"]},
        [{"subject": "wsp.chat.message.sent", "eventTypes": ["message.sent"]}],
    )

    assert result["map_version"] == "cred_1"
    assert result["allowed_subjects"] == ["wsp.chat.message.sent"]
    assert result["allowed_event_types"] == ["message.sent"]


def test_memory_events_request_includes_required_agent_id_and_fields(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response({"code": 0, "message": "success", "data": {"receipt": "memory_1"}})

    monkeypatch.setattr("httpx.request", fake_request)
    token_ref = store_runtime_secret("event_token", "event-token")

    result = HttpLinzWorldService("http://linz.test").write_memory(
        {"agent_id": "agent-1"},
        token_ref,
        "artifact-1",
        "delivery evidence",
        "summary",
    )

    assert result["receipt"] == "memory_1"
    assert calls[0][1] == "http://linz.test/api/v1/memory/events"
    assert calls[0][3]["Authorization"] == "Bearer event-token"
    assert set(calls[0][2]) == {
        "agent_id",
        "external_event_id",
        "event_type",
        "event_time",
        "payload",
        "claim",
        "evidence_refs",
        "importance_score",
        "operator_id",
    }
    assert calls[0][2]["agent_id"] == "agent-1"


def test_relationship_projection_response_preserves_memory_projection(monkeypatch):
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "projection_id": "proj_1",
                    "agent_id": "agent-1",
                    "projection_type": "relationships",
                    "source_version": 7,
                    "content": {
                        "summary": "trusted collaborators",
                        "relationships": [
                            {
                                "relationship_id": "rel_1",
                                "counterparty_id": "actor_1",
                                "state": "ACTIVE",
                                "summary": "trusted collaborator",
                            }
                        ],
                    },
                    "generated_at": "2026-05-12T00:00:00Z",
                    "generated_by": "linz-world",
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)
    token_ref = store_runtime_secret("event_token", "event-token")

    result = HttpLinzWorldService("http://linz.test").read_relationships(
        {"agent_id": "agent-1"},
        token_ref,
    )

    assert calls[0][1] == "http://linz.test/api/v1/memory/projections/agent-1/relationships"
    assert result["relationships"][0]["relationship_id"] == "rel_1"
    assert result["projection"]["projection_id"] == "proj_1"
    assert result["projection"]["projection_type"] == "relationships"
    assert result["projection"]["content"]["summary"] == "trusted collaborators"
