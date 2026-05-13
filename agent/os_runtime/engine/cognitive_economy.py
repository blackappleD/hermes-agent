"""Cognitive budget recommendation for os_runtime action potential."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Callable

from agent.linz_world.compute import invoke_compute
from agent.os_runtime.domain import (
    ActionPotential,
    AgentContextView,
    CognitiveEconomyPath,
    CognitiveEconomyRecommendation,
    LifeState,
    RecommendedDepth,
    SignalSet,
    Tension,
    TensionSet,
    TensionType,
    WorldComputeEligibility,
)


ComputeGateway = Callable[..., Any]


class CognitiveEconomyController:
    """Return model/budget path recommendations without switching models."""

    rule_version = "cognitive_economy.v1"

    def __init__(self, *, config: dict[str, Any] | None = None, compute_gateway: ComputeGateway | None = None) -> None:
        self.config = {
            "allow_world_compute": False,
            "world_compute_score_at": 0.68,
            "world_compute_learning_at": 0.36,
            "main_model_score_at": 0.40,
            "auxiliary_small_score_at": 0.22,
            "high_reasoning_score_at": 0.62,
            **(config or {}),
        }
        self.compute_gateway = compute_gateway or invoke_compute

    def recommend(
        self,
        *,
        action_potential: ActionPotential,
        signal_set: SignalSet | None = None,
        life_state: LifeState | None = None,
        tension_set: TensionSet | None = None,
        world_task: str = "os_runtime_cognitive_economy",
        world_input: dict[str, Any] | None = None,
        repository: Any = None,
    ) -> CognitiveEconomyRecommendation:
        signals = signal_set or SignalSet()
        life = life_state or LifeState(restraint=0.2, life_cycle="active")
        tensions = tension_set or TensionSet()
        world_input = dict(world_input or {})
        evidence = _base_evidence(action_potential, signals, tensions, life)

        explicit_credential = _has_explicit_credential(world_input)
        wants_world = self._should_try_world_compute(action_potential, signals, tensions, explicit_credential)
        eligibility = self._world_compute_eligibility(
            signals.agent_context,
            explicit_credential=explicit_credential,
        )
        receipt_summary: dict[str, Any] = {}
        downgrade_reason = ""

        if wants_world:
            if eligibility.eligible:
                receipt = self._invoke_world_compute(world_task, _safe_world_input(world_input), repository)
                receipt_summary = _receipt_summary(receipt)
                eligibility.receipt_status = str(receipt_summary.get("status") or "")
                if receipt_summary.get("status") == "published":
                    return self._recommendation(
                        CognitiveEconomyPath.WORLD_COMPUTE,
                        "High-value uncertain action is eligible for governed world compute.",
                        "external_governed",
                        evidence + ["world_compute:eligible", "receipt:published"],
                        eligibility,
                        action_potential,
                        receipt_summary=receipt_summary,
                    )
                downgrade_reason = f"world_compute_receipt_{receipt_summary.get('status') or 'missing'}"
                evidence.append(f"receipt:{receipt_summary.get('status') or 'missing'}")
            else:
                downgrade_reason = eligibility.reason
                evidence.append(f"world_compute:ineligible:{eligibility.reason}")
        elif explicit_credential:
            downgrade_reason = "explicit_credentials_rejected"
            evidence.append("world_compute:ineligible:explicit_credentials_rejected")

        path, reason, budget = self._local_path(action_potential, signals, tensions, life)
        if downgrade_reason and path == CognitiveEconomyPath.MAIN_MODEL and _high_uncertainty(signals, tensions, action_potential):
            path = CognitiveEconomyPath.HIGH_REASONING
            budget = "expanded_reasoning"
            reason = "World compute is unavailable, so keep the work local with higher reasoning."
        return self._recommendation(
            path,
            reason,
            budget,
            evidence,
            eligibility,
            action_potential,
            downgrade_reason=downgrade_reason,
            receipt_summary=receipt_summary,
        )

    def _should_try_world_compute(
        self,
        action_potential: ActionPotential,
        signals: SignalSet,
        tensions: TensionSet,
        explicit_credential: bool,
    ) -> bool:
        return (
            bool(self.config.get("allow_world_compute"))
            and not explicit_credential
            and action_potential.risk_cost < 0.42
            and action_potential.overall_score >= float(self.config["world_compute_score_at"])
            and _high_uncertainty(signals, tensions, action_potential)
        )

    def _world_compute_eligibility(
        self,
        agent_context: AgentContextView | None,
        *,
        explicit_credential: bool,
    ) -> WorldComputeEligibility:
        if explicit_credential:
            return WorldComputeEligibility(
                reason="explicit_credentials_rejected",
                config_enabled=bool(self.config.get("allow_world_compute")),
            )
        if not self.config.get("allow_world_compute"):
            return WorldComputeEligibility(reason="config_disabled", config_enabled=False)
        if agent_context is None:
            return WorldComputeEligibility(reason="missing_agent_context", config_enabled=True)

        identity = agent_context.world_identity
        metadata = dict(agent_context.metadata)
        if identity is not None:
            metadata = {**identity.metadata, **metadata}
        login_state = str(metadata.get("login_state") or "unknown")
        token_ref = str(metadata.get("token_ref") or metadata.get("access_token_ref") or "")
        token_secret_available = bool(metadata.get("token_secret_available"))
        authorization_state = str(
            metadata.get("authorization_state")
            or (identity.authorization_state if identity else "")
            or "unknown"
        )
        memory_summary_available = bool(
            agent_context.memory_summary
            or metadata.get("memory_summary_available")
            or (identity.memory_summary_available if identity else False)
        )

        base = {
            "login_state": login_state,
            "token_ref_present": bool(token_ref),
            "token_secret_available": token_secret_available,
            "memory_summary_available": memory_summary_available,
            "authorization_state": authorization_state,
            "config_enabled": True,
        }
        if login_state != "logged_in":
            return WorldComputeEligibility(reason="not_logged_in", **base)
        if not token_ref:
            return WorldComputeEligibility(reason="missing_token_ref", **base)
        if not token_secret_available:
            return WorldComputeEligibility(reason="token_secret_unavailable", **base)
        if not memory_summary_available:
            return WorldComputeEligibility(reason="missing_soul_memory_summary", **base)
        if authorization_state not in {"current", "allowed"}:
            return WorldComputeEligibility(reason="authorization_not_current", **base)
        return WorldComputeEligibility(eligible=True, reason="eligible", **base)

    def _invoke_world_compute(self, task: str, input_data: dict[str, Any], repository: Any) -> Any:
        try:
            return self.compute_gateway(task, input_data=input_data, repository=repository)
        except TypeError:
            return self.compute_gateway(task, input_data)

    def _local_path(
        self,
        action_potential: ActionPotential,
        signals: SignalSet,
        tensions: TensionSet,
        life: LifeState,
    ) -> tuple[CognitiveEconomyPath, str, str]:
        score = action_potential.overall_score
        risk = action_potential.risk_cost
        depth = _depth_value(action_potential)
        if score < float(self.config["auxiliary_small_score_at"]) or depth in {RecommendedDepth.NONE.value, RecommendedDepth.REPORT.value}:
            return CognitiveEconomyPath.RULE_PATH, "Low score or report-only depth does not justify model budget.", "minimal"
        if risk >= 0.62 or life.restraint >= 0.80:
            return CognitiveEconomyPath.RULE_PATH, "Risk or restraint keeps the recommendation on a deterministic path.", "minimal"
        if score < float(self.config["main_model_score_at"]):
            return CognitiveEconomyPath.AUXILIARY_SMALL, "Low-risk lightweight work fits a small auxiliary path.", "small"
        if score >= float(self.config["high_reasoning_score_at"]) and _high_uncertainty(signals, tensions, action_potential):
            return CognitiveEconomyPath.HIGH_REASONING, "High uncertainty merits local high reasoning.", "expanded_reasoning"
        return CognitiveEconomyPath.MAIN_MODEL, "Mainline answer needs the primary model context but no external compute.", "standard"

    def _recommendation(
        self,
        path: CognitiveEconomyPath,
        reason: str,
        budget_hint: str,
        evidence: list[str],
        eligibility: WorldComputeEligibility,
        action_potential: ActionPotential,
        *,
        downgrade_reason: str = "",
        receipt_summary: dict[str, Any] | None = None,
    ) -> CognitiveEconomyRecommendation:
        return CognitiveEconomyRecommendation(
            selected_path=path,
            reason=reason,
            budget_hint=budget_hint,
            downgrade_reason=downgrade_reason,
            receipt_summary=receipt_summary or {},
            evidence=_dedupe(evidence + ["config:cognitive_economy:path_rules"]),
            metadata={
                "rule_version": self.rule_version,
                "score_snapshot": {
                    "value_potential": action_potential.value_potential,
                    "mutual_benefit_potential": action_potential.mutual_benefit_potential,
                    "learning_potential": action_potential.learning_potential,
                    "risk_cost": action_potential.risk_cost,
                    "overall_score": action_potential.overall_score,
                    "recommended_depth": _depth_value(action_potential),
                },
                "world_compute_eligibility": eligibility.to_dict(),
                "allowed_paths": [item.value for item in CognitiveEconomyPath],
                "config": dict(self.config),
            },
        )


def _base_evidence(
    action_potential: ActionPotential,
    signals: SignalSet,
    tensions: TensionSet,
    life: LifeState,
) -> list[str]:
    evidence = [
        "action_potential:overall_score",
        "action_potential:risk_cost",
        "life_state:restraint",
    ]
    score_evidence = action_potential.metadata.get("score_evidence")
    if isinstance(score_evidence, dict):
        for values in score_evidence.values():
            if isinstance(values, list):
                evidence.extend(str(item) for item in values)
    if signals.task_context and signals.task_context.active_goal:
        evidence.append("task_context:active_goal")
    for tension in _active_tensions(tensions):
        evidence.append(f"tension:{tension.tension_type.value}:{tension.tension_id}")
    if life.fatigue:
        evidence.append("life_state:fatigue")
    return _dedupe(evidence)


def _high_uncertainty(signals: SignalSet, tensions: TensionSet, action_potential: ActionPotential) -> bool:
    if action_potential.learning_potential >= 0.36:
        return True
    for item in _signal_items(signals):
        if _matches(item, ("uncertain", "uncertainty", "unknown", "memory", "new_task", "explore")):
            return True
    return any(tension.tension_type in {TensionType.UNCERTAINTY, TensionType.MEMORY_RESONANCE} for tension in _active_tensions(tensions))


def _signal_items(signal_set: SignalSet) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group, value in signal_set.signals.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            normalized = dict(item) if isinstance(item, dict) else {"value": item}
            normalized["_group"] = str(group)
            items.append(normalized)
    return items


def _active_tensions(tension_set: TensionSet) -> list[Tension]:
    return [
        tension
        for tension in [*tension_set.core_tensions, *tension_set.dynamic_tensions]
        if tension.activation > 0.0 or str(tension.metadata.get("status") or "").lower() == "active"
    ]


def _matches(item: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("_group", "code", "kind", "type", "level", "status", "reason", "summary", "value")
    ).lower()
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        haystack = f"{haystack} {' '.join(str(value) for value in metadata.values()).lower()}"
    return any(needle in haystack for needle in needles)


def _receipt_summary(receipt: Any) -> dict[str, Any]:
    if receipt is None:
        return {"status": "missing"}
    if is_dataclass(receipt):
        data = asdict(receipt)
    elif hasattr(receipt, "to_dict"):
        data = receipt.to_dict()
    elif isinstance(receipt, dict):
        data = dict(receipt)
    else:
        data = {
            "request_id": getattr(receipt, "request_id", ""),
            "status": getattr(receipt, "status", ""),
            "message": getattr(receipt, "message", ""),
        }
    return {
        "request_id": str(data.get("request_id") or data.get("receipt_id") or ""),
        "status": _enum_value(data.get("status") or ""),
        "provider_summary": str(data.get("provider_summary") or ""),
        "message": str(data.get("message") or ""),
    }


def _has_explicit_credential(input_data: dict[str, Any]) -> bool:
    return any(str(key).lower() in {"token", "api_key", "secret"} for key in input_data)


def _safe_world_input(input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in input_data.items()
        if str(key).lower() not in {"token", "api_key", "secret"}
    }


def _depth_value(action_potential: ActionPotential) -> str:
    depth = action_potential.recommended_depth
    if isinstance(depth, RecommendedDepth):
        return depth.value
    return str(depth or action_potential.metadata.get("recommended_depth") or "")


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
