from __future__ import annotations

from typing import Any

from .mappings import ACTION_FIELDS, LIFE_FIELDS, TENSION_FIELDS, delta, ranked_action_potential
from .redaction import redact_event


def build_transition_record(
    *,
    run_id: str,
    phase: str,
    scenario_id: str,
    seed_id: str,
    event: dict[str, Any],
    repeat_index: int,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    tick_state: dict[str, Any] | None,
    raw_transitions: list[dict[str, Any]],
    actual_action: dict[str, Any],
    stop_reason: str,
    judgement: dict[str, Any],
    evidence_refs: list[str],
) -> dict[str, Any]:
    life_delta = delta(before_state["life_state"], after_state["life_state"], LIFE_FIELDS)
    tension_delta = delta(before_state["tension_field"], after_state["tension_field"], TENSION_FIELDS)
    action_delta = delta(before_state["action_potential"], after_state["action_potential"], ACTION_FIELDS)
    after_state = dict(after_state)
    after_state["action_potential_ranking"] = ranked_action_potential(after_state["action_potential"])
    if tick_state is not None:
        tick_state = dict(tick_state)
        tick_state["action_potential_ranking"] = ranked_action_potential(tick_state["action_potential"])
    return {
        "run_id": run_id,
        "phase": phase,
        "scenario_id": scenario_id,
        "seed_id": seed_id,
        "event": redact_event(event),
        "repeat_index": repeat_index,
        "before_state": before_state,
        "raw_transitions": raw_transitions,
        "after_state": after_state,
        "tick_state": tick_state,
        "delta_summary": {
            "life_state": life_delta,
            "tension_field": tension_delta,
            "action_potential": action_delta,
            "memory_evolution": after_state.get("memory_evolution", {}),
        },
        "actual_action": actual_action,
        "stop_reason": stop_reason,
        "judgement": judgement,
        "evidence_refs": evidence_refs,
    }
