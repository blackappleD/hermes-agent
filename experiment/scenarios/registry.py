from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    phase: str
    title: str
    seed_ids: tuple[str, ...]
    event_sequence: tuple[str, ...]
    repeat: int = 1
    tick_policy: dict[str, Any] = field(default_factory=dict)
    judgement_rules: tuple[str, ...] = ("direction", "magnitude", "bounds")


DEFAULT_SEED = ("seed_neutral_001",)

SCENARIOS: tuple[Scenario, ...] = (
    Scenario("P0-identity-smoke", "P0", "Identity and environment smoke", DEFAULT_SEED, ("P0-login", "P0-heartbeat", "P0-system-notice"), tick_policy={"kind": "heartbeat", "decay": 0.01}),
    Scenario("P1-clear-opportunity", "P1", "Single clear opportunity perturbation", DEFAULT_SEED, ("P1-clear-opportunity",), repeat=3, tick_policy={"kind": "repeat_decay", "decay": 0.03}),
    Scenario("P1-ambiguous-risk", "P1", "Single ambiguous risk perturbation", DEFAULT_SEED, ("P1-ambiguous-risk",), repeat=3, tick_policy={"kind": "repeat_decay", "decay": 0.03}),
    Scenario("P1-pressure-rule", "P1", "Single pressure and rule perturbation", DEFAULT_SEED, ("P1-pressure-rule",), repeat=3, tick_policy={"kind": "repeat_decay", "decay": 0.03}),
    Scenario("P1-failure-feedback", "P1", "Single failure feedback perturbation", DEFAULT_SEED, ("P1-failure-feedback",), repeat=3, tick_policy={"kind": "repeat_decay", "decay": 0.03}),
    Scenario("P2-C1", "P2", "Opportunity with clear requirements", DEFAULT_SEED, ("P1-clear-opportunity",), judgement_rules=("ap_ranking", "intent_source", "arbitration")),
    Scenario("P2-C2", "P2", "Opportunity and risk conflict", DEFAULT_SEED, ("P1-clear-opportunity", "P1-ambiguous-risk"), judgement_rules=("ap_ranking", "intent_source", "arbitration")),
    Scenario("P2-C3", "P2", "Pressure and rule conflict", DEFAULT_SEED, ("P1-pressure-rule",), judgement_rules=("ap_ranking", "intent_source", "arbitration")),
    Scenario("P2-C4", "P2", "Failure and repair", DEFAULT_SEED, ("P1-failure-feedback", "P4-rule-learning"), judgement_rules=("ap_ranking", "intent_source", "arbitration")),
    Scenario("P2-C5", "P2", "Survival and opportunity", DEFAULT_SEED, ("P2-survival-opportunity",), judgement_rules=("ap_ranking", "intent_source", "arbitration")),
    Scenario("P2-C6", "P2", "Reward and exploration", DEFAULT_SEED, ("P2-reward-exploration",), judgement_rules=("ap_ranking", "intent_source", "arbitration")),
    Scenario("P3-L1", "P3", "Natural time flow", DEFAULT_SEED, ("P3-time-flow",), tick_policy={"kind": "natural", "minutes": 45}),
    Scenario("P3-L2", "P3", "Continuous work", DEFAULT_SEED, ("P3-workload", "P3-workload"), tick_policy={"kind": "workload", "minutes": 120}),
    Scenario("P3-L3", "P3", "Continuous rejection", DEFAULT_SEED, ("P3-rejection", "P3-rejection", "P3-rejection"), tick_policy={"kind": "social_decay", "decay": 0.02}),
    Scenario("P3-L4", "P3", "Resource pressure", DEFAULT_SEED, ("P3-resource-pressure",), tick_policy={"kind": "resource_pressure", "decay": 0.01}),
    Scenario("P3-L5", "P3", "Recovery event", DEFAULT_SEED, ("P3-resource-pressure", "P3-recovery"), tick_policy={"kind": "recovery", "decay": 0.04}),
    Scenario("P4-S1", "P4", "Positive feedback self evolution", DEFAULT_SEED, ("P4-positive-success", "P4-positive-success", "P4-positive-success", "P4-positive-success", "P4-positive-success"), judgement_rules=("threshold_delta", "memory_delta", "bounds")),
    Scenario("P4-S2", "P4", "Negative feedback self evolution", DEFAULT_SEED, ("P1-failure-feedback", "P1-failure-feedback", "P1-failure-feedback"), judgement_rules=("threshold_delta", "memory_delta", "bounds")),
    Scenario("P4-S3", "P4", "Rule constraint learning", DEFAULT_SEED, ("P1-pressure-rule", "P4-rule-learning", "P4-rule-learning"), judgement_rules=("threshold_delta", "preference_delta", "bounds")),
    Scenario("P4-S4", "P4", "Survival pressure adaptation", DEFAULT_SEED, ("P3-resource-pressure", "P2-survival-opportunity", "P3-recovery"), judgement_rules=("threshold_delta", "preference_delta", "bounds")),
    Scenario("P4-S5", "P4", "Relationship memory flow", ("seed_social_001",), ("P4-relation-memory", "P5-collab-request", "P4-relation-memory"), judgement_rules=("memory_delta", "relationship_delta", "bounds")),
    Scenario("P5-M1", "P5", "Broadcast high value demand", ("seed_bold_001", "seed_competitive_001", "seed_neutral_001"), ("P5-broadcast-demand",), judgement_rules=("seed_comparison", "relationship_delta", "behavior")),
    Scenario("P5-M2", "P5", "Competition for shared resource", ("seed_competitive_001", "seed_prudent_001", "seed_fragile_001"), ("P5-competition",), judgement_rules=("seed_comparison", "relationship_delta", "behavior")),
    Scenario("P5-M3", "P5", "Collaboration help request", ("seed_social_001", "seed_prudent_001", "seed_fragile_001"), ("P5-collab-request",), judgement_rules=("seed_comparison", "relationship_delta", "behavior")),
    Scenario("P5-M4", "P5", "Refusal followed by repair", ("seed_social_001", "seed_competitive_001"), ("P3-rejection", "P5-refusal-repair"), judgement_rules=("seed_comparison", "relationship_delta", "behavior")),
    Scenario("P5-M5", "P5", "Peer evaluation", ("seed_bold_001", "seed_prudent_001", "seed_social_001"), ("P5-evaluation",), judgement_rules=("seed_comparison", "relationship_delta", "behavior")),
    Scenario("P5-M6", "P5", "Seek help under survival pressure", ("seed_fragile_001", "seed_social_001", "seed_neutral_001"), ("P3-resource-pressure", "P5-collab-request"), judgement_rules=("seed_comparison", "relationship_delta", "behavior")),
)


def list_scenarios() -> list[Scenario]:
    return list(SCENARIOS)


def get_scenarios(phases: list[str]) -> list[Scenario]:
    wanted = set(phases)
    return [scenario for scenario in SCENARIOS if scenario.phase in wanted]
