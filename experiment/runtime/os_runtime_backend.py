from __future__ import annotations

import importlib.util
from typing import Any, Protocol

from experiment.collectors.transitions import build_transition_record
from experiment.config import ExperimentRunConfig
from experiment.events.library import load_events, validate_event_envelope
from experiment.scenarios.registry import Scenario


class RuntimeExperimentClient(Protocol):
    """Thin boundary for a configured real runtime or a test stub."""

    def capability_check(self, config: ExperimentRunConfig) -> dict[str, Any]:
        """Return login/permission/query/evidence capability diagnostics."""

    def capture_transition(
        self,
        *,
        config: ExperimentRunConfig,
        scenario: Scenario,
        seed_id: str,
        event: dict[str, Any],
        repeat_index: int,
    ) -> dict[str, Any]:
        """Inject/read one formal event envelope and return normalized snapshots."""


class UnconfiguredRuntimeClient:
    """Default client used by CLI runtime mode when no real adapter is wired."""

    def capability_check(self, config: ExperimentRunConfig) -> dict[str, Any]:
        return {
            "login": False,
            "permissions": False,
            "query": False,
            "evidence_repository": False,
            "adapter": "unconfigured",
            "blocked_reasons": ["no runtime experiment client configured"],
        }

    def capture_transition(
        self,
        *,
        config: ExperimentRunConfig,
        scenario: Scenario,
        seed_id: str,
        event: dict[str, Any],
        repeat_index: int,
    ) -> dict[str, Any]:
        raise RuntimeError("runtime experiment client is not configured")


class RuntimeCapabilityBackend:
    """Runtime backend with fail-closed capability checks and injectable adapter."""

    REQUIRED_MODULES = (
        "agent.os_runtime.driver",
        "agent.os_runtime.evidence",
        "agent.os_runtime.domain",
        "agent.linz_world.event_bus",
    )
    REQUIRED_CLIENT_CAPABILITIES = ("login", "permissions", "query", "evidence_repository")

    def __init__(self, client: RuntimeExperimentClient | None = None) -> None:
        self.client = client or UnconfiguredRuntimeClient()
        self.events = load_events()

    def run(self, config: ExperimentRunConfig, scenarios: list[Scenario]) -> dict[str, Any]:
        diagnostics = self.capability_check(config)
        if diagnostics["blocked_reasons"]:
            return {
                "status": "blocked",
                "mode": "runtime",
                "transitions": [],
                "invalid_events": [],
                "capabilities": diagnostics,
                "blocked_reason": "; ".join(diagnostics["blocked_reasons"]),
                "scenario_count": len(scenarios),
            }
        records: list[dict[str, Any]] = []
        invalid_events: list[dict[str, Any]] = []
        for scenario in scenarios:
            repeat = config.repeat if scenario.phase == "P1" else scenario.repeat
            for repeat_index in range(1, repeat + 1):
                for event_id in scenario.event_sequence:
                    event = self.events[event_id]
                    missing = validate_event_envelope(event)
                    if missing:
                        invalid_events.append({"event_id": event.get("event_id"), "missing": missing})
                        continue
                    for seed_id in scenario.seed_ids:
                        adapter_result = self.client.capture_transition(
                            config=config,
                            scenario=scenario,
                            seed_id=seed_id,
                            event=event,
                            repeat_index=repeat_index,
                        )
                        records.append(self._build_record(config, scenario, seed_id, event, repeat_index, adapter_result))
        return {
            "status": "completed",
            "mode": "runtime",
            "transitions": records,
            "invalid_events": invalid_events,
            "capabilities": diagnostics,
            "scenario_count": len(scenarios),
        }

    def capability_check(self, config: ExperimentRunConfig) -> dict[str, Any]:
        blocked: list[str] = []
        modules = {module: importlib.util.find_spec(module) is not None for module in self.REQUIRED_MODULES}
        for module, available in modules.items():
            if not available:
                blocked.append(f"missing query module: {module}")
        if not config.profile:
            blocked.append("missing explicit --profile for runtime mode")
        client = self.client.capability_check(config)
        for capability in self.REQUIRED_CLIENT_CAPABILITIES:
            if client.get(capability) is not True:
                blocked.append(f"runtime capability unavailable: {capability}")
        blocked.extend(str(reason) for reason in client.get("blocked_reasons", []))
        return {
            "runtime": not blocked,
            "mock": False,
            "profile": config.profile,
            "modules": modules,
            "client": client,
            "blocked_reasons": blocked,
            "fail_closed": bool(blocked),
        }

    def _build_record(
        self,
        config: ExperimentRunConfig,
        scenario: Scenario,
        seed_id: str,
        event: dict[str, Any],
        repeat_index: int,
        adapter_result: dict[str, Any],
    ) -> dict[str, Any]:
        required = {"before_state", "after_state", "raw_transitions", "actual_action", "stop_reason", "judgement", "evidence_refs"}
        missing = sorted(required - set(adapter_result))
        if missing:
            raise ValueError(f"runtime adapter result missing fields: {', '.join(missing)}")
        return build_transition_record(
            run_id=config.run_id,
            phase=scenario.phase,
            scenario_id=scenario.scenario_id,
            seed_id=seed_id,
            event=event,
            repeat_index=repeat_index,
            before_state=adapter_result["before_state"],
            after_state=adapter_result["after_state"],
            tick_state=adapter_result.get("tick_state"),
            raw_transitions=adapter_result["raw_transitions"],
            actual_action=adapter_result["actual_action"],
            stop_reason=adapter_result["stop_reason"],
            judgement=adapter_result["judgement"],
            evidence_refs=adapter_result["evidence_refs"],
        )
