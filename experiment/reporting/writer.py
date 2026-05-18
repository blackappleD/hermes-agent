from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from experiment.collectors.redaction import redact
from experiment.config import ExperimentRunConfig


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(redact(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(redact(row), ensure_ascii=False, sort_keys=True) + "\n")


def write_run_results(
    *,
    config: ExperimentRunConfig,
    backend_result: dict[str, Any],
    summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> dict[str, str]:
    run_dir = config.run_dir
    run_dir.mkdir(parents=True, exist_ok=False)
    records = list(backend_result.get("transitions", []))
    events = [record["event"] for record in records]
    files = {
        "manifest": "manifest.json",
        "events": "events.jsonl",
        "transitions": "transitions.jsonl",
        "summary": "summary.json",
        "summary_csv": "summary.csv",
        "anomalies": "anomalies.json",
    }
    manifest = {
        "run_id": config.run_id,
        "mode": config.mode,
        "phase": config.phase,
        "repeat": config.repeat,
        "profile": config.profile,
        "status": backend_result.get("status"),
        "capabilities": backend_result.get("capabilities", {}),
        "files": files,
    }
    _write_json(run_dir / files["manifest"], manifest)
    _write_jsonl(run_dir / files["events"], events)
    _write_jsonl(run_dir / files["transitions"], records)
    _write_json(run_dir / files["summary"], summary)
    _write_json(run_dir / files["anomalies"], anomalies)
    _write_summary_csv(run_dir / files["summary_csv"], records)
    return files


def _write_summary_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = ["run_id", "phase", "scenario_id", "seed_id", "event_id", "repeat_index", "action_type", "decision", "judgement_status", "stop_reason"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({
                "run_id": record["run_id"],
                "phase": record["phase"],
                "scenario_id": record["scenario_id"],
                "seed_id": record["seed_id"],
                "event_id": record["event"]["event_id"],
                "repeat_index": record["repeat_index"],
                "action_type": record["actual_action"]["action_type"],
                "decision": record["after_state"]["arbitration"]["decision"],
                "judgement_status": record["judgement"]["status"],
                "stop_reason": record["stop_reason"],
            })
