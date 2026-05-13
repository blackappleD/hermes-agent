"""Lightweight protocol objects for the os_runtime tension-field runtime.

This module intentionally defines data contracts only. It does not import or
invoke Hermes runtime, Linz World, tool, memory, or session infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints


class EventSource(str, Enum):
    LINZ_WORLD = "linz_world"
    HERMES_CONVERSATION = "hermes_conversation"
    TOOL_RESULT = "tool_result"
    RUNTIME_FEEDBACK = "runtime_feedback"
    MEMORY = "memory"
    SYSTEM = "system"


class TensionType(str, Enum):
    VALUE_CONFLICT = "value_conflict"
    UNSATISFIED_GOAL = "unsatisfied_goal"
    ENVIRONMENTAL_CHANGE = "environmental_change"
    SOCIAL_SIGNAL = "social_signal"
    MEMORY_RESONANCE = "memory_resonance"
    CREATIVE_PRESSURE = "creative_pressure"
    UNCERTAINTY = "uncertainty"
    CONSTRAINT = "constraint"


class TensionOperationType(str, Enum):
    GENERATE = "generate"
    UPDATE = "update"
    MERGE = "merge"
    HIBERNATE = "hibernate"
    ELIMINATE = "eliminate"


class OpenActionFamily(str, Enum):
    COMMUNICATE = "communicate"
    LEARN = "learn"
    TRADE = "trade"
    COLLABORATE = "collaborate"
    REST = "rest"
    CREATE = "create"
    NEW_TOOL = "new_tool"
    NEW_SKILL = "new_skill"


class ArbitrationDecision(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    SANDBOX_EXECUTE = "sandbox_execute"
    REQUIRE_APPROVAL = "require_approval"
    REPORT_ONLY = "report_only"
    REJECT = "reject"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BubbleLifecycle(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class RuleMaturity(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


T = TypeVar("T", bound="JSONRoundTripMixin")


class JSONRoundTripMixin:
    """Dataclass mixin with strict enum parsing and JSON-friendly output."""

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _to_json_value(getattr(self, item.name))
            for item in fields(self)
        }

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        if not isinstance(data, dict):
            raise TypeError(f"{cls.__name__}.from_dict() requires a dict")

        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for item in fields(cls):
            if item.name in data:
                kwargs[item.name] = _from_json_value(
                    data[item.name],
                    hints.get(item.name, Any),
                )
        return cls(**kwargs)


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _to_json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_json_value(item) for key, item in value.items()}
    return value


def _from_json_value(value: Any, hint: Any) -> Any:
    if hint is Any:
        return value

    origin = get_origin(hint)
    args = get_args(hint)

    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        for option in args:
            if option is type(None):
                continue
            try:
                return _from_json_value(value, option)
            except (TypeError, ValueError):
                continue
        return value

    if origin is list:
        item_hint = args[0] if args else Any
        return [_from_json_value(item, item_hint) for item in value]

    if origin is dict:
        value_hint = args[1] if len(args) > 1 else Any
        return {
            key: _from_json_value(item, value_hint)
            for key, item in value.items()
        }

    if isinstance(hint, type) and issubclass(hint, Enum):
        if isinstance(value, hint):
            return value
        return hint(value)

    if isinstance(hint, type) and issubclass(hint, JSONRoundTripMixin):
        if isinstance(value, hint):
            return value
        return hint.from_dict(value)

    return value


@dataclass
class OSRuntimeEventRef(JSONRoundTripMixin):
    event_id: str
    source: EventSource
    trace_id: str = ""
    session_id: str = ""
    timestamp: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldIdentityRef(JSONRoundTripMixin):
    os_id: str = ""
    soul_id: str = ""
    os_name: str = ""
    account_id: str = ""
    authorization_state: str = "unknown"
    map_version: str = ""
    memory_summary_available: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContextView(JSONRoundTripMixin):
    task_id: str = ""
    session_id: str = ""
    user_goal: str = ""
    active_goal: str = ""
    recent_event_ids: list[str] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContextView(JSONRoundTripMixin):
    agent_id: str = ""
    profile_name: str = ""
    world_identity: WorldIdentityRef | None = None
    capabilities: list[str] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    memory_summary: str = ""
    context_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalSet(JSONRoundTripMixin):
    event_refs: list[OSRuntimeEventRef] = field(default_factory=list)
    task_context: TaskContextView | None = None
    agent_context: AgentContextView | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifeState(JSONRoundTripMixin):
    energy: float = 1.0
    fatigue: float = 0.0
    health: float = 1.0
    wakefulness: float = 1.0
    curiosity: float = 0.0
    boredom: float = 0.0
    creative_pressure: float = 0.0
    social_hunger: float = 0.0
    silence_pressure: float = 0.0
    restraint: float = 1.0
    life_cycle: str = ""
    recovery_cycle: str = ""
    generated_intent_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifeStateDelta(JSONRoundTripMixin):
    previous: dict[str, Any] = field(default_factory=dict)
    current: LifeState | None = None
    changes: dict[str, dict[str, float]] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TensionOperation(JSONRoundTripMixin):
    operation: TensionOperationType
    tension_id: str
    tension_type: TensionType | None = None
    intensity_delta: float = 0.0
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TensionExplanation(JSONRoundTripMixin):
    event_id: str = ""
    detected_conflicts: list[str] = field(default_factory=list)
    operation_reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TensionInterpretation(JSONRoundTripMixin):
    event_id: str
    detected_conflicts: list[str] = field(default_factory=list)
    operations: list[TensionOperation] = field(default_factory=list)
    explanation: str = ""
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tension(JSONRoundTripMixin):
    tension_id: str
    tension_type: TensionType
    intensity: float = 0.0
    trend: float = 0.0
    trend_slope: float = 0.0
    baseline: float = 0.0
    activation: float = 0.0
    confidence: float = 0.0
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TensionSet(JSONRoundTripMixin):
    core_tensions: list[Tension] = field(default_factory=list)
    dynamic_tensions: list[Tension] = field(default_factory=list)
    propagation_edges: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TensionNetworkDelta(JSONRoundTripMixin):
    operations: list[TensionOperation] = field(default_factory=list)
    propagation_edges: list[dict[str, Any]] = field(default_factory=list)
    activated_tensions: list[str] = field(default_factory=list)
    hibernated_tensions: list[str] = field(default_factory=list)
    eliminated_tensions: list[str] = field(default_factory=list)
    rejected_operations: list[TensionOperation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionPotential(JSONRoundTripMixin):
    intent_id: str = ""
    value_potential: float = 0.0
    mutual_benefit_potential: float = 0.0
    learning_potential: float = 0.0
    risk_cost: float = 0.0
    overall_score: float = 0.0
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SelfPrompt(JSONRoundTripMixin):
    prompt_id: str = ""
    state_summary: str = ""
    tension_summary: str = ""
    potential_summary: str = ""
    memory_scope: list[str] = field(default_factory=list)
    constraint_scope: list[str] = field(default_factory=list)
    environment_scope: str = ""
    open_space: OpenSpace | None = None
    target_direction: TargetDirection | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenSpace(JSONRoundTripMixin):
    space_id: str = ""
    description: str = ""
    available_action_families: list[OpenActionFamily] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetDirection(JSONRoundTripMixin):
    direction_id: str = ""
    description: str = ""
    success_condition: str = ""
    stop_condition: str = ""
    priority: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenIntent(JSONRoundTripMixin):
    intent_id: str
    action_family: OpenActionFamily
    action_type: str = ""
    why_now: str = ""
    open_space: OpenSpace | None = None
    target_direction: TargetDirection | None = None
    tools_needed: list[str] = field(default_factory=list)
    proposed_new_tools: list[str] = field(default_factory=list)
    proposed_new_skills: list[str] = field(default_factory=list)
    success_condition: str = ""
    stop_condition: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbitrationResult(JSONRoundTripMixin):
    intent_id: str
    decision: ArbitrationDecision
    risk_level: RiskLevel = RiskLevel.LOW
    bo_score: float = 0.0
    yue_score: float = 0.0
    harmony_score: float = 0.0
    innovation_score: float = 0.0
    opportunity_score: float = 0.0
    expansion_value: float = 0.0
    risk_score: float = 0.0
    permission_level: float = 0.0
    compliance_fit: float = 0.0
    trust_impact: float = 0.0
    mutual_benefit_score: float = 0.0
    long_term_net_value: float = 0.0
    ecosystem_gain: float = 0.0
    rationale: str = ""
    required_approvals: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionTicket(JSONRoundTripMixin):
    ticket_id: str
    intent_id: str
    decision: ArbitrationDecision
    issued_at: str = ""
    expires_at: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionReceipt(JSONRoundTripMixin):
    receipt_id: str
    ticket_id: str = ""
    intent_id: str = ""
    status: str = ""
    started_at: str = ""
    completed_at: str = ""
    output_summary: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BubbleSpec(JSONRoundTripMixin):
    bubble_id: str
    title: str = ""
    lifecycle: BubbleLifecycle = BubbleLifecycle.PROPOSED
    goal: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    owner_agent_id: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidencePackage(JSONRoundTripMixin):
    evidence_id: str
    trace_id: str = ""
    event_ids: list[str] = field(default_factory=list)
    receipt_ids: list[str] = field(default_factory=list)
    summary: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleCrystal(JSONRoundTripMixin):
    rule_id: str
    maturity: RuleMaturity = RuleMaturity.R0
    title: str = ""
    description: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    applies_to: list[str] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ActionPotential",
    "AgentContextView",
    "ArbitrationDecision",
    "ArbitrationResult",
    "BubbleLifecycle",
    "BubbleSpec",
    "EventSource",
    "EvidencePackage",
    "ExecutionReceipt",
    "JSONRoundTripMixin",
    "LifeState",
    "LifeStateDelta",
    "OpenActionFamily",
    "OpenIntent",
    "OpenSpace",
    "OSRuntimeEventRef",
    "PermissionTicket",
    "RiskLevel",
    "RuleCrystal",
    "RuleMaturity",
    "SelfPrompt",
    "SignalSet",
    "TargetDirection",
    "TaskContextView",
    "Tension",
    "TensionExplanation",
    "TensionInterpretation",
    "TensionNetworkDelta",
    "TensionOperation",
    "TensionOperationType",
    "TensionSet",
    "TensionType",
    "WorldIdentityRef",
]
