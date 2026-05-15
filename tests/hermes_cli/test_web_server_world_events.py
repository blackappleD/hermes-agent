from __future__ import annotations

import pytest

from gateway.config import Platform
from gateway.event_projection_store import EventProjectionStore
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


@pytest.fixture
def client(monkeypatch, _isolate_hermes_home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import hermes_cli.web_server as web_server

    monkeypatch.setattr(
        web_server,
        "read_runtime_status",
        lambda: {
            "gateway_state": "running",
            "updated_at": "2026-05-15T00:00:00+00:00",
            "platforms": {"linz_world": {"state": "connected"}},
        },
    )
    test_client = TestClient(web_server.app)
    test_client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    return test_client


def _record_event(index: int, *, source_category: str = "telegram", status: str = "received") -> str:
    platform = Platform.TELEGRAM if source_category == "telegram" else Platform.WEBHOOK
    raw = {"message_id": f"msg-{index}", "payload": {"text": f"hello {index}"}}
    if source_category == "linz_world_nats":
        raw.update(
            {
                "event_id": f"evt-{index}",
                "subject": "wsp.chat.message.sent",
                "event_type": "message.sent",
                "nats_sequence": str(index),
                "sequence_key": f"stream:consumer:{index}",
            }
        )
    event = MessageEvent(
        text=f"hello {index}",
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=platform,
            chat_id="chat",
            chat_name="Chat",
            user_id="user",
            user_name="User",
            message_id=f"msg-{index}",
        ),
        raw_message=raw,
        message_id=f"msg-{index}",
    )
    store = EventProjectionStore()
    try:
        return store.record_message_event_projected(event, consume_status=status, session_id=f"session-{index}")
    finally:
        store.close()


def test_list_gateway_message_events_returns_latest_summary_default_limit(client):
    for index in range(105):
        _record_event(index)

    resp = client.get("/api/gateway/message-events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "gateway_message_events"
    assert len(data["records"]) == 100
    assert data["limits"] == {"requested_limit": 100, "returned": 100}
    assert data["source_status"]["gateway_state"] == "running"
    assert data["records"][0]["message_event_id"] == "msg-104"


def test_gateway_message_event_detail_includes_raw_payload_projection_and_transitions(client):
    record_id = _record_event(1, source_category="linz_world_nats", status="processing")
    store = EventProjectionStore()
    try:
        store.mark_handled(record_id)
    finally:
        store.close()

    detail_resp = client.get(f"/api/gateway/message-events/{record_id}")
    missing_resp = client.get("/api/gateway/message-events/missing")

    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["mode"] == "gateway_message_event_detail"
    assert detail["record"]["source_category"] == "linz_world_nats"
    assert detail["record"]["raw_payload"]["event_id"] == "evt-1"
    assert detail["projection"]["message_event_id"] == "msg-1"
    assert [t["to_status"] for t in detail["transitions"]][-1] == "handled"
    assert missing_resp.status_code == 404


def test_message_events_query_validation_and_filters(client):
    _record_event(1, source_category="linz_world_nats", status="handled")
    _record_event(2, status="failed")

    invalid_limit = client.get("/api/gateway/message-events?limit=501")
    invalid_status = client.get("/api/gateway/message-events?consume_status=nope")
    filtered = client.get("/api/gateway/message-events?source_category=linz_world_nats&consume_status=handled&limit=1")

    assert invalid_limit.status_code == 400
    assert invalid_status.status_code == 400
    assert filtered.status_code == 200
    data = filtered.json()
    assert len(data["records"]) == 1
    assert data["records"][0]["source_category"] == "linz_world_nats"
    assert data["next_cursor"] is None


def test_message_events_handles_empty_unknown_status_and_unserializable_payload(client, monkeypatch):
    import hermes_cli.web_server as web_server

    monkeypatch.setattr(web_server, "read_runtime_status", lambda: {})
    empty = client.get("/api/gateway/message-events")
    assert empty.status_code == 200
    assert empty.json()["source_status"]["gateway_state"] == "unknown"

    event = MessageEvent(
        text="bad payload",
        source=SessionSource(platform=Platform.WEBHOOK, chat_id="chat", user_id="user"),
        raw_message={"message_id": "bad-1"},
        message_id="bad-1",
    )
    store = EventProjectionStore()
    try:
        record_id = store.record_message_event_projected(event, raw_payload={"bad": object()})
    finally:
        store.close()

    detail = client.get(f"/api/gateway/message-events/{record_id}")
    assert detail.status_code == 200
    assert detail.json()["record"]["raw_payload_available"] is False
