from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from hermes_cli.profile_gateways import (
    print_profile_gateway_launch_results,
    start_profile_gateways,
)
from hermes_cli.profiles import ProfileInfo


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


def _profile(name: str, path: Path, *, running: bool = False) -> ProfileInfo:
    return ProfileInfo(
        name=name,
        path=path,
        is_default=(name == "default"),
        gateway_running=running,
    )


def test_dashboard_gateway_bootstrap_starts_missing_profiles(monkeypatch, tmp_path):
    calls: list[tuple[list[str], dict]] = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(4242)

    monkeypatch.setattr(
        "hermes_cli.profile_gateways.get_python_path",
        lambda: "python-test",
    )
    monkeypatch.setattr(
        "hermes_cli.profile_gateways.windows_detach_popen_kwargs",
        lambda: {"start_new_session": True},
    )

    default_home = tmp_path / "default"
    shannon_home = tmp_path / "profiles" / "shannon"
    results = start_profile_gateways(
        profiles=[
            _profile("default", default_home),
            _profile("shannon", shannon_home),
        ],
        popen_factory=fake_popen,
    )

    assert [row.status for row in results] == ["started", "started"]
    assert [row.pid for row in results] == [4242, 4242]
    assert len(calls) == 2

    default_args, default_kwargs = calls[0]
    assert default_args == [
        "python-test",
        "-m",
        "hermes_cli.main",
        "--profile",
        "default",
        "gateway",
        "run",
        "--replace",
        "--quiet",
    ]
    assert default_kwargs["env"]["HERMES_HOME"] == str(default_home)
    assert default_kwargs["env"]["HERMES_GATEWAY_DETACHED"] == "1"
    assert default_kwargs["stdin"] is subprocess.DEVNULL
    assert default_kwargs["stdout"] is subprocess.DEVNULL
    assert default_kwargs["stderr"] is subprocess.DEVNULL
    assert default_kwargs["close_fds"] is True
    assert default_kwargs["start_new_session"] is True

    shannon_args, shannon_kwargs = calls[1]
    assert shannon_args[3:5] == ["--profile", "shannon"]
    assert shannon_kwargs["env"]["HERMES_HOME"] == str(shannon_home)


def test_dashboard_gateway_bootstrap_skips_running_profiles(monkeypatch, tmp_path):
    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(100)

    results = start_profile_gateways(
        profiles=[_profile("pipi", tmp_path / "pipi", running=True)],
        popen_factory=fake_popen,
    )

    assert len(calls) == 0
    assert results[0].profile == "pipi"
    assert results[0].status == "already_running"


def test_profile_gateway_bootstrap_can_skip_current_profile(monkeypatch, tmp_path):
    calls = []
    current_home = tmp_path / "profiles" / "shannon"
    other_home = tmp_path / "profiles" / "pipi"

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(101)

    monkeypatch.setenv("HERMES_HOME", str(current_home))

    results = start_profile_gateways(
        profiles=[
            _profile("shannon", current_home),
            _profile("pipi", other_home),
        ],
        popen_factory=fake_popen,
        exclude_current_profile=True,
    )

    assert [row.status for row in results] == ["skipped_current", "started"]
    assert len(calls) == 1
    assert calls[0][0][3:5] == ["--profile", "pipi"]


def test_profile_gateway_bootstrap_skips_current_profile_by_name(monkeypatch, tmp_path):
    calls = []
    default_home = tmp_path / ".hermes"
    other_home = tmp_path / ".hermes" / "profiles" / "shannon"

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeProcess(101)

    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(
        "hermes_cli.profile_gateways.get_active_profile_name",
        lambda: "default",
    )

    results = start_profile_gateways(
        profiles=[
            _profile("default", default_home),
            _profile("shannon", other_home),
        ],
        popen_factory=fake_popen,
        exclude_current_profile=True,
    )

    assert [row.status for row in results] == ["skipped_current", "started"]
    assert len(calls) == 1
    assert calls[0][0][3:5] == ["--profile", "shannon"]


def test_dashboard_gateway_bootstrap_reports_spawn_failures(tmp_path):
    def fake_popen(args, **kwargs):
        raise OSError("boom")

    results = start_profile_gateways(
        profiles=[_profile("broken", tmp_path / "broken")],
        popen_factory=fake_popen,
    )

    assert len(results) == 1
    assert results[0].profile == "broken"
    assert results[0].status == "failed"
    assert "boom" in results[0].error


def test_dashboard_gateway_summary_is_compact(capsys, tmp_path):
    results = start_profile_gateways(
        profiles=[
            _profile("pipi", tmp_path / "pipi", running=True),
            _profile("shannon", tmp_path / "shannon"),
        ],
        popen_factory=lambda args, **kwargs: _FakeProcess(55),
    )

    print_profile_gateway_launch_results(results)

    out = capsys.readouterr().out
    assert "Starting profile gateways" in out
    assert "started shannon (PID 55)" in out
    assert "already running pipi" in out


def test_gateway_restart_all_uses_detached_profile_bootstrap(monkeypatch, capsys):
    import hermes_cli.gateway as gateway_cli

    calls = []

    monkeypatch.setattr(gateway_cli, "supports_systemd_services", lambda: False)
    monkeypatch.setattr(gateway_cli, "is_macos", lambda: False)
    monkeypatch.setattr(gateway_cli, "is_windows", lambda: False)
    monkeypatch.setattr(gateway_cli, "kill_gateway_processes", lambda **kwargs: calls.append(("kill", kwargs)) or 2)
    monkeypatch.setattr(gateway_cli, "_wait_for_gateway_exit", lambda **kwargs: calls.append(("wait", kwargs)))
    monkeypatch.setattr(
        gateway_cli,
        "_start_all_profile_gateways_after_gateway_restart",
        lambda: calls.append(("start_profiles", {})),
    )
    monkeypatch.setattr(
        gateway_cli,
        "run_gateway",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("foreground gateway should not run")),
    )

    gateway_cli._gateway_command_inner(
        SimpleNamespace(gateway_command="restart", all=True, system=False)
    )

    assert calls == [
        ("kill", {"all_profiles": True}),
        ("wait", {"timeout": 10.0, "force_after": 5.0}),
        ("start_profiles", {}),
    ]
    assert "Stopped 2 gateway process(es) across all profiles" in capsys.readouterr().out
