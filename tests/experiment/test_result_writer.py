import csv
import json

from experiment.config import ExperimentRunConfig
from experiment.run import run_experiment


def test_phase_all_writes_expected_result_files(tmp_path) -> None:
    result = run_experiment(ExperimentRunConfig(phase="all", mode="mock", run_id="test-all", output_root=tmp_path))
    run_dir = tmp_path / "test-all"
    for filename in ["manifest.json", "events.jsonl", "transitions.jsonl", "summary.json", "summary.csv", "anomalies.json"]:
        assert (run_dir / filename).exists()
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["transitions"] == result["summary"]["counts"]["transitions"]
    assert {"P0", "P1", "P2", "P3", "P4", "P5"} <= set(summary["phases"])
    rows = list(csv.DictReader((run_dir / "summary.csv").open(encoding="utf-8")))
    assert len(rows) == summary["counts"]["transitions"]


def test_runtime_mode_fails_closed_without_fake_transitions(tmp_path) -> None:
    result = run_experiment(ExperimentRunConfig(phase="P0", mode="runtime", run_id="test-runtime", output_root=tmp_path))
    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["counts"]["transitions"] == 0
    assert result["summary"]["capabilities"]["fail_closed"] is True
    transitions = (tmp_path / "test-runtime" / "transitions.jsonl").read_text(encoding="utf-8")
    assert transitions == ""
