"""Tests for dashboard OS_RUNTIME log aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from hermes_cli.os_runtime_logs import get_os_runtime_logs


def _write_os_runtime_log(home: Path, *records: dict | str) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "os_runtime_20260514.log"
    lines = []
    for record in records:
        if isinstance(record, str):
            lines.append(record)
        else:
            lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _record(step: str, data: dict, *, timestamp: str = "2026-05-14T15:30:00.000+08:00") -> dict:
    return {
        "timestamp": timestamp,
        "surface": "test",
        "session_id": "session-1",
        "profile_id": "default",
        "phase": "after_turn",
        "step": step,
        "step_index": 1,
        "trace_id": "trace-1",
        "data": data,
    }


def _module(response: dict, module_id: str) -> dict:
    return next(module for module in response["modules"] if module["module_id"] == module_id)


def _params(module: dict) -> dict:
    return {param["key"]: param for param in module["parameters"]}


def test_life_state_jsonl_maps_to_life_state_module(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(
        home,
        _record(
            "life_state",
            {
                "life_state": {
                    "energy": 0.82,
                    "fatigue": 0.12,
                    "wakefulness": 0.9,
                    "curiosity": 0.45,
                    "restraint": 0.3,
                }
            },
        ),
    )

    response = get_os_runtime_logs()
    module = _module(response, "life_state")
    params = _params(module)

    assert module["status"] == "ok"
    assert params["energy"]["value"] == 0.82
    assert params["fatigue"]["value"] == 0.12
    assert params["wakefulness"]["value"] == 0.9
    assert params["curiosity"]["value"] == 0.45
    assert params["restraint"]["value"] == 0.3


def test_tension_set_jsonl_maps_to_tension_field_module(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(
        home,
        _record(
            "tension_set",
            {
                "tension_set": {
                    "dynamic_tensions": [
                        {
                            "tension_id": "goal:unsatisfied",
                            "tension_type": "unsatisfied_goal",
                            "intensity": 0.76,
                            "activation": 0.7,
                            "trend": 0.15,
                            "confidence": 0.9,
                        }
                    ]
                }
            },
        ),
    )

    response = get_os_runtime_logs()
    module = _module(response, "tension_field")
    params = _params(module)

    assert module["status"] == "ok"
    assert params["active_tensions"]["value"] == 1
    assert params["intensity"]["value"] == 0.76
    assert params["activation"]["value"] == 0.7
    assert params["trend"]["value"] == 0.15
    assert params["confidence"]["value"] == 0.9


def test_action_potential_jsonl_maps_to_action_potential_module(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(
        home,
        _record(
            "action_potential",
            {
                "action_potential": {
                    "value_potential": 0.7,
                    "learning_potential": 0.5,
                    "risk_cost": 0.2,
                    "overall_score": 0.72,
                    "recommended_depth": "continue_turn",
                }
            },
        ),
    )

    response = get_os_runtime_logs()
    module = _module(response, "action_potential")
    params = _params(module)

    assert module["status"] == "ok"
    assert params["value_potential"]["value"] == 0.7
    assert params["learning_potential"]["value"] == 0.5
    assert params["risk_cost"]["value"] == 0.2
    assert params["overall_score"]["value"] == 0.72
    assert params["recommended_depth"]["value"] == "continue_turn"


def test_consecutive_snapshots_include_change_direction(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(
        home,
        _record("life_state", {"life_state": {"energy": 0.8}}, timestamp="2026-05-14T15:30:00.000+08:00"),
        _record("life_state", {"life_state": {"energy": 0.9}}, timestamp="2026-05-14T15:30:01.000+08:00"),
    )

    response = get_os_runtime_logs()
    params = _params(_module(response, "life_state"))

    assert params["energy"]["previous_value"] == 0.8
    assert params["energy"]["change"] == "up"
    assert round(params["energy"]["delta"], 6) == 0.1


def test_bad_json_is_preserved_as_raw_line(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(home, "{not-json")

    response = get_os_runtime_logs()

    assert response["parse_error_count"] == 1
    assert response["raw_lines"] == ["{not-json"]


def test_unknown_step_is_preserved_in_raw_lines(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(home, _record("future_step", {"future": {"value": 1}}))

    response = get_os_runtime_logs()

    assert response["parse_error_count"] == 0
    assert response["raw_line_count"] == 1
    assert response["raw_lines"]
    assert all(module["status"] == "empty" for module in response["modules"])


def test_no_os_runtime_logs_returns_empty_primary_modules(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))

    response = get_os_runtime_logs()

    assert response["source_files"] == []
    assert response["empty_reason"]
    assert [module["module_id"] for module in response["modules"]] == [
        "life_state",
        "tension_field",
        "action_potential",
    ]
    assert all(module["status"] == "empty" for module in response["modules"])


def test_partial_modules_keep_missing_primary_modules_empty(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(home, _record("life_state", {"life_state": {"energy": 0.82}}))

    response = get_os_runtime_logs()

    assert _module(response, "life_state")["status"] == "ok"
    assert _module(response, "tension_field")["status"] == "empty"
    assert _module(response, "action_potential")["status"] == "empty"


def test_redacted_secret_is_not_expanded_by_parser(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    _write_os_runtime_log(
        home,
        _record("life_state", {"life_state": {"energy": 0.82}, "token": "[REDACTED]"}),
    )

    response = get_os_runtime_logs()

    assert "secret-value" not in json.dumps(response)
    assert "[REDACTED]" in response["raw_lines"][0]
