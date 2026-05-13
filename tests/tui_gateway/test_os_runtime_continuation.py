from __future__ import annotations

import importlib
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.driver import OS_RUNTIME_CONTINUATION_MARKER


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


@pytest.fixture()
def server(hermes_home):
    with patch.dict(
        "sys.modules",
        {
            "hermes_cli.env_loader": MagicMock(),
            "hermes_cli.banner": MagicMock(),
        },
    ):
        mod = importlib.import_module("tui_gateway.server")
        yield mod
        mod._sessions.clear()
        mod._pending.clear()
        mod._answers.clear()
        mod._methods.clear()
        importlib.reload(mod)


@pytest.fixture()
def session(server):
    sid = "sid-os-runtime"
    session_key = "tui-os-runtime-session"
    s = {
        "session_key": session_key,
        "history": [],
        "history_lock": threading.Lock(),
        "history_version": 0,
        "running": False,
        "attached_images": [],
        "cols": 120,
    }
    server._sessions[sid] = s
    return sid, session_key, s


def test_command_dispatch_os_runtime_goal(server, session, monkeypatch):
    sid, session_key, _ = session
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: OSRuntimeConfig(enabled=True, mode="assisted"))

    result = _call(server, "command.dispatch", name="os_runtime", arg="goal draft docs", session_id=sid)["result"]

    assert result["type"] == "send"
    assert result["message"] == "draft docs"
    assert "assisted goal set" in result["notice"]


def test_pending_input_commands_includes_os_runtime(server):
    assert "os_runtime" in server._PENDING_INPUT_COMMANDS
    assert "os-runtime" in server._PENDING_INPUT_COMMANDS


def test_pause_clear_marks_pending_os_runtime_followup_cancelled(server, session, monkeypatch):
    sid, _, s = session
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: OSRuntimeConfig(enabled=True, mode="assisted"))
    _call(server, "command.dispatch", name="os_runtime", arg="goal draft docs", session_id=sid)

    pause = _call(server, "command.dispatch", name="os_runtime", arg="pause", session_id=sid)["result"]
    assert pause["type"] == "exec"
    assert s["os_runtime_cancel_pending"] is True

    clear = _call(server, "command.dispatch", name="os_runtime", arg="clear", session_id=sid)["result"]
    assert clear["type"] == "exec"
    assert s["os_runtime_cancel_pending"] is True


def test_post_turn_assisted_continuation_dispatches_prompt_submit(server, session, monkeypatch):
    sid, _, s = session
    _FakeAgent.prompts = []
    _FakeDriver.calls = 0
    s["agent"] = _FakeAgent()
    events = []
    monkeypatch.setattr(server, "_emit", lambda event, sid, payload=None: events.append((event, sid, payload or {})))
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: OSRuntimeConfig(enabled=True, mode="assisted"))
    monkeypatch.setattr("agent.os_runtime.driver.OSRuntimeDriver", _FakeDriver)

    server._run_prompt_submit(1, sid, s, "start")

    deadline = time.time() + 2.0
    while time.time() < deadline:
        if _FakeAgent.prompts and _FakeAgent.prompts[-1].startswith(OS_RUNTIME_CONTINUATION_MARKER):
            break
        time.sleep(0.02)

    assert any(payload.get("kind") == "os_runtime" for event, _, payload in events if event == "status.update")
    assert any(prompt.startswith(OS_RUNTIME_CONTINUATION_MARKER) for prompt in _FakeAgent.prompts)


def _call(server, method, **params):
    return server._methods[method](1, params)


class _FakeAgent:
    prompts = []
    model = "test-model"

    def run_conversation(self, prompt, conversation_history=None, stream_callback=None):
        self.prompts.append(prompt)
        return {
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "assistant response"},
            ],
            "final_response": "assistant response",
        }


class _FakeDriver:
    calls = 0

    def __init__(self, *args, **kwargs):
        self.state = SimpleNamespace(status="assisted")

    def evaluate_after_turn(self, *args, **kwargs):
        type(self).calls += 1
        if type(self).calls == 1:
            return SimpleNamespace(
                should_continue=True,
                continuation_prompt=f"{OS_RUNTIME_CONTINUATION_MARKER}\nGoal: draft docs",
                message="OS Runtime continuing",
            )
        return SimpleNamespace(
            should_continue=False,
            continuation_prompt=None,
            message="OS Runtime passive",
        )
