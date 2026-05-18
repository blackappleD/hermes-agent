from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from experiment.config import ExperimentRunConfig
from experiment.scenarios.registry import Scenario


def build_anomalies(records: list[dict[str, Any]], invalid_events: list[dict[str, Any]], blocked_reason: str | None = None) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    if blocked_reason:
        anomalies.append({"type": "runtime_blocked", "severity": "blocked", "reason": blocked_reason})
    for event in invalid_events:
        anomalies.append({"type": "invalid_event", "severity": "fail", **event})
    for record in records:
        status = record.get("judgement", {}).get("status")
        if status in {"warn", "fail"}:
            anomalies.append({
                "type": "judgement",
                "severity": status,
                "scenario_id": record["scenario_id"],
                "event_id": record["event"]["event_id"],
                "seed_id": record["seed_id"],
                "reasons": record.get("judgement", {}).get("reasons", []),
            })
    return anomalies


def build_summary(
    *,
    config: ExperimentRunConfig,
    scenarios: list[Scenario],
    backend_result: dict[str, Any],
    started_at: str,
    files: dict[str, str],
) -> dict[str, Any]:
    records = list(backend_result.get("transitions", []))
    anomalies = build_anomalies(records, backend_result.get("invalid_events", []), backend_result.get("blocked_reason"))
    phases = sorted({scenario.phase for scenario in scenarios})
    scenario_counts = Counter(scenario.phase for scenario in scenarios)
    seed_ids = sorted({record["seed_id"] for record in records})
    event_ids = sorted({record["event"]["event_id"] for record in records})
    p4_evolution = _p4_evolution(records)
    p5_comparison = _p5_comparison(records)
    return {
        "run_id": config.run_id,
        "mode": config.mode,
        "status": backend_result.get("status", "completed"),
        "phases": phases,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "counts": {
            "events": len(event_ids),
            "transitions": len(records),
            "scenarios": len(scenarios),
            "seeds": len(seed_ids),
            "anomalies": len(anomalies),
        },
        "coverage": {
            "scenario_counts_by_phase": dict(sorted(scenario_counts.items())),
            "required_files": ["events.jsonl", "transitions.jsonl", "summary.json", "summary.csv", "anomalies.json"],
            "raw_transition_chain": ["event", "context/signals", "life_state", "tension_field", "action_potential", "self_prompt", "open_intent", "arbitration", "action/evidence"],
        },
        "capabilities": backend_result.get("capabilities", {}),
        "p4_evolution": p4_evolution,
        "p5_seed_comparison": p5_comparison,
        "anomalies": anomalies,
        "files": files,
    }


def _p4_evolution(records: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for record in records:
        if record["phase"] != "P4":
            continue
        memory = record["delta_summary"].get("memory_evolution", {})
        for group in ("threshold_delta", "preference_delta", "memory_weight_delta", "relationship_delta"):
            for field, value in memory.get(group, {}).items():
                totals[group][field] += float(value)
    return {group: {field: round(value, 4) for field, value in fields.items()} for group, fields in totals.items()}


def _p5_comparison(records: list[dict[str, Any]]) -> dict[str, Any]:
    comparison: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["phase"] != "P5":
            continue
        action = record["actual_action"]["action_type"]
        seed = record["seed_id"]
        entry = comparison.setdefault(seed, {"actions": Counter(), "decisions": Counter(), "relationship_delta": {}})
        entry["actions"][action] += 1
        entry["decisions"][record["after_state"]["arbitration"]["decision"]] += 1
        for key, value in record["after_state"].get("memory_evolution", {}).get("relationship_delta", {}).items():
            entry["relationship_delta"][key] = round(entry["relationship_delta"].get(key, 0.0) + float(value), 4)
    return {
        seed: {
            "actions": dict(data["actions"]),
            "decisions": dict(data["decisions"]),
            "relationship_delta": data["relationship_delta"],
        }
        for seed, data in sorted(comparison.items())
    }
