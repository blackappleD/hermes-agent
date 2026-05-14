from __future__ import annotations

import pytest

from agent.linz_world.api_client import (
    HttpLinzWorldService,
    LinzWorldServiceError,
    derive_authorization_summary,
    derive_listener_authorization_summary,
    normalize_api_base_url,
    resolve_secret_ref,
    store_runtime_secret,
)
from agent.linz_world.key_material import ensure_key_material


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.reason_phrase = "error"

    def json(self):
        return self._payload


class _TextResponse:
    status_code = 404
    reason_phrase = "Not Found"
    text = "404 Not Found"

    def json(self):
        raise ValueError("Extra data: line 1 column 5 (char 4)")


def test_service_url_normalization_supports_origin_and_api_root():
    assert normalize_api_base_url("http://8.156.84.202:17878") == "http://8.156.84.202:17878/api/v1"
    assert normalize_api_base_url("http://8.156.84.202:17878/api/v1") == "http://8.156.84.202:17878/api/v1"


def test_private_service_url_bypasses_environment_proxy(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
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

    HttpLinzWorldService("http://192.168.1.2:8080").register_original_spirit(
        "profile-1",
        "Hermes",
        "seed",
        public_key="public-key",
        fingerprint="fingerprint",
    )

    assert calls[0][1] == "http://192.168.1.2:8080/api/v1/auth/register"
    assert calls[0][2]["trust_env"] is False


def test_wsl_virtual_gateway_url_bypasses_environment_proxy(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
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

    HttpLinzWorldService("http://198.18.0.2:8080").register_original_spirit(
        "profile-1",
        "Hermes",
        "seed",
        public_key="public-key",
        fingerprint="fingerprint",
    )

    assert calls[0][1] == "http://198.18.0.2:8080/api/v1/auth/register"
    assert calls[0][2]["trust_env"] is False


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

    result = HttpLinzWorldService("http://linz.test").register_original_spirit(
        "profile-1",
        "Hermes",
        "reliable, direct, and careful",
        public_key="-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----\n",
        fingerprint="fingerprint-1",
    )

    assert result["agentId"] == "agent-1"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://linz.test/api/v1/auth/register"
    assert set(calls[0][2]) == {
        "publicKey",
        "publicKeyType",
        "fingerprint",
        "agent_name",
        "persona_seed",
        "type",
        "runtime_type",
        "metadata",
    }
    assert calls[0][2]["publicKey"].startswith("-----BEGIN PUBLIC KEY-----")
    assert calls[0][2]["fingerprint"] == "fingerprint-1"
    assert calls[0][2]["persona_seed"] == "reliable, direct, and careful"
    assert calls[0][2]["metadata"]["persona_seed"] == "reliable, direct, and careful"
    assert "hermes_profile" not in {k for k in calls[0][2] if k != "metadata"}


def test_envelope_nonzero_and_missing_data_are_errors(monkeypatch):
    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 123, "message": "nope", "data": None}),
    )
    with pytest.raises(LinzWorldServiceError, match="nope"):
        HttpLinzWorldService("http://linz.test").register_original_spirit(
            "profile-1",
            "Hermes",
            "seed",
            public_key="public-key",
            fingerprint="fingerprint",
        )

    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 0, "message": "success"}),
    )
    with pytest.raises(LinzWorldServiceError, match="missing object data"):
        HttpLinzWorldService("http://linz.test").register_original_spirit(
            "profile-1",
            "Hermes",
            "seed",
            public_key="public-key",
            fingerprint="fingerprint",
        )


def test_non_json_response_reports_endpoint_and_status(tmp_path, monkeypatch):
    monkeypatch.setattr("httpx.request", lambda *args, **kwargs: _TextResponse())
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    key_material = ensure_key_material("test-profile")

    with pytest.raises(LinzWorldServiceError, match=r"POST /auth/login .*HTTP 404"):
        HttpLinzWorldService("http://linz.test").login({
            "agent_id": "agent-1",
            "private_key_path": key_material.private_key_path,
        })


def test_login_uses_confirmed_auth_login_contract(tmp_path, monkeypatch):
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "token": "event-token",
                    "expires_in": 3600,
                    "memorySummary": {"available": True},
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    key_material = ensure_key_material("test-profile")

    result = HttpLinzWorldService("http://linz.test").login({
        "agent_id": "agent-1",
        "private_key_path": key_material.private_key_path,
    })

    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://linz.test/api/v1/auth/login"
    assert calls[0][2]["osId"] == "agent-1"
    assert "agentId" not in calls[0][2]
    assert isinstance(calls[0][2]["timestamp"], int)
    assert result["token"] == "event-token"


def test_runtime_secret_persists_under_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    token_ref = store_runtime_secret("event_token", "event-token")

    from agent.linz_world import api_client as api_client_mod

    api_client_mod._RUNTIME_SECRETS.clear()
    assert resolve_secret_ref(token_ref) == "event-token"
    assert (tmp_path / "linz_world" / "secrets.json").is_file()


def test_compute_uses_login_token_bearer_and_parses_current_response(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

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
    token_ref = store_runtime_secret("event_token", "login-jwt-token")

    result = HttpLinzWorldService("http://linz.test/api/v1").invoke_compute(
        token_ref,
        "do work",
        {"model": "gpt-4o-mini", "temperature": 0.2},
    )

    assert calls[0][1] == "http://linz.test/api/v1/compute/chat"
    assert calls[0][3]["Authorization"] == "Bearer login-jwt-token"
    assert result["request_id"] == "req_1"
    assert result["provider"] == "openai-main"
    assert result["usage"]["total_tokens"] == 10


def test_compute_401_envelope_is_diagnostic_failure(monkeypatch):
    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 401, "message": "invalid login token", "data": None}, status_code=401),
    )

    with pytest.raises(LinzWorldServiceError, match="invalid login token"):
        HttpLinzWorldService("http://linz.test").invoke_compute("revoked-key", "task", {})


def test_listener_bootstrap_derives_authorization_summary(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "osId": "agent-001",
                    "allowedPublishSubjects": ["sys.heartbeat", "mrk.requirement.published"],
                    "allowedSubscribeSubjects": [
                        "wsp.agent-001",
                        "sys.broadcast",
                        "mrk.requirement.published.broadcast",
                    ],
                    "allowedPublishEventTypes": ["sys.heartbeat.report", "mrk.requirement.published"],
                    "allowedSubscribeEventTypes": [
                        "wsp.sys.login.response",
                        "wsp.sys.subject.changed",
                        "sys.broadcast.notice_published",
                        "mrk.requirement.published.broadcast",
                    ],
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)
    token_ref = store_runtime_secret("event_token", "event-token")

    result = HttpLinzWorldService("http://linz.test").refresh_authorization_map({"agent_id": "agent-1"}, token_ref)

    assert calls[0][1] == "http://linz.test/api/v1/event/agents/listener/bootstrap"
    assert calls[0][3]["Authorization"] == "Bearer event-token"
    assert result["map_version"] == "agent-001"
    assert result["allowed_publish_subjects"] == ["mrk.requirement.published", "sys.heartbeat"]
    assert result["allowed_publish_event_types"] == ["mrk.requirement.published", "sys.heartbeat.report"]
    assert result["allowed_subscribe_subjects"] == [
        "mrk.requirement.published.broadcast",
        "sys.broadcast",
        "wsp.agent-001",
    ]
    assert result["allowed_subscribe_event_types"] == [
        "mrk.requirement.published.broadcast",
        "sys.broadcast.notice_published",
        "wsp.sys.login.response",
        "wsp.sys.subject.changed",
    ]


def test_derive_authorization_summary_accepts_subjects_array():
    result = derive_authorization_summary(
        {"subjectClaims": ["wsp.*"], "credentialId": "cred_1"},
        {"id": "cred_1", "publishScopeSnapshot": ["wsp.*"]},
        [{"subject": "wsp.*", "eventTypes": ["wsp.chat.message.sent"]}],
    )

    assert result["map_version"] == "cred_1"
    assert result["allowed_publish_subjects"] == ["wsp.*"]
    assert result["allowed_publish_event_types"] == ["wsp.chat.message.sent"]
    assert result["allowed_subscribe_subjects"] == []
    assert result["allowed_subscribe_event_types"] == []


def test_memory_events_request_includes_required_agent_id_and_fields(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

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


def test_relationship_projection_response_preserves_memory_projection(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

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


def test_relationship_add_posts_confirmed_memory_relationship_route(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "relationship_id": "rel_1",
                    "target_os_id": "agent-2",
                    "relation_type": "FRIEND",
                    "status": "ACTIVE",
                    "summary": "trusted",
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)
    token_ref = store_runtime_secret("event_token", "event-token")

    result = HttpLinzWorldService("http://linz.test").add_active_relationship(
        {"agent_id": "agent-1"},
        token_ref,
        "agent-2",
        "trusted",
        "FRIEND",
    )

    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://linz.test/api/v1/memory/relationships/agent-1"
    assert calls[0][3]["Authorization"] == "Bearer event-token"
    assert calls[0][2] == {
        "target_os_id": "agent-2",
        "relation_type": "FRIEND",
        "status": "ACTIVE",
        "summary": "trusted",
        "operator_id": "agent-1",
    }
    assert result["relationship_id"] == "rel_1"
