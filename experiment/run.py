from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from experiment.config import ExperimentRunConfig, parse_args
from experiment.reporting.summaries import build_anomalies, build_summary
from experiment.reporting.writer import write_run_results
from experiment.runtime import MockRuntimeBackend, RuntimeCapabilityBackend
from experiment.scenarios.registry import get_scenarios


def run_experiment(config: ExperimentRunConfig) -> dict[str, object]:
    started_at = datetime.now(UTC).isoformat()
    scenarios = get_scenarios(config.phases)
    backend = MockRuntimeBackend() if config.mode == "mock" else RuntimeCapabilityBackend()
    backend_result = backend.run(config, scenarios)
    initial_files = {
        "manifest": "manifest.json",
        "events": "events.jsonl",
        "transitions": "transitions.jsonl",
        "summary": "summary.json",
        "summary_csv": "summary.csv",
        "anomalies": "anomalies.json",
    }
    summary = build_summary(config=config, scenarios=scenarios, backend_result=backend_result, started_at=started_at, files=initial_files)
    anomalies = build_anomalies(backend_result.get("transitions", []), backend_result.get("invalid_events", []), backend_result.get("blocked_reason"))
    files = write_run_results(config=config, backend_result=backend_result, summary=summary, anomalies=anomalies)
    summary["files"] = files
    return {"run_dir": str(config.run_dir), "summary": summary}


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    result = run_experiment(config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result["summary"].get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
