import json

from experiment.config import ExperimentRunConfig
from experiment.events.library import load_events
from experiment.run import run_experiment


def test_result_files_redact_sensitive_payload_values(tmp_path, monkeypatch) -> None:
    secret = "sk-test-secret-value-123456"
    events = load_events()
    events["P1-clear-opportunity"]["payload"].update({
        "token": secret,
        "api_key": "api-key-secret",
        "password": "password-secret",
        "private_key": "private-key-secret",
        "authorization": "Bearer auth-secret",
    })
    monkeypatch.setattr("experiment.runtime.mock_backend.load_events", lambda: events)
    run_experiment(ExperimentRunConfig(phase="P1", mode="mock", repeat=1, run_id="test-redact", output_root=tmp_path))
    combined = ""
    for filename in ["events.jsonl", "transitions.jsonl", "summary.json", "anomalies.json"]:
        combined += (tmp_path / "test-redact" / filename).read_text(encoding="utf-8")
    assert secret not in combined
    assert "api-key-secret" not in combined
    assert "password-secret" not in combined
    assert "private-key-secret" not in combined
    assert "auth-secret" not in combined


def test_restricted_payload_is_replaced_with_audit_ref(tmp_path, monkeypatch) -> None:
    events = load_events()
    events["P1-clear-opportunity"]["payload"] = {
        "classification": "restricted",
        "restricted_raw_payload": True,
        "body": "restricted raw payload should not be stored",
    }
    monkeypatch.setattr("experiment.runtime.mock_backend.load_events", lambda: events)
    run_experiment(ExperimentRunConfig(phase="P1", mode="mock", repeat=1, run_id="test-restricted", output_root=tmp_path))
    event_text = (tmp_path / "test-restricted" / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(event_text.splitlines()[0])
    assert event["payload"]["redacted"] is True
    assert "audit_ref" in event["payload"]
    assert "restricted raw payload should not be stored" not in event_text
