from __future__ import annotations

from typing import Any

from experiment.collectors.mappings import ACTION_FIELDS, LIFE_FIELDS, TENSION_FIELDS
from experiment.config import ExperimentRunConfig
from experiment.runtime.os_runtime_backend import RuntimeCapabilityBackend
from experiment.scenarios.registry import get_scenarios


class FakeRuntimeClient:
    def capability_check(self, config: ExperimentRunConfig) -> dict[str, Any]:
        return {
            "login": True,
            "permissions": True,
            "query": True,
            "evidence_repository": True,
            "adapter": "fake-readonly",
            "blocked_reasons": [],
        }

    def capture_transition(
        self,
        *,
        config: ExperimentRunConfig,
        scenario,
        seed_id: str,
        event: dict[str, Any],
        repeat_index: int,
    ) -> dict[str, Any]:
        before = _snapshot(event, 0.1)
        after = _snapshot(event, 0.2)
        evidence_refs = [f"runtime_receipt:{config.run_id}:{seed_id}:{event['event_id']}:{repeat_index}"]
        after["self_prompt"]["evidence_refs"] = evidence_refs
        after["arbitration"]["evidence_refs"] = evidence_refs
        return {
            "before_state": before,
            "after_state": after,
            "tick_state": _snapshot(event, 0.18),
            "raw_transitions": [
                {"stage": "event", "data": {"event_id": event["event_id"], "event_type": event["event_type"], "subject": event["subject"]}},
                {"stage": "context/signals", "data": {"adapter": "fake-readonly", "profile": config.profile}},
                {"stage": "life_state", "before": before["life_state"], "after": after["life_state"]},
                {"stage": "tension_field", "before": before["tension_field"], "after": after["tension_field"]},
                {"stage": "action_potential", "before": before["action_potential"], "after": after["action_potential"]},
                {"stage": "self_prompt", "data": after["self_prompt"]},
                {"stage": "open_intent", "data": after["open_intent"]},
                {"stage": "arbitration", "data": after["arbitration"]},
                {"stage": "action/evidence", "data": {"evidence_refs": evidence_refs}},
            ],
            "actual_action": {"action_family": "productive", "action_type": "accept_task", "status": "adapter_observed"},
            "stop_reason": "completed",
            "judgement": {"status": "pass", "rules": list(scenario.judgement_rules), "reasons": []},
            "evidence_refs": evidence_refs,
        }


class BlockedRuntimeClient(FakeRuntimeClient):
    def capability_check(self, config: ExperimentRunConfig) -> dict[str, Any]:
        return {
            "login": True,
            "permissions": False,
            "query": True,
            "evidence_repository": True,
            "adapter": "fake-readonly",
            "blocked_reasons": ["permission probe denied"],
        }


def test_runtime_backend_success_path_uses_adapter_backed_transitions() -> None:
    config = ExperimentRunConfig(phase="P0", mode="runtime", profile="test-profile", run_id="runtime-success")
    result = RuntimeCapabilityBackend(client=FakeRuntimeClient()).run(config, get_scenarios(["P0"]))
    assert result["status"] == "completed"
    assert result["capabilities"]["runtime"] is True
    assert result["capabilities"]["fail_closed"] is False
    assert len(result["transitions"]) == 3
    record = result["transitions"][0]
    assert record["event"]["subject"]
    assert record["actual_action"]["status"] == "adapter_observed"
    assert record["evidence_refs"][0].startswith("runtime_receipt:")
    assert record["after_state"]["open_intent"]["source_action_potential"]


def test_runtime_backend_blocks_when_client_probe_fails() -> None:
    config = ExperimentRunConfig(phase="P0", mode="runtime", profile="test-profile", run_id="runtime-blocked")
    result = RuntimeCapabilityBackend(client=BlockedRuntimeClient()).run(config, get_scenarios(["P0"]))
    assert result["status"] == "blocked"
    assert result["transitions"] == []
    assert result["capabilities"]["runtime"] is False
    assert "runtime capability unavailable: permissions" in result["blocked_reason"]
    assert "permission probe denied" in result["blocked_reason"]


def _snapshot(event: dict[str, Any], value: float) -> dict[str, Any]:
    return {
        "life_state": {field: value for field in LIFE_FIELDS},
        "tension_field": {field: value for field in TENSION_FIELDS},
        "action_potential": {field: value for field in ACTION_FIELDS},
        "self_prompt": {
            "fields": {"event_type": event["event_type"]},
            "summary": "adapter-backed runtime snapshot",
            "reason": "fake_runtime_probe",
            "evidence_refs": [],
        },
        "open_intent": {
            "action_family": "productive",
            "action_type": "accept_task",
            "why_now": "adapter reported accept_task",
            "open_space": "runtime_adapter",
            "target_direction": "T_value",
            "tools_needed": ["runtime.query"],
            "success_condition": "transition captured",
            "stop_condition": "adapter stop",
            "score": value,
            "source_tension": {"T_value": value},
            "source_action_potential": {"AP_accept_task": value},
        },
        "arbitration": {
            "decision": "sandbox_execute",
            "bo_bias": 0.5,
            "yue_bias": 0.5,
            "risk_level": "low",
            "primary_result": "accept_task",
            "constraint_reasons": [],
            "approval_required": False,
            "permission_refs": ["runtime_permission:test"],
            "evidence_refs": [],
        },
        "memory_evolution": {"threshold_delta": {}, "preference_delta": {}, "memory_weight_delta": {}, "relationship_delta": {}},
    }
