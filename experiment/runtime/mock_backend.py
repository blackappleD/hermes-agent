from __future__ import annotations

import copy
from typing import Any

from experiment.collectors.mappings import ACTION_FIELDS, ARBITRATION_DECISIONS, LIFE_FIELDS, TENSION_FIELDS, ranked_action_potential
from experiment.collectors.redaction import audit_ref, redact_event
from experiment.collectors.transitions import build_transition_record
from experiment.config import ExperimentRunConfig
from experiment.events.library import load_events, validate_event_envelope
from experiment.scenarios.registry import Scenario
from experiment.seeds.library import load_seeds


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _canonical_action(action_field: str) -> tuple[str, str]:
    name = action_field.removeprefix("AP_")
    if name in {"accept_task", "submit", "review", "learn"}:
        return "productive", name
    if name in {"ask_clarify", "seek_help", "negotiate"}:
        return "coordination", name
    return "protective", name


class MockRuntimeBackend:
    """Deterministic backend that validates experiment shape without external services."""

    def __init__(self) -> None:
        self.seeds = load_seeds()
        self.events = load_events()
        self.states: dict[str, dict[str, Any]] = {}
        self.relationships: dict[str, dict[str, float]] = {}

    def run(self, config: ExperimentRunConfig, scenarios: list[Scenario]) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        invalid_events: list[dict[str, Any]] = []
        for scenario in scenarios:
            for seed_id in scenario.seed_ids:
                self._ensure_seed(seed_id)
            repeat = config.repeat if scenario.phase == "P1" else scenario.repeat
            for repeat_index in range(1, repeat + 1):
                for event_id in scenario.event_sequence:
                    event = self.events[event_id]
                    missing = validate_event_envelope(event)
                    if missing:
                        invalid_events.append({"event_id": event.get("event_id"), "missing": missing})
                        continue
                    for seed_id in scenario.seed_ids:
                        records.append(self._apply_event(config, scenario, seed_id, event, repeat_index))
        return {
            "status": "completed",
            "mode": "mock",
            "transitions": records,
            "invalid_events": invalid_events,
            "capabilities": {"mock": True, "runtime": False, "blocked_reasons": []},
        }

    def _ensure_seed(self, seed_id: str) -> None:
        if seed_id in self.states:
            return
        seed = self.seeds[seed_id]
        life_state = {field: float(seed["initial_life_state"][field]) for field in LIFE_FIELDS}
        self.states[seed_id] = {
            "life_state": life_state,
            "tension_field": {field: 0.0 for field in TENSION_FIELDS},
            "action_potential": {field: 0.0 for field in ACTION_FIELDS},
            "self_prompt": {
                "fields": {"role": seed["role"], "seed_id": seed_id},
                "summary": f"{seed['name']} baseline prompt",
                "reason": "seed_initialization",
                "evidence_refs": [],
            },
            "open_intent": {
                "action_family": "observation",
                "action_type": "review",
                "why_now": "initial_state",
                "open_space": "baseline",
                "target_direction": "observe",
                "tools_needed": [],
                "success_condition": "state initialized",
                "stop_condition": "none",
                "score": 0.0,
                "source_tension": {},
                "source_action_potential": {},
            },
            "arbitration": {
                "decision": "report_only",
                "bo_bias": seed["bo_bias"],
                "yue_bias": seed["yue_bias"],
                "risk_level": "low",
                "primary_result": "observe",
                "constraint_reasons": [],
                "approval_required": False,
                "permission_refs": [],
                "evidence_refs": [],
            },
            "memory_evolution": {"threshold_delta": {}, "preference_delta": {}, "memory_weight_delta": {}, "relationship_delta": {}},
        }
        self.relationships[seed_id] = {}

    def _apply_event(
        self,
        config: ExperimentRunConfig,
        scenario: Scenario,
        seed_id: str,
        event: dict[str, Any],
        repeat_index: int,
    ) -> dict[str, Any]:
        before_state = copy.deepcopy(self.states[seed_id])
        seed = self.seeds[seed_id]
        effects = event.get("expected_effects", {})
        after_state = copy.deepcopy(before_state)
        self._apply_numeric_effects(after_state, seed, effects, scenario.phase)
        self._apply_evolution(after_state, seed_id, event, scenario)
        self._apply_intent_and_arbitration(after_state, seed, event)
        evidence_refs = [f"mock_receipt:{config.run_id}:{seed_id}:{event['event_id']}:{repeat_index}", audit_ref(event)]
        after_state["self_prompt"]["evidence_refs"] = evidence_refs
        after_state["arbitration"]["evidence_refs"] = evidence_refs
        raw_transitions = self._raw_chain(event, before_state, after_state, evidence_refs)
        tick_state = self._tick(after_state, scenario.tick_policy)
        self.states[seed_id] = copy.deepcopy(tick_state)
        action_field = ranked_action_potential(after_state["action_potential"])[0]["action"]
        family, action_type = _canonical_action(str(action_field))
        judgement = self._judge(before_state, after_state, scenario, event)
        return build_transition_record(
            run_id=config.run_id,
            phase=scenario.phase,
            scenario_id=scenario.scenario_id,
            seed_id=seed_id,
            event=event,
            repeat_index=repeat_index,
            before_state=before_state,
            after_state=after_state,
            tick_state=tick_state,
            raw_transitions=raw_transitions,
            actual_action={"action_family": family, "action_type": action_type, "status": "planned"},
            stop_reason="completed",
            judgement=judgement,
            evidence_refs=evidence_refs,
        )

    def _apply_numeric_effects(self, state: dict[str, Any], seed: dict[str, Any], effects: dict[str, Any], phase: str) -> None:
        life_effects = effects.get("life", {})
        for field in LIFE_FIELDS:
            state["life_state"][field] = _clamp(float(state["life_state"].get(field, 0.0)) + float(life_effects.get(field, 0.0)))
        tension_effects = effects.get("tension", {})
        for field in TENSION_FIELDS:
            weight = float(seed["tension_weights"].get(field, 1.0))
            state["tension_field"][field] = _clamp(float(state["tension_field"].get(field, 0.0)) + float(tension_effects.get(field, 0.0)) * weight)
        action_effects = effects.get("ap", {})
        bo_bias = float(seed["bo_bias"])
        yue_bias = float(seed["yue_bias"])
        for field in ACTION_FIELDS:
            adjustment = float(action_effects.get(field, 0.0))
            if field in {"AP_accept_task", "AP_submit", "AP_learn"}:
                adjustment *= 0.85 + bo_bias * 0.3
            if field in {"AP_ask_clarify", "AP_review", "AP_refuse"}:
                adjustment *= 0.85 + yue_bias * 0.3
            if phase == "P5" and field in {"AP_negotiate", "AP_seek_help"}:
                adjustment += 0.02
            state["action_potential"][field] = _clamp(float(state["action_potential"].get(field, 0.0)) + adjustment)

    def _apply_evolution(self, state: dict[str, Any], seed_id: str, event: dict[str, Any], scenario: Scenario) -> None:
        memory = copy.deepcopy(state.get("memory_evolution", {}))
        threshold_delta = dict(memory.get("threshold_delta", {}))
        preference_delta = dict(memory.get("preference_delta", {}))
        memory_delta = dict(memory.get("memory_weight_delta", {}))
        relationship_delta = dict(memory.get("relationship_delta", {}))
        event_type = event["event_type"]
        if scenario.phase == "P4":
            if "succeeded" in event_type:
                threshold_delta["accept_task"] = round(threshold_delta.get("accept_task", 0.0) - 0.01, 4)
                memory_delta["success_pattern"] = round(memory_delta.get("success_pattern", 0.0) + 0.03, 4)
            if "failed" in event_type or "constraint" in event_type:
                threshold_delta["ask_clarify"] = round(threshold_delta.get("ask_clarify", 0.0) - 0.01, 4)
                preference_delta["self_check"] = round(preference_delta.get("self_check", 0.0) + 0.03, 4)
            if "resource" in event_type:
                threshold_delta["seek_help"] = round(threshold_delta.get("seek_help", 0.0) - 0.015, 4)
            if "relationship" in event_type or "help_requested" in event_type:
                relationship_delta["peer_trust"] = round(relationship_delta.get("peer_trust", 0.0) + 0.04, 4)
        if scenario.phase == "P5":
            relation_key = scenario.scenario_id
            change = 0.02
            if "competition" in event_type:
                change = -0.015
            if "help_requested" in event_type or "refusal_repair" in event_type:
                change = 0.035
            self.relationships[seed_id][relation_key] = round(self.relationships[seed_id].get(relation_key, 0.0) + change, 4)
            relationship_delta[relation_key] = change
        state["memory_evolution"] = {
            "threshold_delta": threshold_delta,
            "preference_delta": preference_delta,
            "memory_weight_delta": memory_delta,
            "relationship_delta": relationship_delta,
        }

    def _apply_intent_and_arbitration(self, state: dict[str, Any], seed: dict[str, Any], event: dict[str, Any]) -> None:
        ranking = ranked_action_potential(state["action_potential"])
        top = str(ranking[0]["action"])
        family, action_type = _canonical_action(top)
        top_tension = max(TENSION_FIELDS, key=lambda field: float(state["tension_field"].get(field, 0.0)))
        risk = float(state["tension_field"].get("T_risk", 0.0)) + float(state["tension_field"].get("T_governance", 0.0)) * 0.5
        decision = "auto_execute"
        risk_level = "low"
        if risk > 0.75 or top == "AP_refuse":
            decision = "reject" if top == "AP_refuse" else "require_approval"
            risk_level = "high"
        elif risk > 0.42 or top in {"AP_review", "AP_ask_clarify"}:
            decision = "require_approval" if top == "AP_review" else "report_only"
            risk_level = "medium"
        elif top in {"AP_submit", "AP_accept_task"}:
            decision = "sandbox_execute"
        assert decision in ARBITRATION_DECISIONS
        state["self_prompt"] = {
            "fields": {"event_type": event["event_type"], "top_tension": top_tension, "seed_role": seed["role"]},
            "summary": f"{event['event_type']} indicates {top_tension}; prefer {action_type}.",
            "reason": "deterministic_mock_projection",
            "evidence_refs": [],
        }
        state["open_intent"] = {
            "action_family": family,
            "action_type": action_type,
            "why_now": f"highest action potential is {top}",
            "open_space": "mock_runtime",
            "target_direction": top_tension,
            "tools_needed": ["experiment.mock"],
            "success_condition": "transition captured with bounded state",
            "stop_condition": "judgement fail or approval required",
            "score": ranking[0]["score"],
            "ranking": ranking,
            "source_tension": {top_tension: state["tension_field"][top_tension]},
            "source_action_potential": {top: state["action_potential"][top]},
        }
        state["arbitration"] = {
            "decision": decision,
            "bo_bias": seed["bo_bias"],
            "yue_bias": seed["yue_bias"],
            "risk_level": risk_level,
            "primary_result": action_type,
            "constraint_reasons": ["risk_or_governance"] if risk_level != "low" else [],
            "approval_required": decision == "require_approval",
            "permission_refs": [f"mock_permission:{decision}"],
            "evidence_refs": [],
        }

    def _raw_chain(self, event: dict[str, Any], before: dict[str, Any], after: dict[str, Any], evidence_refs: list[str]) -> list[dict[str, Any]]:
        redacted_event = redact_event(event)
        return [
            {"stage": "event", "data": redacted_event},
            {"stage": "context/signals", "data": {"tags": event.get("tags", []), "payload_summary": redacted_event["payload"]}},
            {"stage": "life_state", "before": before["life_state"], "after": after["life_state"]},
            {"stage": "tension_field", "before": before["tension_field"], "after": after["tension_field"]},
            {"stage": "action_potential", "before": before["action_potential"], "after": after["action_potential"], "ranking": ranked_action_potential(after["action_potential"])},
            {"stage": "self_prompt", "data": after["self_prompt"]},
            {"stage": "open_intent", "data": after["open_intent"]},
            {"stage": "arbitration", "data": after["arbitration"]},
            {"stage": "action/evidence", "data": {"evidence_refs": evidence_refs, "receipt_status": "mock_recorded"}},
        ]

    def _tick(self, state: dict[str, Any], tick_policy: dict[str, Any]) -> dict[str, Any]:
        ticked = copy.deepcopy(state)
        decay = float(tick_policy.get("decay", 0.02))
        ticked["life_state"]["stress"] = _clamp(float(ticked["life_state"].get("stress", 0.0)) - decay)
        ticked["life_state"]["fatigue"] = _clamp(float(ticked["life_state"].get("fatigue", 0.0)) - decay / 2)
        for field in TENSION_FIELDS:
            ticked["tension_field"][field] = _clamp(float(ticked["tension_field"].get(field, 0.0)) * (1.0 - decay))
        for field in ACTION_FIELDS:
            ticked["action_potential"][field] = _clamp(float(ticked["action_potential"].get(field, 0.0)) * (1.0 - decay))
        ticked["tick_policy"] = tick_policy or {"kind": "default_decay", "decay": decay}
        return ticked

    def _judge(self, before: dict[str, Any], after: dict[str, Any], scenario: Scenario, event: dict[str, Any]) -> dict[str, Any]:
        out_of_bounds = []
        for group in ("life_state", "tension_field", "action_potential"):
            for field, value in after[group].items():
                if not 0.0 <= float(value) <= 1.0:
                    out_of_bounds.append(f"{group}.{field}")
        expected = event.get("expected_effects", {})
        observed = []
        for group, key in (("life", "life_state"), ("tension", "tension_field"), ("ap", "action_potential")):
            for field, expected_delta in expected.get(group, {}).items():
                actual = float(after[key].get(field, 0.0)) - float(before[key].get(field, 0.0))
                direction_ok = expected_delta == 0 or actual == 0 or (expected_delta > 0 and actual > 0) or (expected_delta < 0 and actual < 0)
                observed.append({"field": field, "expected_direction": "up" if expected_delta > 0 else "down", "actual_delta": round(actual, 4), "direction_ok": direction_ok})
        status = "pass"
        reasons: list[str] = []
        if out_of_bounds:
            status = "fail"
            reasons.append("state_out_of_bounds")
        elif any(not item["direction_ok"] for item in observed):
            status = "warn"
            reasons.append("direction_mismatch")
        return {"status": status, "rules": list(scenario.judgement_rules), "observed": observed, "reasons": reasons}
