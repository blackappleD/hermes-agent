from experiment.collectors.mappings import ACTION_FIELDS, LIFE_FIELDS, TENSION_FIELDS
from experiment.config import ExperimentRunConfig
from experiment.run import run_experiment


def test_p1_repeat_records_tick_decay_and_required_schema(tmp_path) -> None:
    result = run_experiment(ExperimentRunConfig(phase="P1", mode="mock", repeat=3, run_id="test-p1", output_root=tmp_path))
    summary = result["summary"]
    assert summary["status"] == "completed"
    assert summary["counts"]["transitions"] == 12
    transitions = _records(tmp_path / "test-p1" / "transitions.jsonl")
    assert {record["repeat_index"] for record in transitions} == {1, 2, 3}
    required_chain = ["event", "context/signals", "life_state", "tension_field", "action_potential", "self_prompt", "open_intent", "arbitration", "action/evidence"]
    for record in transitions:
        assert [stage["stage"] for stage in record["raw_transitions"]] == required_chain
        assert set(LIFE_FIELDS) <= set(record["after_state"]["life_state"])
        assert set(TENSION_FIELDS) <= set(record["after_state"]["tension_field"])
        assert set(ACTION_FIELDS) <= set(record["after_state"]["action_potential"])
        assert record["tick_state"]["tick_policy"]["kind"] == "repeat_decay"
        assert record["judgement"]["status"] in {"pass", "warn"}


def test_p2_records_action_ranking_intent_source_and_arbitration(tmp_path) -> None:
    run_experiment(ExperimentRunConfig(phase="P2", mode="mock", run_id="test-p2", output_root=tmp_path))
    transitions = _records(tmp_path / "test-p2" / "transitions.jsonl")
    assert {record["scenario_id"] for record in transitions} >= {"P2-C1", "P2-C2", "P2-C3", "P2-C4", "P2-C5", "P2-C6"}
    for record in transitions:
        assert record["after_state"]["action_potential_ranking"]
        assert record["after_state"]["open_intent"]["source_action_potential"]
        assert record["after_state"]["arbitration"]["decision"] in {"auto_execute", "sandbox_execute", "require_approval", "report_only", "reject"}


def test_p3_records_life_state_delta(tmp_path) -> None:
    run_experiment(ExperimentRunConfig(phase="P3", mode="mock", run_id="test-p3", output_root=tmp_path))
    transitions = _records(tmp_path / "test-p3" / "transitions.jsonl")
    assert {record["scenario_id"] for record in transitions} >= {"P3-L1", "P3-L2", "P3-L3", "P3-L4", "P3-L5"}
    assert any(any(abs(value) > 0 for value in record["delta_summary"]["life_state"].values()) for record in transitions)


def test_p4_records_evolution_summary(tmp_path) -> None:
    result = run_experiment(ExperimentRunConfig(phase="P4", mode="mock", run_id="test-p4", output_root=tmp_path))
    evolution = result["summary"]["p4_evolution"]
    assert "threshold_delta" in evolution
    assert "memory_weight_delta" in evolution or "relationship_delta" in evolution


def test_p5_records_seed_comparison_and_relationships(tmp_path) -> None:
    result = run_experiment(ExperimentRunConfig(phase="P5", mode="mock", run_id="test-p5", output_root=tmp_path))
    comparison = result["summary"]["p5_seed_comparison"]
    assert {"seed_bold_001", "seed_competitive_001", "seed_social_001", "seed_fragile_001"} <= set(comparison)
    assert any(data["relationship_delta"] for data in comparison.values())


def _records(path):
    import json

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
