from __future__ import annotations

from pathlib import Path

import pytest

from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.driver import OSRuntimeDriver
from hermes_cli.os_runtime import handle_os_runtime_command


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


def test_status_passive_goal_pause_resume_clear(hermes_home):
    cfg = OSRuntimeConfig(enabled=True, mode="assisted", max_continuation_turns=3)
    assert "No active" in handle_os_runtime_command("status", session_id="s1", config=cfg).output

    passive = handle_os_runtime_command("passive", session_id="s1", config=cfg)
    assert "passive" in passive.output.lower()
    assert OSRuntimeDriver("s1", config=cfg).state.status == "passive"

    goal = handle_os_runtime_command("goal draft docs", session_id="s1", config=cfg)
    assert goal.send_message == "draft docs"
    assert "assisted goal set" in goal.output

    paused = handle_os_runtime_command("pause", session_id="s1", config=cfg)
    assert paused.clear_pending is True
    assert "paused" in paused.output

    resumed = handle_os_runtime_command("resume", session_id="s1", config=cfg)
    assert "resumed" in resumed.output

    cleared = handle_os_runtime_command("clear", session_id="s1", config=cfg)
    assert cleared.clear_pending is True
    assert "cleared" in cleared.output


def test_config_disabled_empty_goal_and_missing_session(hermes_home):
    disabled = OSRuntimeConfig(enabled=False, mode="assisted")
    result = handle_os_runtime_command("goal draft", session_id="s1", config=disabled)
    assert "disabled" in result.output
    assert result.send_message is None

    enabled = OSRuntimeConfig(enabled=True, mode="assisted")
    assert "Usage" in handle_os_runtime_command("goal", session_id="s1", config=enabled).output
    assert "missing session" in handle_os_runtime_command("status", session_id="", config=enabled).output


def test_tick_obeys_driver_gates(hermes_home):
    cfg = OSRuntimeConfig(enabled=True, mode="passive")
    handle_os_runtime_command("passive", session_id="s1", config=cfg)
    result = handle_os_runtime_command("tick", session_id="s1", config=cfg)
    assert result.send_message is None
    assert result.decision["should_continue"] is False
