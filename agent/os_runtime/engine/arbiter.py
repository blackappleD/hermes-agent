"""BoYue arbitration for pre-execution os_runtime intents."""

from __future__ import annotations

from typing import Any

from agent.os_runtime.domain import (
    ActionPotential,
    ArbitrationDecision,
    ArbitrationResult,
    OpenActionFamily,
    OpenIntent,
    RiskLevel,
    SelfPrompt,
)


EXECUTABLE_DECISIONS = {
    ArbitrationDecision.AUTO_EXECUTE,
    ArbitrationDecision.SANDBOX_EXECUTE,
}


class BoYueArbiter:
    """Score intent value, restraint, and harmony before any side effect."""

    rule_version = "bo_yue_arbiter.v1"

    def arbitrate(
        self,
        *,
        intent: OpenIntent,
        self_prompt: SelfPrompt | None = None,
        action_potential: ActionPotential | None = None,
        available_tools: list[str] | None = None,
        policy_preflight: dict[str, Any] | None = None,
        event_catalog_preflight: dict[str, Any] | None = None,
        authorization_summary: dict[str, Any] | None = None,
        approval_granted: bool = False,
        allow_auto_execute: bool = False,
    ) -> ArbitrationResult:
        potential = action_potential or ActionPotential(risk_cost=_risk_cost(intent.risk_level))
        tools = list(available_tools or [])
        policy = dict(policy_preflight or {})
        catalog = dict(event_catalog_preflight or {})
        authorization = dict(authorization_summary or {})
        scores = _scores(intent, potential, policy, catalog, authorization)
        decision, approvals, reasons = self._decision(
            intent=intent,
            potential=potential,
            available_tools=tools,
            policy=policy,
            catalog=catalog,
            authorization=authorization,
            approval_granted=approval_granted,
            allow_auto_execute=allow_auto_execute,
        )
        risk_level = _combined_risk(intent.risk_level, potential.risk_cost)
        metadata = {
            "rule_version": self.rule_version,
            "policy_preflight": policy,
            "event_catalog_preflight": catalog,
            "authorization_summary": authorization,
            "self_prompt_id": self_prompt.prompt_id if self_prompt else "",
            "legacy_decision_aliases": {
                "allow_reply": decision == ArbitrationDecision.REPORT_ONLY,
                "allow_draft": decision in {ArbitrationDecision.REPORT_ONLY, ArbitrationDecision.SANDBOX_EXECUTE},
                "allow_sandbox": decision == ArbitrationDecision.SANDBOX_EXECUTE,
                "allow_tool": decision in EXECUTABLE_DECISIONS,
                "allow_world_publish": decision == ArbitrationDecision.AUTO_EXECUTE and _is_linz_publish(intent),
            },
        }
        return ArbitrationResult(
            intent_id=intent.intent_id,
            decision=decision,
            risk_level=risk_level,
            bo_score=scores["bo_score"],
            yue_score=scores["yue_score"],
            harmony_score=scores["harmony_score"],
            innovation_score=scores["innovation_score"],
            opportunity_score=scores["opportunity_score"],
            expansion_value=scores["expansion_value"],
            risk_score=scores["risk_score"],
            permission_level=scores["permission_level"],
            compliance_fit=scores["compliance_fit"],
            trust_impact=scores["trust_impact"],
            mutual_benefit_score=scores["mutual_benefit_score"],
            long_term_net_value=scores["long_term_net_value"],
            ecosystem_gain=scores["ecosystem_gain"],
            rationale="; ".join(reasons),
            required_approvals=approvals,
            metadata=metadata,
        )

    def _decision(
        self,
        *,
        intent: OpenIntent,
        potential: ActionPotential,
        available_tools: list[str],
        policy: dict[str, Any],
        catalog: dict[str, Any],
        authorization: dict[str, Any],
        approval_granted: bool,
        allow_auto_execute: bool,
    ) -> tuple[ArbitrationDecision, list[str], list[str]]:
        reasons: list[str] = []
        approvals: list[str] = []

        unknown_tools = [tool for tool in intent.tools_needed if tool not in available_tools]
        if unknown_tools:
            return (
                ArbitrationDecision.REJECT,
                [],
                [f"unknown tools are outside the allowed action space: {', '.join(unknown_tools)}"],
            )

        if _is_chat_reply(intent):
            if not _chat_reply_send_requested(intent):
                reasons.append("chat reply intent is draft-only until send is explicitly requested")
                return ArbitrationDecision.REPORT_ONLY, approvals, reasons
            return _chat_reply_send_decision(policy, catalog, authorization, approval_granted)

        if _is_linz_publish(intent):
            return _linz_publish_decision(policy, catalog, authorization, approval_granted)

        if _policy_denied(policy):
            return ArbitrationDecision.REJECT, [], ["policy preflight denied the intent"]
        if _policy_missing(policy) and intent.tools_needed:
            return ArbitrationDecision.REJECT, [], ["policy preflight is required for tool execution"]

        high_risk = intent.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} or potential.risk_cost >= 0.60
        if high_risk:
            approvals.append("human_approval")
            if approval_granted:
                reasons.append("high risk was approved, but execution remains sandbox-limited")
                return ArbitrationDecision.SANDBOX_EXECUTE, approvals, reasons
            reasons.append("high risk requires approval before execution")
            return ArbitrationDecision.REQUIRE_APPROVAL, approvals, reasons

        if intent.action_family in {OpenActionFamily.NEW_TOOL, OpenActionFamily.NEW_SKILL, OpenActionFamily.REST, OpenActionFamily.LEARN}:
            reasons.append("intent is advisory or capability-seeking, so it should be reported only")
            return ArbitrationDecision.REPORT_ONLY, approvals, reasons

        if not intent.tools_needed:
            reasons.append("low-risk intent has no tool side effects")
            return ArbitrationDecision.REPORT_ONLY, approvals, reasons

        if allow_auto_execute and _policy_allowed(policy) and potential.risk_cost <= 0.20:
            reasons.append("low-risk tool intent is explicitly allowed for auto execution")
            return ArbitrationDecision.AUTO_EXECUTE, approvals, reasons

        reasons.append("low-risk tool intent is limited to sandbox execution")
        return ArbitrationDecision.SANDBOX_EXECUTE, approvals, reasons


def pre_tool_call(
    *,
    intent: OpenIntent,
    tool_name: str,
    arbiter: BoYueArbiter | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Thin pre_tool_call adapter that blocks non-executable arbitration results."""

    tool_intent = intent
    if tool_name and tool_name not in tool_intent.tools_needed:
        tool_intent = OpenIntent.from_dict(
            {
                **intent.to_dict(),
                "tools_needed": [*intent.tools_needed, tool_name],
            }
        )
    result = (arbiter or BoYueArbiter()).arbitrate(intent=tool_intent, **kwargs)
    allowed = result.decision in EXECUTABLE_DECISIONS
    return {
        "allowed": allowed,
        "decision": result.decision.value,
        "arbitration": result.to_dict(),
        "reason": result.rationale,
    }


def _linz_publish_decision(
    policy: dict[str, Any],
    catalog: dict[str, Any],
    authorization: dict[str, Any],
    approval_granted: bool,
) -> tuple[ArbitrationDecision, list[str], list[str]]:
    if _policy_denied(policy):
        return ArbitrationDecision.REJECT, [], ["policy preflight denied Linz World publish"]
    if not _policy_allowed(policy):
        return ArbitrationDecision.REJECT, [], ["Linz World publish requires PolicyEngine allow"]
    if not _catalog_allowed(catalog):
        return ArbitrationDecision.REJECT, [], ["Linz World publish requires confirmed event catalog subject/event_type"]
    if not _authorization_allowed(authorization):
        return ArbitrationDecision.REJECT, [], ["Linz World publish requires authorization map allow"]
    if _requires_approval(policy, authorization) and not approval_granted:
        return (
            ArbitrationDecision.REQUIRE_APPROVAL,
            ["linz_world_publish_approval"],
            ["Linz World publish requires approval before execution"],
        )
    return ArbitrationDecision.AUTO_EXECUTE, [], ["Linz World publish passed policy, catalog, and authorization"]


def _scores(
    intent: OpenIntent,
    potential: ActionPotential,
    policy: dict[str, Any],
    catalog: dict[str, Any],
    authorization: dict[str, Any],
) -> dict[str, float]:
    innovation_score = _clamp(
        potential.learning_potential
        + (0.15 if intent.action_family in {OpenActionFamily.NEW_TOOL, OpenActionFamily.NEW_SKILL, OpenActionFamily.CREATE} else 0.0)
    )
    opportunity_score = _clamp(max(potential.value_potential, potential.overall_score))
    expansion_value = _clamp((innovation_score + opportunity_score) / 2.0)
    risk_score = _clamp(max(potential.risk_cost, _risk_cost(intent.risk_level)))
    permission_level = 1.0 if _policy_allowed(policy) or not intent.tools_needed else 0.0
    compliance_fit = 1.0 if not _policy_denied(policy) else 0.0
    if _is_linz_publish(intent) or (_is_chat_reply(intent) and _chat_reply_send_requested(intent)):
        compliance_fit = 1.0 if _policy_allowed(policy) and _catalog_allowed(catalog) and _authorization_allowed(authorization) else 0.0
        permission_level = 1.0 if _authorization_allowed(authorization) else 0.0
    trust_impact = _clamp(1.0 - risk_score + (0.10 if compliance_fit else -0.20))
    mutual_benefit_score = _clamp(potential.mutual_benefit_potential)
    long_term_net_value = _clamp((potential.overall_score + trust_impact) / 2.0)
    ecosystem_gain = _clamp((mutual_benefit_score + expansion_value) / 2.0)
    return {
        "innovation_score": innovation_score,
        "opportunity_score": opportunity_score,
        "expansion_value": expansion_value,
        "risk_score": risk_score,
        "permission_level": permission_level,
        "compliance_fit": compliance_fit,
        "trust_impact": trust_impact,
        "mutual_benefit_score": mutual_benefit_score,
        "long_term_net_value": long_term_net_value,
        "ecosystem_gain": ecosystem_gain,
        "bo_score": _clamp((innovation_score + opportunity_score + expansion_value) / 3.0),
        "yue_score": _clamp(((1.0 - risk_score) + permission_level + compliance_fit + trust_impact) / 4.0),
        "harmony_score": _clamp((mutual_benefit_score + long_term_net_value + ecosystem_gain) / 3.0),
    }


def _is_linz_publish(intent: OpenIntent) -> bool:
    haystack = " ".join(
        [
            intent.action_type,
            *intent.tools_needed,
            str(intent.metadata.get("operation") or ""),
            str(intent.metadata.get("linz_world") or ""),
            str(intent.metadata.get("linz_world_publish") or ""),
            str(intent.metadata.get("world_publish") or ""),
        ]
    ).lower()
    return ("linz_world" in haystack or "linz_publish" in haystack) and "publish" in haystack


def _is_chat_reply(intent: OpenIntent) -> bool:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    return intent.action_type == "reply_chat_message" or isinstance(metadata.get("reply"), dict)


def _chat_reply_send_requested(intent: OpenIntent) -> bool:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    reply = metadata.get("reply") if isinstance(metadata.get("reply"), dict) else {}
    return bool(metadata.get("chat_reply_send_requested") or reply.get("send_requested"))


def _chat_reply_send_decision(
    policy: dict[str, Any],
    catalog: dict[str, Any],
    authorization: dict[str, Any],
    approval_granted: bool,
) -> tuple[ArbitrationDecision, list[str], list[str]]:
    if _policy_denied(policy):
        return ArbitrationDecision.REJECT, [], ["policy preflight denied Linz World chat reply"]
    if not _policy_allowed(policy):
        return ArbitrationDecision.REJECT, [], ["Linz World chat reply requires PolicyEngine allow"]
    if not _catalog_allowed(catalog):
        return ArbitrationDecision.REJECT, [], ["Linz World chat reply requires confirmed event catalog subject/event_type"]
    if not _authorization_allowed(authorization):
        return ArbitrationDecision.REJECT, [], ["Linz World chat reply requires authorization map allow"]
    if _requires_approval(policy, authorization) and not approval_granted:
        return (
            ArbitrationDecision.REQUIRE_APPROVAL,
            ["linz_world_chat_reply_approval"],
            ["Linz World chat reply requires approval before execution"],
        )
    return ArbitrationDecision.AUTO_EXECUTE, [], ["Linz World chat reply passed policy, catalog, and authorization"]


def _policy_allowed(policy: dict[str, Any]) -> bool:
    return str(policy.get("decision") or policy.get("status") or "").lower() in {"allow", "allowed", "pass", "passed"}


def _policy_denied(policy: dict[str, Any]) -> bool:
    return str(policy.get("decision") or policy.get("status") or "").lower() in {"deny", "denied", "reject", "rejected", "blocked"}


def _policy_missing(policy: dict[str, Any]) -> bool:
    return not policy


def _catalog_allowed(catalog: dict[str, Any]) -> bool:
    return bool(catalog.get("subject_confirmed") and catalog.get("event_type_confirmed"))


def _authorization_allowed(authorization: dict[str, Any]) -> bool:
    return str(authorization.get("decision") or authorization.get("status") or "").lower() in {"allow", "allowed"}


def _requires_approval(policy: dict[str, Any], authorization: dict[str, Any]) -> bool:
    return bool(policy.get("requires_approval") or authorization.get("requires_approval"))


def _combined_risk(intent_risk: RiskLevel, potential_risk: float) -> RiskLevel:
    by_score = RiskLevel.LOW
    if potential_risk >= 0.80:
        by_score = RiskLevel.CRITICAL
    elif potential_risk >= 0.60:
        by_score = RiskLevel.HIGH
    elif potential_risk >= 0.35:
        by_score = RiskLevel.MEDIUM
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    return max(intent_risk, by_score, key=order.index)


def _risk_cost(risk_level: RiskLevel) -> float:
    return {
        RiskLevel.LOW: 0.15,
        RiskLevel.MEDIUM: 0.45,
        RiskLevel.HIGH: 0.70,
        RiskLevel.CRITICAL: 0.90,
    }[risk_level]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(float(value), 6)))
