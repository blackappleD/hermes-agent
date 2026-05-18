from __future__ import annotations

import argparse
from types import SimpleNamespace

from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from gateway.event_projection_store import EventProjectionStore
from scripts import formal_experiment_lib as formal


def _args(home, **overrides):
    data = {"profile": "default", "hermes_home": str(home), "phase": "all", "no_live_check": True}
    data.update(overrides)
    return argparse.Namespace(**data)


def _passing_status():
    return {
        "login_state": "logged_in",
        "login_verified": True,
        "identity": {"compute_token_configured": True},
        "authorization_state": "current",
        "gateway_state": "running",
        "gateway_linz_platform_enabled": True,
        "gateway_linz_platform_state": "online",
    }


def _runtime_cfg(enabled=True):
    return SimpleNamespace(enabled=enabled, autonomous=SimpleNamespace(enabled=False, start_with_gateway=False))


def _make_home(home):
    store = EventProjectionStore(root=home)
    store.close()
    repo = OSRuntimeEventRepository(root=home)
    repo.close()
    (home / "linz_world").mkdir(parents=True, exist_ok=True)
    (home / "linz_world" / "state.json").write_text('{"receipts":[]}', encoding="utf-8")
    (home / "logs").mkdir(parents=True, exist_ok=True)
    (home / "logs" / "os_runtime_20260518.log").write_text("", encoding="utf-8")


def test_prepare_passes_with_login_auth_gateway_and_runtime_paths(tmp_path, monkeypatch, capsys):
    home = tmp_path / "hermes"
    _make_home(home)
    monkeypatch.setattr("agent.linz_world.status.status_summary", lambda check_live=True: _passing_status())
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: _runtime_cfg())

    code = formal.run_prepare(_args(home))

    assert code == 0
    output = capsys.readouterr().out
    assert '"success": true' in output
    assert "gateway_message_events_db" in output


def test_prepare_fails_closed_when_linz_logged_out(tmp_path, monkeypatch, capsys):
    home = tmp_path / "hermes"
    _make_home(home)
    status = _passing_status()
    status["login_state"] = "logged_out"
    status["login_verified"] = False
    monkeypatch.setattr("agent.linz_world.status.status_summary", lambda check_live=True: status)
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: _runtime_cfg())

    code = formal.run_prepare(_args(home))

    assert code == 2
    output = capsys.readouterr().out
    assert '"linz_login"' in output
    assert "Run hermes linz login" in output


def test_prepare_fails_closed_when_gateway_or_paths_missing(tmp_path, monkeypatch, capsys):
    home = tmp_path / "hermes"
    home.mkdir()
    status = _passing_status()
    status["gateway_state"] = "stopped"
    monkeypatch.setattr("agent.linz_world.status.status_summary", lambda check_live=True: status)
    monkeypatch.setattr("hermes_cli.os_runtime.load_runtime_config", lambda: _runtime_cfg(enabled=False))

    code = formal.run_prepare(_args(home))

    assert code == 2
    output = capsys.readouterr().out
    assert "gateway_state=stopped" in output
    assert "Missing required file" in output
    assert "os_runtime_config" in output
