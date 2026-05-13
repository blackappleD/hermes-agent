from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.driver import OS_RUNTIME_CONTINUATION_MARKER
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, Platform, PlatformConfig
from gateway.run import GatewayRunner


class _StubAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True, token="test"), Platform.TELEGRAM)

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        from gateway.platforms.base import SendResult

        return SendResult(success=True, message_id="msg-1")

    async def get_chat_info(self, chat_id):
        return {"id": chat_id, "type": "dm"}


@pytest.fixture()
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    from agent.os_runtime import driver

    driver._DB_CACHE.clear()
    yield home
    driver._DB_CACHE.clear()


@pytest.mark.asyncio
async def test_assisted_continuation_enqueues_plain_message_event(monkeypatch, hermes_home):
    runner = _runner()
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: OSRuntimeConfig(enabled=True, mode="assisted"))
    monkeypatch.setattr("agent.os_runtime.driver.OSRuntimeDriver", _FakeDriver)

    await runner._post_turn_os_runtime_continuation(
        session_entry=SimpleNamespace(session_id="session-1"),
        source=_source(),
        final_response="draft started",
    )

    event = runner.adapters[Platform.TELEGRAM]._pending_messages["telegram:user:123"]
    assert isinstance(event, MessageEvent)
    assert event.text.startswith(OS_RUNTIME_CONTINUATION_MARKER)
    assert event.message_type == MessageType.TEXT


def test_pause_clear_removes_only_os_runtime_synthetic_continuations(hermes_home):
    runner = _runner()
    adapter = runner.adapters[Platform.TELEGRAM]
    session_key = "telegram:user:123"
    normal = MessageEvent(text="real user queued prompt", source=_source(), message_type=MessageType.TEXT)
    synthetic = MessageEvent(
        text=f"{OS_RUNTIME_CONTINUATION_MARKER}\nGoal: draft",
        source=_source(),
        message_type=MessageType.TEXT,
    )
    adapter._pending_messages[session_key] = synthetic
    runner._queued_events[session_key] = [normal, synthetic]

    removed = runner._clear_os_runtime_pending_continuations(session_key, adapter)

    assert removed == 2
    assert session_key not in adapter._pending_messages
    assert runner._queued_events[session_key] == [normal]


@pytest.mark.asyncio
async def test_disabled_config_does_not_affect_goal_queue(monkeypatch, hermes_home):
    runner = _runner()
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: OSRuntimeConfig(enabled=False, mode="assisted"))

    await runner._post_turn_os_runtime_continuation(
        session_entry=SimpleNamespace(session_id="session-1"),
        source=_source(),
        final_response="draft started",
    )

    assert runner.adapters[Platform.TELEGRAM]._pending_messages == {}


def _runner():
    runner = GatewayRunner.__new__(GatewayRunner)
    adapter = _StubAdapter()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._queued_events = {}
    runner._session_key_for_source = lambda source: "telegram:user:123"
    async def _noop(*args, **kwargs):
        return None
    runner._defer_goal_status_notice_after_delivery = _noop
    return runner


def _source():
    return MagicMock(chat_id="123", platform=Platform.TELEGRAM)


class _FakeDriver:
    state = SimpleNamespace(status="assisted")

    def __init__(self, *args, **kwargs):
        pass

    def evaluate_after_turn(self, *args, **kwargs):
        return SimpleNamespace(
            should_continue=True,
            continuation_prompt=f"{OS_RUNTIME_CONTINUATION_MARKER}\nGoal: draft",
            message="OS Runtime continuing",
        )
