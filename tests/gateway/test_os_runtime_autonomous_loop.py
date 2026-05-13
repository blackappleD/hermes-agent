from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.os_runtime.config import OSRuntimeConfig
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
    yield home


@pytest.mark.asyncio
async def test_gateway_autonomous_pre_turn_starts_idle(monkeypatch, hermes_home):
    cfg = OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": {
                "enabled": True,
                "start_with_gateway": True,
                "apply_to_all_turns": True,
                "inject_self_prompt": False,
            },
        }
    )
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: cfg)
    runner = _runner()
    event = MessageEvent(text="hello", source=_source(), message_type=MessageType.TEXT)

    await runner._pre_turn_os_runtime_autonomous_hook(
        session_entry=SimpleNamespace(session_id="session-1"),
        event=event,
    )

    from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository

    repo = RuntimeQueueRepository(root=hermes_home)
    try:
        state = repo.load_state("session-1")
        assert state is not None
        assert state.status == "idle"
    finally:
        repo.close()


@pytest.mark.asyncio
async def test_gateway_autonomous_disabled_is_noop(monkeypatch, hermes_home):
    cfg = OSRuntimeConfig.from_dict(
        {
            "enabled": False,
            "autonomous": {"enabled": True, "apply_to_all_turns": True},
        }
    )
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: cfg)
    runner = _runner()
    event = MessageEvent(text="hello", source=_source(), message_type=MessageType.TEXT)

    await runner._pre_turn_os_runtime_autonomous_hook(
        session_entry=SimpleNamespace(session_id="session-1"),
        event=event,
    )

    from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository

    repo = RuntimeQueueRepository(root=hermes_home)
    try:
        assert repo.load_state("session-1") is None
    finally:
        repo.close()


@pytest.mark.asyncio
async def test_gateway_autonomous_manual_tick_command(monkeypatch, hermes_home):
    cfg = OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": {
                "enabled": True,
                "idle_cooldown_seconds": 0,
            },
        }
    )
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: cfg)
    runner = _runner()
    event = MessageEvent(
        text="/os_runtime autonomous tick",
        source=_source(),
        message_type=MessageType.TEXT,
    )

    output = await runner._handle_os_runtime_command(event)

    assert "Autonomous tick completed" in output or "Autonomous tick skipped" in output


def _runner():
    runner = GatewayRunner.__new__(GatewayRunner)
    adapter = _StubAdapter()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._queued_events = {}
    runner._session_key_for_source = lambda source: "telegram:user:123"
    runner.session_store = SimpleNamespace(
        get_or_create_session=lambda source: SimpleNamespace(session_id="session-1")
    )
    return runner


def _source():
    return MagicMock(chat_id="123", platform=Platform.TELEGRAM)
