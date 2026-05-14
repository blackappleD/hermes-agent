"""Turn-boundary hooks for all-turn tension observation and optional injection."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.os_runtime.adapters.context import ContextAdapter
from agent.os_runtime.adapters.events import EventProjectionAdapter
from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEvent, OSRuntimeEventRepository
from agent.os_runtime.autonomous_state import AutonomousRuntimeState
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.debug_log import log_pipeline_step
from agent.os_runtime.domain import EventSource, LifeState, TensionSet
from agent.os_runtime.engine import BoYueArbiter, OpenIntentGenerator, SelfPromptCompiler, TensionFieldEngine, TensionInterpreter
from agent.os_runtime.engine.action_potential import ActionPotentialEvaluator
from agent.os_runtime.engine.life_state import LifeStateSystem
from agent.os_runtime.engine.signals import SignalInterpreter
from agent.os_runtime.self_prompt_injector import SelfPromptInjector

logger = logging.getLogger(__name__)


@dataclass
class TurnTensionEvaluation:
    applied: bool = False
    request: dict[str, Any] | None = None
    event_id: str = ""
    self_prompt: dict[str, Any] = field(default_factory=dict)
    injected: bool = False
    should_block_side_effect: bool = False
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class TurnTensionHook:
    def __init__(
        self,
        session_id: str,
        *,
        profile_id: str = "",
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        event_repository: OSRuntimeEventRepository | None = None,
        queue_repository: RuntimeQueueRepository | None = None,
        context_adapter: Any = None,
        signal_interpreter: Any = None,
        life_system: Any = None,
        tension_interpreter: Any = None,
        tension_engine: Any = None,
        action_evaluator: Any = None,
        self_prompt_compiler: Any = None,
        intent_generator: Any = None,
        arbiter: Any = None,
        injector: SelfPromptInjector | None = None,
    ) -> None:
        self.session_id = session_id
        self.profile_id = profile_id
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.event_repository = event_repository or OSRuntimeEventRepository(enabled=self.config.enabled)
        self.queue_repository = queue_repository or RuntimeQueueRepository(enabled=self.config.enabled)
        self.context_adapter = context_adapter
        self.signal_interpreter = signal_interpreter or SignalInterpreter(config=self.config)
        self.life_system = life_system or LifeStateSystem()
        self.tension_interpreter = tension_interpreter or TensionInterpreter()
        self.tension_engine = tension_engine or TensionFieldEngine()
        self.action_evaluator = action_evaluator or ActionPotentialEvaluator()
        self.self_prompt_compiler = self_prompt_compiler or SelfPromptCompiler()
        self.intent_generator = intent_generator or OpenIntentGenerator()
        self.arbiter = arbiter or BoYueArbiter()
        self.injector = injector or SelfPromptInjector()

    def before_turn(
        self,
        request: dict[str, Any],
        *,
        message: Any = None,
        event_type: str = "human_request",
        external_side_effect: bool = False,
    ) -> TurnTensionEvaluation:
        if not self._enabled(pre=True):
            return TurnTensionEvaluation(applied=False, request=request, reason="disabled")
        try:
            projection = self._project_before(message, event_type=event_type, request=request)
            if not projection:
                return TurnTensionEvaluation(applied=False, request=request, reason="projection skipped")
            evaluation = self._evaluate([projection], phase="before_turn")
            next_request = request
            injected = False
            payload: dict[str, Any] = {}
            if self.config.autonomous.inject_self_prompt:
                injected_result = self.injector.inject(
                    request,
                    evaluation["self_prompt"],
                    evidence_refs=evaluation["evidence_refs"],
                )
                next_request = injected_result.request
                injected = injected_result.injected
                payload = injected_result.payload
            return TurnTensionEvaluation(
                applied=True,
                request=next_request,
                event_id=projection.event_id,
                self_prompt=payload,
                injected=injected,
                evidence=evaluation,
            )
        except Exception as exc:
            logger.debug("os_runtime before_turn hook failed open: %s", exc, exc_info=True)
            return TurnTensionEvaluation(
                applied=False,
                request=request,
                should_block_side_effect=external_side_effect,
                reason=f"hook error: {type(exc).__name__}",
            )

    def after_turn(
        self,
        *,
        assistant_response: str = "",
        tool_result: Any = None,
        runtime_feedback: str = "",
        external_side_effect: bool = False,
    ) -> TurnTensionEvaluation:
        if not self._enabled(post=True):
            return TurnTensionEvaluation(applied=False, reason="disabled")
        try:
            events = self._project_after(
                assistant_response=assistant_response,
                tool_result=tool_result,
                runtime_feedback=runtime_feedback,
            )
            if not events:
                return TurnTensionEvaluation(applied=False, reason="projection skipped")
            evaluation = self._evaluate(events, phase="after_turn")
            return TurnTensionEvaluation(
                applied=True,
                event_id=events[0].event_id,
                evidence=evaluation,
            )
        except Exception as exc:
            logger.debug("os_runtime after_turn hook failed open: %s", exc, exc_info=True)
            return TurnTensionEvaluation(
                applied=False,
                should_block_side_effect=external_side_effect,
                reason=f"hook error: {type(exc).__name__}",
            )

    def _enabled(self, *, pre: bool = False, post: bool = False) -> bool:
        auto = self.config.autonomous
        if not self.config.enabled or not auto.enabled or not auto.apply_to_all_turns:
            return False
        if pre and not auto.pre_turn_evaluation:
            return False
        if post and not auto.post_turn_evaluation:
            return False
        return bool(self.session_id)

    def _project_before(
        self,
        message: Any,
        *,
        event_type: str,
        request: dict[str, Any],
    ) -> OSRuntimeEvent | None:
        adapter = EventProjectionAdapter(self.event_repository, self.config)
        if event_type == "world_event":
            result = adapter.world_event(message, session_id=self.session_id, trace_id=self.session_id)
        elif event_type in {"runtime_tick", "scheduled_tick", "tick"}:
            result = adapter.project(
                event_type="runtime_tick",
                source=EventSource.RUNTIME_FEEDBACK,
                summary=_message_text(message) or "scheduled runtime tick",
                session_id=self.session_id,
                trace_id=self.session_id,
                event_id=f"osr-tick-{uuid.uuid4().hex}",
                metadata={"phase": "before_turn"},
            )
        else:
            result = adapter.human_request(
                _message_text(message) or _last_user_text(request),
                session_id=self.session_id,
                trace_id=self.session_id,
                metadata={"phase": "before_turn"},
            )
        return result.event if result.written else None

    def _project_after(
        self,
        *,
        assistant_response: str,
        tool_result: Any,
        runtime_feedback: str,
    ) -> list[OSRuntimeEvent]:
        adapter = EventProjectionAdapter(self.event_repository, self.config)
        events: list[OSRuntimeEvent] = []
        if assistant_response:
            result = adapter.assistant_response(
                assistant_response,
                session_id=self.session_id,
                trace_id=self.session_id,
                metadata={"phase": "after_turn"},
            )
            if result.written and result.event:
                events.append(result.event)
        if tool_result is not None:
            tool_name = "tool"
            if isinstance(tool_result, dict):
                tool_name = str(tool_result.get("tool_name") or tool_result.get("name") or "tool")
            result = adapter.tool_result(
                tool_name,
                tool_result,
                session_id=self.session_id,
                trace_id=self.session_id,
                metadata={"phase": "after_turn"},
            )
            if result.written and result.event:
                events.append(result.event)
        if runtime_feedback:
            result = adapter.runtime_feedback(
                runtime_feedback,
                session_id=self.session_id,
                trace_id=self.session_id,
                metadata={"phase": "after_turn"},
            )
            if result.written and result.event:
                events.append(result.event)
        return events

    def _evaluate(self, events: list[OSRuntimeEvent], *, phase: str) -> dict[str, Any]:
        state = self.queue_repository.load_state(self.session_id) or AutonomousRuntimeState(
            session_id=self.session_id,
            profile_id=self.profile_id,
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="goal_event",
            data={
                "state": {
                    "status": state.status,
                    "last_turn_event_id": state.last_turn_event_id,
                    "last_intent_id": state.last_intent_id,
                },
                "events": events,
            },
        )
        adapter = self.context_adapter or ContextAdapter(
            event_repository=self.event_repository,
            config=self.config,
        )
        snapshot = adapter.build_context(
            session_id=self.session_id,
            user_goal="",
            active_goal="",
            task_id=f"autonomous-turn:{self.session_id}",
            profile_name=self.profile_id,
            recent_events=events,
            resource_state={"source": phase},
        )
        signals = self.signal_interpreter.interpret(
            task_context=snapshot.task_context,
            agent_context=snapshot.agent_context,
            events=snapshot.recent_events,
            authorization_map=getattr(snapshot, "authorization_map", None),
            relationships=getattr(snapshot, "relationships", None),
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="signal_set",
            data={
                "task_context": snapshot.task_context,
                "agent_context": snapshot.agent_context,
                "diagnostics": getattr(snapshot, "diagnostics", {}),
                "signals": signals,
            },
        )
        life_state, life_delta = self.life_system.update(
            signals,
            previous_state=_life_state(state),
            execution_feedback={"status": "observed", "phase": phase},
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="life_state",
            data={
                "life_state": life_state,
                "life_delta": life_delta,
            },
        )
        event_ref = signals.event_refs[0] if signals.event_refs else events[0].to_ref()
        previous_tensions = _tension_set(state)
        tension_interpretation = self.tension_interpreter.interpret(
            event_ref,
            signals,
            snapshot.task_context,
            life_state,
            previous_tensions,
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="tension_operation",
            data={
                "event_ref": event_ref,
                "previous_tensions": previous_tensions,
                "tension_interpretation": tension_interpretation,
                "operations": tension_interpretation.operations,
            },
        )
        tension_set, tension_delta = self.tension_engine.update(
            previous_tensions,
            tension_interpretation.operations,
            signals,
            life_state,
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="tension_set",
            data={
                "tension_set": tension_set,
                "tension_delta": tension_delta,
            },
        )
        action_potential = self.action_evaluator.evaluate(
            signal_set=signals,
            life_state=life_state,
            tension_set=tension_set,
            intent_id=f"turn-ap:{self.session_id}:{events[0].event_id}",
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="action_potential",
            data={"action_potential": action_potential},
        )
        self_prompt = self.self_prompt_compiler.compile(
            task_context=snapshot.task_context,
            agent_context=snapshot.agent_context,
            life_state=life_state,
            tension_set=tension_set,
            tension_explanation=tension_interpretation,
            action_potential=action_potential,
            constraints=[
                "ephemeral self prompt only",
                "no tool execution",
                "no world publish",
            ],
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="self_prompt",
            data={"self_prompt": self_prompt},
        )
        intent = self.intent_generator.generate(
            self_prompt=self_prompt,
            action_potential=action_potential,
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="open_intent",
            data={"intent": intent},
        )
        arbitration = self.arbiter.arbitrate(
            intent=intent,
            self_prompt=self_prompt,
            action_potential=action_potential,
            available_tools=[],
            allow_auto_execute=False,
        )
        log_pipeline_step(
            surface="turn_hook",
            session_id=self.session_id,
            profile_id=self.profile_id,
            phase=phase,
            step="arbiter",
            data={"arbitration": arbitration},
        )
        state.last_turn_event_id = events[0].event_id
        state.last_intent_id = intent.intent_id
        state.last_arbitration = arbitration.to_dict()
        state.last_action_summary = arbitration.rationale
        state.life_state = life_state.to_dict()
        state.tension_set = tension_set.to_dict()
        state.action_potential = action_potential.to_dict()
        state.self_prompt = self_prompt.to_dict()
        evidence_refs = list(self_prompt.metadata.get("evidence_refs") or [])
        state.evidence = {
            "phase": phase,
            "event_ids": [event.event_id for event in events],
            "life_delta": _safe_to_dict(life_delta),
            "tension_delta": _safe_to_dict(tension_delta),
            "action_potential": action_potential.to_dict(),
            "open_intent": intent.to_dict(),
            "arbitration": arbitration.to_dict(),
            "evidence_refs": evidence_refs,
        }
        self.queue_repository.save_state(state)
        return {
            **state.evidence,
            "self_prompt": self_prompt.to_dict(),
            "evidence_refs": evidence_refs,
        }


def _life_state(state: AutonomousRuntimeState) -> LifeState | None:
    try:
        return LifeState.from_dict(state.life_state) if state.life_state else None
    except Exception:
        return None


def _tension_set(state: AutonomousRuntimeState) -> TensionSet | None:
    try:
        return TensionSet.from_dict(state.tension_set) if state.tension_set else None
    except Exception:
        return None


def _safe_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {"value": data}
    if isinstance(value, dict):
        return dict(value)
    return {"value": str(value)}


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return str(message.get("text") or message.get("content") or "")
    return str(getattr(message, "text", "") or getattr(message, "content", "") or "")


def _last_user_text(request: dict[str, Any]) -> str:
    for message in reversed(request.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


__all__ = ["TurnTensionEvaluation", "TurnTensionHook"]
