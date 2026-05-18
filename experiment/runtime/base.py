from __future__ import annotations

from typing import Any, Protocol

from experiment.config import ExperimentRunConfig
from experiment.scenarios.registry import Scenario


class RuntimeBackend(Protocol):
    def run(self, config: ExperimentRunConfig, scenarios: list[Scenario]) -> dict[str, Any]:
        """Return run data with transition records or blocked diagnostics."""
