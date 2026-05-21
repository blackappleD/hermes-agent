"""SelfPrompt compilation for the os_runtime tension-field runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent.os_runtime.domain import (
    ActionPotential,
    AgentContextView,
    LifeState,
    OpenActionFamily,
    OpenSpace,
    RuleCrystal,
    SelfPrompt,
    TargetDirection,
    TaskContextView,
    Tension,
    TensionExplanation,
    TensionInterpretation,
    TensionSet,
)


DEFAULT_ACTION_FAMILIES = [
    OpenActionFamily.COMMUNICATE,
    OpenActionFamily.LEARN,
    OpenActionFamily.COLLABORATE,
    OpenActionFamily.CREATE,
    OpenActionFamily.REST,
]


class SelfPromptCompiler:
    """Compile transient runtime evidence into a JSON-friendly SelfPrompt."""

    rule_version = "self_prompt_compiler.v1"

    def compile(
        self,
        *,
        task_context: TaskContextView | None = None,
        agent_context: AgentContextView | None = None,
        life_state: LifeState | None = None,
        tension_set: TensionSet | None = None,
        tension_explanation: TensionExplanation | TensionInterpretation | None = None,
        action_potential: ActionPotential | None = None,
        memory_refs: list[str] | None = None,
        constraints: list[str] | None = None,
        environment_state: dict[str, Any] | str | None = None,
        available_tools: list[str] | None = None,
        rule_crystals: list[RuleCrystal] | None = None,
    ) -> SelfPrompt:
        task = task_context or TaskContextView()
        agent = agent_context or AgentContextView()
        life = life_state or LifeState()
        tensions = tension_set or TensionSet()
        explanation = _coerce_explanation(tension_explanation)
        potential = action_potential or ActionPotential()
        tools = _dedupe([*(available_tools or []), *task.tool_names, *agent.active_tools])
        merged_constraints = _dedupe([*(constraints or []), *task.constraints, *_linz_rule_constraints(task)])
        if not action_potential:
            merged_constraints.append("action potential unavailable: using neutral defaults")
        fail_closed = _fail_closed_constraints(merged_constraints, environment_state)
        merged_constraints = _dedupe([*merged_constraints, *fail_closed])

        memory_scope = _dedupe(
            [
                *(memory_refs or []),
                *task.memory_refs,
                *(["agent_context:memory_summary"] if agent.memory_summary else []),
            ]
        )
        environment_scope = _environment_scope(environment_state, agent, tools)
        open_space = _open_space(task, potential, tools, merged_constraints)
        target_direction = _target_direction(task, tensions, explanation, potential)
        evidence_refs = _evidence_refs(task, tensions, explanation, potential)
        prompt_id = f"self-prompt:{task.task_id or potential.intent_id or explanation.event_id or 'transient'}"

        return SelfPrompt(
            prompt_id=prompt_id,
            state_summary=_state_summary(life),
            tension_summary=_tension_summary(tensions, explanation),
            potential_summary=_potential_summary(potential),
            memory_scope=memory_scope,
            constraint_scope=merged_constraints,
            environment_scope=environment_scope,
            open_space=open_space,
            target_direction=target_direction,
            metadata={
                "rule_version": self.rule_version,
                "task_id": task.task_id,
                "session_id": task.session_id,
                "available_tools": tools,
                "rule_crystals": [item.rule_id for item in rule_crystals or []],
                "evidence_refs": evidence_refs,
                "diagnostics": _diagnostics(tension_explanation, action_potential),
            },
        )


def pre_llm_call(request: dict[str, Any], self_prompt: SelfPrompt) -> dict[str, Any]:
    """Inject SelfPrompt into the current user message without changing system prompts."""

    next_request = deepcopy(request)
    messages = next_request.setdefault("messages", [])
    if not isinstance(messages, list):
        next_request["messages"] = []
        messages = next_request["messages"]

    target: dict[str, Any] | None = None
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            target = message
            break
    if target is None:
        target = {"role": "user", "content": ""}
        messages.append(target)

    metadata = dict(target.get("metadata") or {})
    ephemeral_context = dict(metadata.get("ephemeral_context") or {})
    ephemeral_context["os_runtime_self_prompt"] = self_prompt.to_dict()
    metadata["ephemeral_context"] = ephemeral_context
    target["metadata"] = metadata
    return next_request


def _coerce_explanation(
    explanation: TensionExplanation | TensionInterpretation | None,
) -> TensionExplanation:
    if isinstance(explanation, TensionExplanation):
        return explanation
    if isinstance(explanation, TensionInterpretation):
        embedded = explanation.metadata.get("explanation")
        if isinstance(embedded, dict):
            return TensionExplanation.from_dict(embedded)
        return TensionExplanation(
            event_id=explanation.event_id,
            detected_conflicts=explanation.detected_conflicts,
            operation_reasons=[operation.reason for operation in explanation.operations],
            evidence=explanation.evidence,
            summary=explanation.explanation,
            metadata={"source": "tension_interpretation"},
        )
    return TensionExplanation(summary="No tension explanation was provided.")


def _state_summary(life: LifeState) -> str:
    return (
        f"cycle={life.life_cycle or 'unknown'} recovery={life.recovery_cycle or 'unknown'} "
        f"energy={life.energy:.2f} fatigue={life.fatigue:.2f} "
        f"wakefulness={life.wakefulness:.2f} restraint={life.restraint:.2f}"
    )


def _tension_summary(tensions: TensionSet, explanation: TensionExplanation) -> str:
    active = sorted(
        [*tensions.core_tensions, *tensions.dynamic_tensions],
        key=lambda item: item.activation,
        reverse=True,
    )[:3]
    if active:
        tension_text = "; ".join(
            f"{item.tension_id}:{item.tension_type.value}:activation={item.activation:.2f}"
            for item in active
        )
    else:
        tension_text = "no active tensions"
    explanation_text = explanation.summary or "no explanation summary"
    return f"{tension_text}. explanation={explanation_text}"


def _potential_summary(potential: ActionPotential) -> str:
    return (
        f"value={potential.value_potential:.2f} mutual={potential.mutual_benefit_potential:.2f} "
        f"learning={potential.learning_potential:.2f} risk={potential.risk_cost:.2f} "
        f"overall={potential.overall_score:.2f}. rationale={potential.rationale or 'not provided'}"
    )


def _environment_scope(
    environment_state: dict[str, Any] | str | None,
    agent_context: AgentContextView,
    tools: list[str],
) -> str:
    if isinstance(environment_state, str):
        base = environment_state
    elif isinstance(environment_state, dict):
        base = "; ".join(f"{key}={value}" for key, value in sorted(environment_state.items()))
    else:
        base = agent_context.context_summary or "environment not provided"
    tool_text = ", ".join(tools) if tools else "none"
    return f"{base}; available_tools={tool_text}"


def _open_space(
    task: TaskContextView,
    potential: ActionPotential,
    tools: list[str],
    constraints: list[str],
) -> OpenSpace:
    families = list(DEFAULT_ACTION_FAMILIES)
    if potential.risk_cost <= 0.45 and tools:
        families.append(OpenActionFamily.NEW_TOOL)
    if potential.learning_potential >= 0.60:
        families.append(OpenActionFamily.NEW_SKILL)
    if any("trade" in item.lower() or "settlement" in item.lower() for item in constraints):
        families.append(OpenActionFamily.TRADE)
    return OpenSpace(
        space_id=f"open-space:{task.task_id or potential.intent_id or 'transient'}",
        description="Allowed action families and tools for this transient decision.",
        available_action_families=_dedupe_families(families),
        constraints=constraints,
        metadata={
            "available_tools": tools,
            "catalog_validation_required": True,
            "authorization_required": True,
        },
    )


def _target_direction(
    task: TaskContextView,
    tensions: TensionSet,
    explanation: TensionExplanation,
    potential: ActionPotential,
) -> TargetDirection:
    strongest = _strongest_tension(tensions)
    description = task.active_goal or task.user_goal or (strongest.summary if strongest else "") or explanation.summary
    if not description:
        description = "Clarify the next low-risk action."
    success = (
        potential.metadata.get("success_condition")
        or task.metadata.get("success_condition")
        or "Produce an auditable next-step proposal."
    )
    stop = (
        potential.metadata.get("stop_condition")
        or task.metadata.get("stop_condition")
        or "Stop before external side effects, unknown authorization, or rising risk."
    )
    return TargetDirection(
        direction_id=f"target-direction:{task.task_id or potential.intent_id or explanation.event_id or 'transient'}",
        description=str(description),
        success_condition=str(success),
        stop_condition=str(stop),
        priority=round(max(potential.overall_score, strongest.activation if strongest else 0.0), 6),
        metadata={
            "source_tension_id": strongest.tension_id if strongest else "",
            "event_id": explanation.event_id,
        },
    )


def _evidence_refs(
    task: TaskContextView,
    tensions: TensionSet,
    explanation: TensionExplanation,
    potential: ActionPotential,
) -> list[str]:
    tension_ids = [item.tension_id for item in [*tensions.core_tensions, *tensions.dynamic_tensions]]
    refs = [
        *(f"event:{item}" for item in task.recent_event_ids),
        *(f"tension:{item}" for item in tension_ids),
        *(f"evidence:{item}" for item in explanation.evidence),
    ]
    if explanation.event_id:
        refs.append(f"event:{explanation.event_id}")
    if potential.intent_id:
        refs.append(f"action_potential:{potential.intent_id}")
    return _dedupe(refs)


def _diagnostics(
    tension_explanation: TensionExplanation | TensionInterpretation | None,
    action_potential: ActionPotential | None,
) -> list[str]:
    diagnostics: list[str] = []
    if tension_explanation is None:
        diagnostics.append("missing_tension_explanation")
    if action_potential is None:
        diagnostics.append("missing_action_potential")
    return diagnostics


def _fail_closed_constraints(
    constraints: list[str],
    environment_state: dict[str, Any] | str | None,
) -> list[str]:
    text = " ".join([*constraints, str(environment_state or "")]).lower()
    constraints_out: list[str] = []
    if "authorization" in text and "allow" not in text:
        constraints_out.append("fail-closed: authorization is not confirmed")
    if "event_catalog" in text and "confirmed" not in text and "allow" not in text:
        constraints_out.append("fail-closed: linz_world.event_catalog is not confirmed")
    if "high risk" in text or "risk=high" in text:
        constraints_out.append("fail-closed: high risk requires approval")
    return constraints_out


def _linz_rule_constraints(task: TaskContextView) -> list[str]:
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    rule = metadata.get("linz_rule_context")
    if not isinstance(rule, dict) or not rule:
        return []
    lines: list[str] = []
    if rule.get("authoritative"):
        sections = [
            str(item.get("section_id") or "")
            for item in rule.get("matched_sections") or []
            if isinstance(item, dict) and item.get("section_id")
        ]
        phase = str(rule.get("phase") or "unknown")
        confidence = str(rule.get("confidence") or "unknown")
        summary = str(rule.get("summary") or "").strip()
        head = f"linz_rule_context: phase={phase}; confidence={confidence}"
        if sections:
            head += f"; sections={','.join(sections[:5])}"
        lines.append(head)
        if summary:
            lines.append(f"linz_rule_summary: {_clamp_rule_text(summary)}")
        required = _string_list(rule.get("required_fields"))
        if required:
            lines.append(f"linz_rule_required_fields: {', '.join(required[:12])}")
        missing = _string_list(rule.get("missing_fields"))
        if missing:
            lines.append(f"linz_rule_missing_fields: {', '.join(missing[:12])}")
        forbidden = _string_list(rule.get("forbidden"))
        if forbidden:
            lines.append(f"linz_rule_forbidden: {'; '.join(forbidden[:8])}")
        next_steps = _string_list(rule.get("next_steps"))
        if next_steps:
            lines.append(f"linz_rule_next_steps: {'; '.join(next_steps[:5])}")
        if rule.get("approval_required"):
            lines.append("linz_rule_approval_required: true")
        return lines
    if rule.get("status") == "unmatched":
        return ["linz_rule_context: no authoritative structured match; ask for missing world identifiers before side effects"]
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return _dedupe([str(item) for item in values if str(item or "").strip()])


def _clamp_rule_text(text: str, max_chars: int = 500) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 16].rstrip() + "... [truncated]"


def _strongest_tension(tensions: TensionSet) -> Tension | None:
    all_tensions = [*tensions.core_tensions, *tensions.dynamic_tensions]
    if not all_tensions:
        return None
    return max(all_tensions, key=lambda item: item.activation)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_families(values: list[OpenActionFamily]) -> list[OpenActionFamily]:
    seen: set[OpenActionFamily] = set()
    result: list[OpenActionFamily] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
