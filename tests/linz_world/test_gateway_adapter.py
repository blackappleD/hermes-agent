import threading
import time

import pytest

from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.config import OSRuntimeConfig
from agent.linz_world.config import LinzWorldConfig
from agent.linz_world.event_bus import project_to_message_event
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.gateway_adapter import LinzWorldPlatformAdapter, dispatch_world_event, persist_world_event_for_gateway
from agent.linz_world.models import AuthState, AuthorizationMap, PublishReceipt, ReceiptStatus
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.event_projection_store import EventProjectionStore
from gateway.platform_registry import platform_registry
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def test_linz_world_platform_is_registered():
    assert platform_registry.is_registered("linz_world")


def test_linz_world_gateway_events_bypass_human_allowlist(monkeypatch):
    monkeypatch.delenv("GATEWAY_ALLOW_ALL_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOWED_USERS", raising=False)

    runner = GatewayRunner(GatewayConfig())
    source = SessionSource(
        platform=Platform("linz_world"),
        chat_id="wsp.target-os",
        chat_type="channel",
        user_id="source-os-id",
        user_name="Source OS",
    )

    assert runner._is_user_authorized(source) is True


@pytest.mark.asyncio
async def test_linz_world_gateway_send_is_suppressed_noop():
    adapter = LinzWorldPlatformAdapter(PlatformConfig(enabled=True))

    result = await adapter.send("wsp.target", "hello")

    assert result.success is True
    assert result.raw_response["suppressed"] is True
    assert result.raw_response["reason"] == "linz_world_gateway_receive_only"


@pytest.mark.asyncio
async def test_linz_world_gateway_send_can_publish_when_auto_respond_enabled(monkeypatch):
    adapter = LinzWorldPlatformAdapter(PlatformConfig(enabled=True))
    sent = {}

    monkeypatch.setattr(
        "agent.linz_world.gateway_adapter.load_linz_world_config",
        lambda: LinzWorldConfig(auto_respond=True),
    )

    def fake_send_chat_message(
        to_os_id,
        content,
        *,
        to_os_name="",
        conversation_id="",
        repository=None,
        service=None,
    ):
        sent.update(
            {
                "to_os_id": to_os_id,
                "content": content,
                "to_os_name": to_os_name,
                "conversation_id": conversation_id,
                "repository": repository,
            }
        )
        return PublishReceipt(
            request_id="req_1",
            subject=f"wsp.{to_os_id}",
            event_type="wsp.chat.message.sent",
            payload_summary="hello",
            status=ReceiptStatus.PUBLISHED,
            world_event_id="evt_reply",
        )

    monkeypatch.setattr("agent.linz_world.chat.send_chat_message", fake_send_chat_message)

    result = await adapter.send(
        "wsp.self",
        "hello",
        metadata={
            "linz_world_user_id": "remote-os",
            "linz_world_user_name": "Remote",
            "linz_world_chat_id": "wsp.self",
        },
    )

    assert result.success is True
    assert result.message_id == "evt_reply"
    assert sent["to_os_id"] == "remote-os"
    assert sent["to_os_name"] == "Remote"
    assert sent["conversation_id"] == "wsp.self"
    assert sent["repository"] is adapter._repository


@pytest.mark.asyncio
async def test_linz_world_adapter_connect_starts_nats_listener(monkeypatch, linz_home):
    started = {}
    monkeypatch.setattr("agent.linz_world.gateway_adapter.os.getpid", lambda: 12345)
    monkeypatch.setattr("agent.linz_world.gateway_adapter.utc_now_iso", lambda: "2026-05-17T00:00:00Z")

    class _FakeListener:
        def __init__(self, *, nats_url, subjects, on_event):
            started["nats_url"] = nats_url
            started["subjects"] = subjects
            self.on_event = on_event

        def start(self):
            started["started"] = True

        def stop(self):
            started["stopped"] = True

    monkeypatch.setattr(
        "agent.linz_world.gateway_adapter.auth.refresh_authorization_map",
        lambda repo: AuthorizationMap(
            state=AuthState.CURRENT,
            allowed_subscribe_subjects=["wsp.agent_b"],
            allowed_subscribe_event_types=["wsp.chat.message.sent"],
        ),
    )
    monkeypatch.setattr(
        "agent.linz_world.gateway_adapter.load_linz_world_config",
        lambda: LinzWorldConfig(nats_url="nats://127.0.0.1:4222"),
    )
    monkeypatch.setattr("agent.linz_world.gateway_adapter.NatsEventListener", _FakeListener)

    adapter = LinzWorldPlatformAdapter(PlatformConfig(enabled=True))
    assert await adapter.connect() is True
    login = adapter._repository.get_login()
    assert login.online is True
    assert login.listener_pid == 12345
    assert login.listener_started_at == "2026-05-17T00:00:00Z"
    assert login.listener_last_error == ""
    await adapter.disconnect()
    login = adapter._repository.get_login()
    assert login.online is False
    assert login.listener_pid == 0
    assert login.listener_started_at == ""

    assert started == {
        "nats_url": "nats://127.0.0.1:4222",
        "subjects": ["wsp.agent_b"],
        "started": True,
        "stopped": True,
    }


@pytest.mark.asyncio
async def test_linz_world_adapter_connect_without_subscribe_subjects_fails(monkeypatch, linz_home):
    monkeypatch.setattr(
        "agent.linz_world.gateway_adapter.auth.refresh_authorization_map",
        lambda repo: AuthorizationMap(state=AuthState.CURRENT),
    )
    monkeypatch.setattr(
        "agent.linz_world.gateway_adapter.load_linz_world_config",
        lambda: LinzWorldConfig(nats_url="nats://127.0.0.1:4222"),
    )

    adapter = LinzWorldPlatformAdapter(PlatformConfig(enabled=True))
    assert await adapter.connect() is False

    login = adapter._repository.get_login()
    assert login.online is False
    assert login.listener_pid == 0
    assert "no authorized NATS subscribe subjects" in login.listener_last_error
    assert adapter.has_fatal_error is True
    assert adapter.fatal_error_code == "linz_world_listener_not_authorized"

    await adapter.disconnect()
    login = adapter._repository.get_login()
    assert "no authorized NATS subscribe subjects" in login.listener_last_error


def test_world_event_projection_uses_redacted_summary(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    record, _ = repo.persist_world_event(
        {
            "event_id": "evt_1",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello", "token": "secret"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
        }
    )

    message = project_to_message_event(record)

    assert message.source.platform.value == "linz_world"
    assert message.message_id == "evt_1"
    assert "secret" not in message.text
    assert "linz_audit:" in message.raw_message["audit_ref"]
    assert message.raw_message["subject"] == "wsp.chat.message.sent"
    assert message.raw_message["event_type"] == "message.sent"


def test_persist_world_event_for_gateway_builds_message_after_state_write(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    raw = {
        "event_id": "evt_1",
        "subject": "wsp.chat.message.sent",
        "event_type": "message.sent",
        "payload": {"text": "hello", "token": "secret"},
        "source": {"room_id": "room_1", "actor_id": "actor_1", "os_id": "os_1", "soul_id": "soul_1"},
        "sequence": {"stream": "world-events", "consumer": "hermes-profile", "nats_sequence": 9},
    }

    result = persist_world_event_for_gateway(raw, repo)
    duplicate = persist_world_event_for_gateway({**raw, "event_id": "evt_2"}, repo)

    stored = repo.recent_events()[0]
    assert result.created is True
    assert result.ack_ready is True
    assert result.message_event is not None
    assert result.record.dispatch_status.value == "processing"
    assert stored.event_id == "evt_1"
    assert stored.dispatch_status.value == "processing"
    assert result.message_event.raw_message["nats_sequence"] == "9"
    assert result.message_event.raw_message["os_id"] == "os_1"
    assert result.message_event.raw_message["soul_id"] == "soul_1"
    assert "secret" not in result.message_event.text
    assert duplicate.created is False
    assert duplicate.message_event is None


def test_persist_world_event_for_gateway_records_projection_ledger(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    raw = {
        "event_id": "evt_ledger",
        "subject": "wsp.chat.message.sent",
        "event_type": "message.sent",
        "payload": {"text": "hello", "token": "secret"},
        "source": {"room_id": "room_1", "actor_id": "actor_1", "os_id": "os_1", "soul_id": "soul_1"},
        "sequence": {"stream": "world-events", "consumer": "hermes-profile", "nats_sequence": 91},
    }

    result = persist_world_event_for_gateway(raw, repo)
    store = EventProjectionStore(root=linz_home)
    try:
        detail = store.get_record("linz_world_nats:evt_ledger")
    finally:
        store.close()

    assert result.message_event is not None
    assert detail is not None
    assert detail["record"]["source_category"] == "linz_world_nats"
    assert detail["record"]["subject"] == "wsp.chat.message.sent"
    assert detail["record"]["event_id"] == "evt_ledger"
    assert detail["record"]["nats_sequence"] == "91"
    assert detail["record"]["raw_payload"]["payload"]["token"] == "secret"
    assert detail["projection"]["message_event_id"] == "evt_ledger"
    assert "secret" not in detail["projection"]["text_summary"]


@pytest.mark.asyncio
async def test_dispatch_world_event_marks_handled_after_success(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    seen = []

    async def _handler(message):
        seen.append(message.message_id)

    result = await dispatch_world_event(
        {
            "event_id": "evt_success",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
        },
        _handler,
        repo,
    )

    assert result.persisted.ack_ready is True
    assert result.handled is True
    assert result.record.dispatch_status.value == "handled"
    assert seen == ["evt_success"]


@pytest.mark.asyncio
async def test_dispatch_world_event_wakes_autonomous_runtime_after_persist(monkeypatch, linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    cfg = OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": {
                "enabled": True,
                "respond_to_world_events": True,
                "idle_cooldown_seconds": 0,
            },
            "intent_generation": "rule",
        }
    )
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: cfg)

    class _SessionStore:
        profile_id = "test-profile"

        def get_or_create_session(self, source):
            return type("Entry", (), {"session_id": "linz-session-1"})()

    async def _handler(message):
        return None

    result = await dispatch_world_event(
        {
            "event_id": "evt_autonomous",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
            "sequence": {"stream": "world-events", "consumer": "hermes-profile", "nats_sequence": 42},
        },
        _handler,
        repo,
        session_store=_SessionStore(),
        wake_inline=True,
    )

    queue_repo = RuntimeQueueRepository(root=linz_home)
    try:
        assert result.handled is True
        inbox = queue_repo.list_inbox("linz-session-1")
        wakes = queue_repo.list_wakes("linz-session-1")
        assert len(inbox) == 1
        assert inbox[0].event_id == "evt_autonomous"
        assert inbox[0].status == "handled"
        assert wakes
        assert wakes[0].wake_reason == "world_event"
        store = EventProjectionStore(root=linz_home)
        try:
            detail = store.get_record("linz_world_nats:evt_autonomous")
        finally:
            store.close()
        assert detail is not None
        reasons = [transition["reason"] for transition in detail["transitions"]]
        assert "os_runtime_wake_scheduled" in reasons
        assert "os_runtime_wake_started" in reasons
        assert "os_runtime_wake" in reasons
        assert "os_runtime_life_state" in reasons
        assert "os_runtime_tension_field" in reasons
        assert "os_runtime_action_potential" in reasons
        assert "os_runtime_self_prompt" in reasons
        assert "os_runtime_open_intent" in reasons
        assert "os_runtime_arbitration" in reasons
        assert "os_runtime_action_execution" in reasons
        assert "os_runtime_evidence_package" in reasons
        tension_transition = next(
            transition for transition in detail["transitions"] if transition["reason"] == "os_runtime_tension_field"
        )
        assert tension_transition["metadata"]["tension_set"]
    finally:
        queue_repo.close()


@pytest.mark.asyncio
async def test_dispatch_world_event_records_async_wake_start_and_result(monkeypatch, linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    cfg = OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": {
                "enabled": True,
                "respond_to_world_events": True,
                "idle_cooldown_seconds": 0,
            },
        }
    )
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: cfg)
    completed = threading.Event()

    def fake_wake(*args, **kwargs):
        completed.set()
        return {"queued": True, "woke": False, "reason": "fake wake completed", "item_id": "item-1"}

    monkeypatch.setattr("agent.linz_world.gateway_adapter._wake_autonomous_runtime", fake_wake)

    class _SessionStore:
        profile_id = "test-profile"

        def get_or_create_session(self, source):
            return type("Entry", (), {"session_id": "linz-session-async"})()

    async def _handler(message):
        return None

    await dispatch_world_event(
        {
            "event_id": "evt_async_autonomous",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
            "sequence": {"stream": "world-events", "consumer": "hermes-profile", "nats_sequence": 43},
        },
        _handler,
        repo,
        session_store=_SessionStore(),
    )

    assert completed.wait(2)
    detail = None
    for _ in range(20):
        store = EventProjectionStore(root=linz_home)
        try:
            detail = store.get_record("linz_world_nats:evt_async_autonomous")
        finally:
            store.close()
        reasons = [transition["reason"] for transition in detail["transitions"]]
        if "os_runtime_wake" in reasons:
            break
        time.sleep(0.1)

    reasons = [transition["reason"] for transition in detail["transitions"]]
    assert "os_runtime_wake_scheduled" in reasons
    assert "os_runtime_wake_started" in reasons
    assert "os_runtime_wake" in reasons


@pytest.mark.asyncio
async def test_dispatch_world_event_records_failure_without_rethrow(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")

    async def _handler(message):
        raise RuntimeError("agent failed")

    result = await dispatch_world_event(
        {
            "event_id": "evt_failure",
            "subject": "wsp.chat.message.sent",
            "event_type": "message.sent",
            "payload": {"text": "hello"},
            "source": {"room_id": "room_1", "actor_id": "actor_1"},
        },
        _handler,
        repo,
        retry_limit=1,
    )

    assert result.persisted.ack_ready is True
    assert result.handled is False
    assert result.record.dispatch_status.value == "failed"
    assert result.record.attempt_count == 1
    assert result.record.requires_manual_handling is True
    assert "agent failed" in result.record.last_error
