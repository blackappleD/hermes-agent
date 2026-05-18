from __future__ import annotations

import importlib.util
from typing import Any

from experiment.config import ExperimentRunConfig
from experiment.scenarios.registry import Scenario


class RuntimeCapabilityBackend:
    """Fail-closed runtime backend until a configured Linz runtime is available."""

    REQUIRED_MODULES = (
        "agent.os_runtime.driver",
        "agent.os_runtime.evidence",
        "agent.os_runtime.domain",
        "agent.linz_world.event_bus",
    )

    def run(self, config: ExperimentRunConfig, scenarios: list[Scenario]) -> dict[str, Any]:
        diagnostics = self.capability_check(config)
        return {
            "status": "blocked",
            "mode": "runtime",
            "transitions": [],
            "invalid_events": [],
            "capabilities": diagnostics,
            "blocked_reason": "; ".join(diagnostics["blocked_reasons"]),
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
        blocked.extend([
            "linz world login not verified by experiment backend",
            "runtime permissions not verified by experiment backend",
            "evidence repository capability not verified by experiment backend",
        ])
        return {
            "runtime": False,
            "mock": False,
            "profile": config.profile,
            "modules": modules,
            "blocked_reasons": blocked,
            "fail_closed": True,
        }
