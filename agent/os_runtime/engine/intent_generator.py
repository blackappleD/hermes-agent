"""Rule-first OpenIntent generation for os_runtime."""

from __future__ import annotations

import json
from typing import Any

from agent.os_runtime.domain import (
    ActionPotential,
    OpenActionFamily,
    OpenIntent,
    OpenSpace,
    RiskLevel,
    SelfPrompt,
    TargetDirection,
)


REQUIRED_INTENT_FIELDS = {
    "action_family",
    "action_type",
    "why_now",
    "open_space",
    "target_direction",
    "tools_needed",
    "proposed_new_tools",
    "proposed_new_skills",
    "success_condition",
    "stop_condition",
}


class OpenIntentGenerator:
    """Generate auditable intents without producing execution permission."""

    rule_version = "open_intent_generator.v1"

    def generate(
        self,
        *,
        self_prompt: SelfPrompt,
        action_potential: ActionPotential | None = None,
        llm_json: str | dict[str, Any] | None = None,
        prefer_llm: bool = False,
    ) -> OpenIntent:
        potential = action_potential or ActionPotential()
        if prefer_llm and llm_json is not None:
            parsed = self._from_llm_json(self_prompt, potential, llm_json)
            if isinstance(parsed, OpenIntent):
                return parsed
            return self._rule_intent(self_prompt, potential, fallback_reason=parsed)
        return self._rule_intent(self_prompt, potential)

    def _from_llm_json(
        self,
        self_prompt: SelfPrompt,
        potential: ActionPotential,
        llm_json: str | dict[str, Any],
    ) -> OpenIntent | str:
        try:
            data = json.loads(llm_json) if isinstance(llm_json, str) else dict(llm_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            return "invalid_json"
        missing = sorted(REQUIRED_INTENT_FIELDS - set(data))
        if missing:
            return f"missing_required_fields:{','.join(missing)}"
        try:
            action_family = OpenActionFamily(data["action_family"])
        except ValueError:
            return f"unknown_action_family:{data.get('action_family')}"
        try:
            open_space = _open_space(data["open_space"], self_prompt.open_space)
            target_direction = _target_direction(data["target_direction"], self_prompt.target_direction)
        except (TypeError, ValueError):
            return "invalid_open_space_or_target_direction"

        metadata = _sanitize_metadata(data)
        metadata.update(
            {
                "source": "llm_candidate",
                "rule_version": self.rule_version,
                "execution_permitted": False,
                "action_potential_id": potential.intent_id,
            }
        )
        return OpenIntent(
            intent_id=str(data.get("intent_id") or f"intent:{self_prompt.prompt_id or 'llm'}"),
            action_family=action_family,
            action_type=str(data["action_type"]),
            why_now=str(data["why_now"]),
            open_space=open_space,
            target_direction=target_direction,
            tools_needed=_string_list(data["tools_needed"]),
            proposed_new_tools=_string_list(data["proposed_new_tools"]),
            proposed_new_skills=_string_list(data["proposed_new_skills"]),
            success_condition=str(data["success_condition"]),
            stop_condition=str(data["stop_condition"]),
            risk_level=_risk_level(data.get("risk_level"), potential),
            metadata=metadata,
        )

    def _rule_intent(
        self,
        self_prompt: SelfPrompt,
        potential: ActionPotential,
        *,
        fallback_reason: str = "",
    ) -> OpenIntent:
        open_space = self_prompt.open_space or OpenSpace()
        target_direction = self_prompt.target_direction or TargetDirection(
            description="Clarify the next low-risk step.",
            success_condition="Produce an auditable next-step proposal.",
            stop_condition="Stop before external side effects or missing authorization.",
        )
        family = _rule_family(open_space, potential)
        action_type = _action_type(family, open_space)
        tools_needed = _allowed_tools(open_space) if family in {OpenActionFamily.CREATE, OpenActionFamily.COLLABORATE} else []
        proposed_new_tools = []
        proposed_new_skills = []
        if family == OpenActionFamily.NEW_TOOL:
            proposed_new_tools = ["catalog-validated-tool-candidate"]
        if family == OpenActionFamily.NEW_SKILL:
            proposed_new_skills = ["skill-candidate-requiring-review"]

        metadata = {
            "source": "rule",
            "rule_version": self.rule_version,
            "execution_permitted": False,
            "action_potential_id": potential.intent_id,
            "evidence_refs": list(self_prompt.metadata.get("evidence_refs") or []),
        }
        if fallback_reason:
            metadata["fallback_reason"] = fallback_reason
        return OpenIntent(
            intent_id=f"intent:{potential.intent_id or self_prompt.prompt_id or 'rule'}",
            action_family=family,
            action_type=action_type,
            why_now=_why_now(self_prompt, potential),
            open_space=open_space,
            target_direction=target_direction,
            tools_needed=tools_needed,
            proposed_new_tools=proposed_new_tools,
            proposed_new_skills=proposed_new_skills,
            success_condition=target_direction.success_condition,
            stop_condition=target_direction.stop_condition,
            risk_level=_risk_level(None, potential),
            metadata=metadata,
        )


def _rule_family(open_space: OpenSpace, potential: ActionPotential) -> OpenActionFamily:
    allowed = set(open_space.available_action_families)
    if potential.risk_cost >= 0.70:
        if OpenActionFamily.REST in allowed:
            return OpenActionFamily.REST
        return OpenActionFamily.LEARN
    if potential.learning_potential >= 0.72 and OpenActionFamily.LEARN in allowed:
        return OpenActionFamily.LEARN
    if potential.value_potential >= 0.70 and potential.risk_cost <= 0.35:
        for candidate in (OpenActionFamily.CREATE, OpenActionFamily.COLLABORATE, OpenActionFamily.COMMUNICATE):
            if candidate in allowed:
                return candidate
    if not _allowed_tools(open_space) and OpenActionFamily.NEW_TOOL in allowed:
        return OpenActionFamily.NEW_TOOL
    for candidate in (OpenActionFamily.COMMUNICATE, OpenActionFamily.LEARN, OpenActionFamily.REST):
        if candidate in allowed:
            return candidate
    return OpenActionFamily.LEARN


def _action_type(family: OpenActionFamily, open_space: OpenSpace) -> str:
    if family == OpenActionFamily.COMMUNICATE:
        return "draft_message"
    if family == OpenActionFamily.LEARN:
        return "inspect_context"
    if family == OpenActionFamily.COLLABORATE:
        return "propose_collaboration"
    if family == OpenActionFamily.CREATE:
        return "draft_artifact"
    if family == OpenActionFamily.REST:
        return "cooldown_report"
    if family == OpenActionFamily.TRADE:
        return "propose_trade"
    if family == OpenActionFamily.NEW_TOOL:
        return "propose_new_tool"
    if family == OpenActionFamily.NEW_SKILL:
        return "propose_new_skill"
    return str(open_space.metadata.get("default_action_type") or "propose_next_step")


def _why_now(self_prompt: SelfPrompt, potential: ActionPotential) -> str:
    direction = self_prompt.target_direction.description if self_prompt.target_direction else "no target direction"
    return (
        f"{direction}; potential overall={potential.overall_score:.2f}, "
        f"value={potential.value_potential:.2f}, learning={potential.learning_potential:.2f}, "
        f"risk={potential.risk_cost:.2f}."
    )


def _risk_level(value: Any, potential: ActionPotential) -> RiskLevel:
    if value:
        try:
            return RiskLevel(str(value))
        except ValueError:
            return RiskLevel.HIGH
    if potential.risk_cost >= 0.80:
        return RiskLevel.CRITICAL
    if potential.risk_cost >= 0.60:
        return RiskLevel.HIGH
    if potential.risk_cost >= 0.35:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _open_space(value: Any, fallback: OpenSpace | None) -> OpenSpace:
    if isinstance(value, OpenSpace):
        return value
    if isinstance(value, dict):
        return OpenSpace.from_dict(value)
    if fallback is not None:
        return fallback
    raise TypeError("open_space must be a dict or OpenSpace")


def _target_direction(value: Any, fallback: TargetDirection | None) -> TargetDirection:
    if isinstance(value, TargetDirection):
        return value
    if isinstance(value, dict):
        return TargetDirection.from_dict(value)
    if fallback is not None:
        return fallback
    raise TypeError("target_direction must be a dict or TargetDirection")


def _sanitize_metadata(data: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = dict(data.get("metadata") or {})
    candidates: dict[str, Any] = {}
    for key in ("subject", "event_type", "payload"):
        if key in data:
            candidates[key] = data[key]
        if key in raw_metadata:
            candidates[key] = raw_metadata.pop(key)
    if candidates:
        raw_metadata["untrusted_linz_world_candidate"] = candidates
        raw_metadata["catalog_validation_required"] = True
    return raw_metadata


def _allowed_tools(open_space: OpenSpace) -> list[str]:
    return _string_list(open_space.metadata.get("available_tools") or [])


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    return [str(item) for item in value]
