from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

from agent.linz_world.event_state import LinzStateRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.domain import EventSource
from gateway.event_projection_store import EventProjectionStore
from scripts import formal_experiment_lib as formal


def _args(home, output_root, run_id="formal-export"):
    return argparse.Namespace(
        profile="default",
        hermes_home=str(home),
        run_id=run_id,
        output_root=str(output_root),
        since=None,
        until=None,
        fail_on_anomaly=False,
    )


def _gateway_event(home, run_id="formal-export", *, secret=False):
    store = EventProjectionStore(root=home)
    raw_event = {
        "event_id": "world-1",
        "subject": "wsp.mrk.requirement.published",
        "event_type": "requirement.published",
        "payload": {
            "run_id": run_id,
            "phase": "P1",
            "scenario_id": "P1-single-requirement-perturbation",
            "title": "Formal export event",
            "api_key": "SECRET_API_KEY_VALUE" if secret else "",
        },
        "occurred_at": "2026-05-18T00:00:00Z",
    }
    record = SimpleNamespace(
        event_id="world-1",
        subject=raw_event["subject"],
        event_type=raw_event["event_type"],
        payload_summary=json.dumps(raw_event["payload"]),
        occurred_at=raw_event["occurred_at"],
        nats_sequence="1",
        source={"actor_id": "world"},
        attempt_count=0,
        last_error="",
    )
    try:
        store.record_linz_world_event(raw_event, record, consume_status="handled")
    finally:
        store.close()


def _runtime_event(home, run_id="formal-export"):
    repo = OSRuntimeEventRepository(root=home)
    try:
        repo.append(
            {
                "event_id": "osr-1",
                "event_type": "os_runtime_transition",
                "source": EventSource.SYSTEM.value,
                "trace_id": f"trace-{run_id}",
                "session_id": f"formal:{run_id}",
                "timestamp": "2026-05-18T00:00:01Z",
                "summary": f"transition for {run_id}",
                "metadata": {
                    "run_id": run_id,
                    "life_state": {"energy": "stable"},
                    "tension_field": {"market": 0.5},
                    "tension_set": ["market"],
                    "action_potential": {"score": 0.6},
                    "self_prompt": {"prompt_id": "self-1"},
                    "open_intent": {"intent_id": "intent-1"},
                    "arbitration": {"decision": "observe"},
                    "actual_action": {"type": "none"},
                    "evidence_refs": ["evidence:1"],
                },
            }
        )
    finally:
        repo.close()


def _linz_state(home, run_id="formal-export"):
    repo = LinzStateRepository(root=home / "linz_world", profile_id="default")
    repo.save({"identity": {"profile_id": "default"}})
    repo.append_list(
        "receipts",
        {
            "request_id": "req-1",
            "status": "published",
            "world_event_id": "world-1",
            "payload_summary": json.dumps({"run_id": run_id}),
            "recorded_at": "2026-05-18T00:00:00Z",
        },
    )


def _runtime_log(home, run_id="formal-export", *, secret=False):
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": "2026-05-18T00:00:02Z", "run_id": run_id, "step": "os_runtime_wake"}
    if secret:
        payload["authorization"] = "Bearer SECRET_AUTH_VALUE"
    (log_dir / "os_runtime_20260518.log").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _empty_runtime_state_db(home):
    repo = OSRuntimeEventRepository(root=home)
    repo.close()


def _pipeline_logs(home, run_id="formal-export", *, complete=True):
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "route": "goal_event -> signal_set -> life_state -> tension_operation -> tension_set -> action_potential -> self_prompt -> open_intent -> arbiter",
        "surface": "driver",
        "session_id": f"formal:{run_id}",
        "trace_id": f"trace-{run_id}",
        "phase": "after_turn",
    }
    if not complete:
        rows = [
            {
                **base,
                "timestamp": "2026-05-18T00:00:00.000+00:00",
                "step": "goal_event",
                "step_index": 1,
                "data": {"run_id": run_id, "event": "seen"},
            }
        ]
    else:
        rows = [
            {**base, "timestamp": "2026-05-18T00:00:01.000+00:00", "step": "life_state", "step_index": 3, "data": {"run_id": run_id, "life_state": {"energy": "stable"}}},
            {**base, "timestamp": "2026-05-18T00:00:02.000+00:00", "step": "tension_operation", "step_index": 4, "data": {"run_id": run_id, "tension_interpretation": {"dominant": "market"}}},
            {**base, "timestamp": "2026-05-18T00:00:03.000+00:00", "step": "tension_set", "step_index": 5, "data": {"run_id": run_id, "tension_set": ["market"]}},
            {**base, "timestamp": "2026-05-18T00:00:04.000+00:00", "step": "action_potential", "step_index": 6, "data": {"run_id": run_id, "action_potential": {"score": 0.6}}},
            {**base, "timestamp": "2026-05-18T00:00:05.000+00:00", "step": "self_prompt", "step_index": 7, "data": {"run_id": run_id, "self_prompt": {"prompt_id": "self-1"}}},
            {**base, "timestamp": "2026-05-18T00:00:06.000+00:00", "step": "open_intent", "step_index": 8, "data": {"run_id": run_id, "intent": {"intent_id": "intent-1"}}},
            {**base, "timestamp": "2026-05-18T00:00:07.000+00:00", "step": "arbiter", "step_index": 9, "data": {"run_id": run_id, "arbitration": {"decision": "observe"}}},
            {**base, "timestamp": "2026-05-18T00:00:08.000+00:00", "step": "action_execution", "step_index": 10, "data": {"run_id": run_id, "actual_action": {"type": "none"}}},
            {**base, "timestamp": "2026-05-18T00:00:09.000+00:00", "step": "evidence_package", "step_index": 11, "data": {"run_id": run_id, "evidence_refs": ["evidence:1"]}},
        ]
    (log_dir / "os_runtime_20260518.log").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_export_writes_required_files_from_real_artifacts(tmp_path):
    home = tmp_path / "hermes"
    output_root = tmp_path / "results"
    _gateway_event(home)
    _runtime_event(home)
    _linz_state(home)
    _runtime_log(home)

    code = formal.run_export(_args(home, output_root))

    assert code == 0
    out = output_root / "formal-export"
    for name in ["manifest.json", "events.jsonl", "transitions.jsonl", "os_runtime_raw.jsonl", "summary.json", "summary.csv", "anomalies.json"]:
        assert (out / name).exists()
    transitions = (out / "transitions.jsonl").read_text(encoding="utf-8")
    assert "life_state" in transitions
    assert "evidence_refs" in transitions


def test_export_marks_missing_runtime_transition_as_anomaly(tmp_path):
    home = tmp_path / "hermes"
    output_root = tmp_path / "results"
    _gateway_event(home)
    _linz_state(home)
    (home / "logs").mkdir(parents=True, exist_ok=True)

    code = formal.run_export(_args(home, output_root))

    assert code == 0
    anomalies = json.loads((output_root / "formal-export" / "anomalies.json").read_text(encoding="utf-8"))
    assert any(item["code"] == "missing_transition" for item in anomalies)


def test_export_builds_transition_from_os_runtime_pipeline_logs(tmp_path):
    home = tmp_path / "hermes"
    output_root = tmp_path / "results"
    _gateway_event(home)
    _empty_runtime_state_db(home)
    _linz_state(home)
    _pipeline_logs(home)

    code = formal.run_export(_args(home, output_root))

    assert code == 0
    transitions = [
        json.loads(line)
        for line in (output_root / "formal-export" / "transitions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(transitions) == 1
    transition = transitions[0]
    assert transition["life_state"] == {"energy": "stable"}
    assert transition["tension_set"] == ["market"]
    assert transition["action_potential"] == {"score": 0.6}
    assert transition["self_prompt"] == {"prompt_id": "self-1"}
    assert transition["open_intent"] == {"intent_id": "intent-1"}
    assert transition["arbitration"] == {"decision": "observe"}
    anomalies = json.loads((output_root / "formal-export" / "anomalies.json").read_text(encoding="utf-8"))
    assert not any(item["code"] == "missing_transition" for item in anomalies)


def test_export_marks_incomplete_runtime_raw_as_anomaly(tmp_path):
    home = tmp_path / "hermes"
    output_root = tmp_path / "results"
    _gateway_event(home)
    _empty_runtime_state_db(home)
    _linz_state(home)
    _pipeline_logs(home, complete=False)

    code = formal.run_export(_args(home, output_root))

    assert code == 0
    transitions = (output_root / "formal-export" / "transitions.jsonl").read_text(encoding="utf-8")
    assert transitions == ""
    anomalies = json.loads((output_root / "formal-export" / "anomalies.json").read_text(encoding="utf-8"))
    assert any(item["code"] == "missing_transition" for item in anomalies)


def test_export_redacts_nested_json_jsonl_and_csv_outputs(tmp_path):
    home = tmp_path / "hermes"
    output_root = tmp_path / "results"
    _gateway_event(home, secret=True)
    _runtime_event(home)
    _linz_state(home)
    _runtime_log(home, secret=True)

    formal.run_export(_args(home, output_root))

    combined = "\n".join(path.read_text(encoding="utf-8") for path in (output_root / "formal-export").iterdir() if path.is_file())
    assert "SECRET_API_KEY_VALUE" not in combined
    assert "SECRET_AUTH_VALUE" not in combined
    assert "[REDACTED]" in combined
