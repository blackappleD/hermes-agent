from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

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
    path = home / "linz_world" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "request_id": "req-1",
                        "status": "published",
                        "world_event_id": "world-1",
                        "payload_summary": json.dumps({"run_id": run_id}),
                        "recorded_at": "2026-05-18T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _runtime_log(home, run_id="formal-export", *, secret=False):
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": "2026-05-18T00:00:02Z", "run_id": run_id, "step": "os_runtime_wake"}
    if secret:
        payload["authorization"] = "Bearer SECRET_AUTH_VALUE"
    (log_dir / "os_runtime_20260518.log").write_text(json.dumps(payload) + "\n", encoding="utf-8")


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
