from __future__ import annotations

import json
from pathlib import Path

from agent.os_runtime.debug_log import PIPELINE_ROUTE, log_pipeline_step
from agent.os_runtime.domain import LifeState


def test_os_runtime_debug_log_writes_jsonl_to_daily_profile_log(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_OS_RUNTIME_LOG", "1")

    log_pipeline_step(
        surface="test",
        session_id="session-1",
        phase="unit",
        step="life_state",
        data={
            "life_state": LifeState(curiosity=0.25),
            "token": "secret-value",
        },
    )

    files = sorted((home / "logs").glob("os_runtime_*.log"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert record["route"] == " -> ".join(PIPELINE_ROUTE)
    assert record["step"] == "life_state"
    assert record["step_index"] == 3
    assert record["data"]["life_state"]["curiosity"] == 0.25
    assert record["data"]["token"] in {"[REDACTED]", "***"}
    assert "secret-value" not in files[0].read_text(encoding="utf-8")


def test_os_runtime_debug_log_skips_under_pytest_without_explicit_enable(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_OS_RUNTIME_LOG", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/os_runtime/test_debug_log.py::test")

    log_pipeline_step(
        surface="test",
        session_id="session-1",
        phase="unit",
        step="life_state",
        data={"value": 1},
    )

    assert not Path(home / "logs").exists()
