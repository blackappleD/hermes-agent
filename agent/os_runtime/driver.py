"""Turn-boundary runtime driver for os_runtime assisted continuation."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.os_runtime.adapters.context import ContextAdapter
from agent.os_runtime.adapters.session_store import OSRuntimeEvent, OSRuntimeEventRepository
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.debug_log import log_pipeline_step
from agent.os_runtime.domain import (
    ActionPotential,
    ArbitrationDecision,
    ArbitrationResult,
    EventSource,
    LifeState,
    OpenIntent,
    RecommendedDepth,
    RiskLevel,
    SelfPrompt,
    SignalSet,
    TensionInterpretation,
    TensionSet,
)
from agent.os_runtime.engine import BoYueArbiter, OpenIntentGenerator, SelfPromptCompiler, TensionFieldEngine, TensionInterpreter
from agent.os_runtime.engine.action_potential import ActionPotentialEvaluator
from agent.os_runtime.engine.life_state import LifeStateSystem
from agent.os_runtime.engine.signals import SignalInterpreter

logger = logging.getLogger(__name__)


OS_RUNTIME_CONTINUATION_MARKER = "[OS Runtime assisted continuation]"
DEFAULT_MAX_TURNS = 8


@dataclass
class OSRuntimeState:
    """Serializable per-session runtime state."""

    status: str = "inactive"
    goal: str = ""
    turns_used: int = 0
    max_turns: int = DEFAULT_MAX_TURNS
    last_tension_interpretation_id: str = ""
    last_action_potential_id: str = ""
    last_self_prompt_id: str = ""
    last_intent_id: str = ""
    last_arbitration: dict[str, Any] = field(default_factory=dict)
    last_world_event_id: str = ""
    paused_reason: str = ""
    last_decision_reason: str = ""
    last_world_event: dict[str, Any] = field(default_factory=dict)
    life_state: dict[str, Any] = field(default_factory=dict)
    tension_set: dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "OSRuntimeState":
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("OSRuntimeState JSON must decode to an object")
        return cls(
            status=str(data.get("status") or "inactive"),
            goal=str(data.get("goal") or ""),
            turns_used=int(data.get("turns_used") or 0),
            max_turns=int(data.get("max_turns") or DEFAULT_MAX_TURNS),
            last_tension_interpretation_id=str(data.get("last_tension_interpretation_id") or ""),
            last_action_potential_id=str(data.get("last_action_potential_id") or ""),
            last_self_prompt_id=str(data.get("last_self_prompt_id") or ""),
            last_intent_id=str(data.get("last_intent_id") or ""),
            last_arbitration=dict(data.get("last_arbitration") or {}),
            last_world_event_id=str(data.get("last_world_event_id") or ""),
            paused_reason=str(data.get("paused_reason") or ""),
            last_decision_reason=str(data.get("last_decision_reason") or ""),
            last_world_event=dict(data.get("last_world_event") or {}),
            life_state=dict(data.get("life_state") or {}),
            tension_set=dict(data.get("tension_set") or {}),
            updated_at=float(data.get("updated_at") or 0.0),
        )


@dataclass
class OSRuntimeDecision:
    status: str
    should_continue: bool = False
    continuation_prompt: str | None = None
    reason: str = ""
    message: str = ""
    trace_ids: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "should_continue": self.should_continue,
            "continuation_prompt": self.continuation_prompt,
            "reason": self.reason,
            "message": self.message,
            "trace_ids": dict(self.trace_ids),
        }


def _meta_key(session_id: str) -> str:
    return f"os_runtime:{session_id}"


_DB_CACHE: dict[str, Any] = {}


class _MetaStore:
    def __init__(self, root: Path):
        self.db_path = root / "state.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("CREATE TABLE IF NOT EXISTS state_meta (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM state_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO state_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()


def _get_session_db() -> Any | None:
    try:
        from hermes_constants import get_hermes_home
        from hermes_state import SessionDB

        home = str(get_hermes_home())
    except Exception as exc:  # pragma: no cover
        logger.debug("os_runtime driver: SessionDB bootstrap failed: %s", exc)
        return None

    cached = _DB_CACHE.get(home)
    if cached is not None:
        return cached
    try:
        db = SessionDB(db_path=Path(home) / "state.db")
    except Exception as exc:  # pragma: no cover
        logger.debug("os_runtime driver: SessionDB unavailable, using meta fallback: %s", exc)
        try:
            db = _MetaStore(Path(home))
        except Exception as fallback_exc:
            logger.debug("os_runtime driver: meta fallback unavailable: %s", fallback_exc)
            return None
    _DB_CACHE[home] = db
    return db


def load_state(session_id: str) -> OSRuntimeState | None:
    if not session_id:
        return None
    db = _get_session_db()
    if db is None:
        return None
    try:
        raw = db.get_meta(_meta_key(session_id))
    except Exception as exc:
        logger.debug("os_runtime driver: get_meta failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        return OSRuntimeState.from_json(raw)
    except Exception as exc:
        logger.warning("os_runtime driver: could not parse state for %s: %s", session_id, exc)
        return None


def save_state(session_id: str, state: OSRuntimeState) -> None:
    if not session_id:
        return
    state.updated_at = time.time()
    db = _get_session_db()
    if db is None:
        return
    try:
        db.set_meta(_meta_key(session_id), state.to_json())
    except Exception as exc:
        logger.debug("os_runtime driver: set_meta failed: %s", exc)


def clear_state(session_id: str) -> None:
    state = load_state(session_id)
    if state is None:
        return
    state.status = "cleared"
    state.paused_reason = "user-cleared"
    save_state(session_id, state)


class OSRuntimeDriver:
    """Evaluate os_runtime state after an assistant turn."""

    def __init__(
        self,
        session_id: str,
        *,
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        event_repository: OSRuntimeEventRepository | None = None,
        context_adapter: Any = None,
        signal_interpreter: Any = None,
        life_system: Any = None,
        tension_interpreter: Any = None,
        tension_engine: Any = None,
        action_evaluator: Any = None,
        self_prompt_compiler: Any = None,
        intent_generator: Any = None,
        arbiter: Any = None,
    ) -> None:
        self.session_id = session_id
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.event_repository = event_repository
        self.context_adapter = context_adapter
        self.signal_interpreter = signal_interpreter or SignalInterpreter(config=self.config)
        self.life_system = life_system or LifeStateSystem()
        self.tension_interpreter = tension_interpreter or TensionInterpreter()
        self.tension_engine = tension_engine or TensionFieldEngine()
        self.action_evaluator = action_evaluator or ActionPotentialEvaluator()
        self.self_prompt_compiler = self_prompt_compiler or SelfPromptCompiler()
        self.intent_generator = intent_generator or OpenIntentGenerator(model_task=self.config.model_task)
        self.arbiter = arbiter or BoYueArbiter()
        self._state = load_state(session_id)

    @property
    def state(self) -> OSRuntimeState | None:
        return self._state

    def ensure_state(self) -> OSRuntimeState:
        if self._state is None:
            self._state = OSRuntimeState(max_turns=int(self.config.max_continuation_turns or DEFAULT_MAX_TURNS))
        return self._state

    def set_passive(self) -> OSRuntimeState:
        state = self.ensure_state()
        state.status = "passive"
        state.goal = state.goal or ""
        state.turns_used = 0
        state.max_turns = int(self.config.max_continuation_turns or DEFAULT_MAX_TURNS)
        state.paused_reason = ""
        save_state(self.session_id, state)
        return state

    def set_goal(self, goal: str, *, max_turns: int | None = None) -> OSRuntimeState:
        goal = (goal or "").strip()
        if not goal:
            raise ValueError("goal text is empty")
        state = self.ensure_state()
        state.status = "assisted"
        state.goal = goal
        state.turns_used = 0
        state.max_turns = int(max_turns or self.config.max_continuation_turns or DEFAULT_MAX_TURNS)
        state.paused_reason = ""
        state.last_decision_reason = ""
        save_state(self.session_id, state)
        return state

    def pause(self, reason: str = "user-paused") -> OSRuntimeState | None:
        if self._state is None:
            return None
        self._state.status = "paused"
        self._state.paused_reason = reason
        save_state(self.session_id, self._state)
        return self._state

    def resume(self) -> OSRuntimeState | None:
        if self._state is None or not self._state.goal:
            return None
        self._state.status = "assisted"
        self._state.paused_reason = ""
        save_state(self.session_id, self._state)
        return self._state

    def clear(self) -> None:
        if self._state is None:
            return
        self._state.status = "cleared"
        self._state.paused_reason = "user-cleared"
        save_state(self.session_id, self._state)
        self._state = None

    def evaluate_after_turn(
        self,
        final_response: str = "",
        *,
        source: str = "",
        recent_event: Any = None,
        recent_events: list[Any] | None = None,
        user_interrupted: bool = False,
        resource_state: dict[str, Any] | None = None,
    ) -> OSRuntimeDecision:
        state = self.ensure_state()
        if not self.config.enabled:
            return self._stop(state, "disabled", reason="os_runtime.enabled=false")
        if state.status in {"inactive", "cleared"}:
            return self._stop(state, state.status, reason="no active os_runtime state")
        if state.status == "paused":
            return self._stop(state, "paused", reason=state.paused_reason or "paused")
        if user_interrupted:
            state.status = "paused"
            state.paused_reason = "user-interrupted"
            return self._stop(state, "paused", reason=state.paused_reason, persist=True)
        if state.status == "assisted" and state.turns_used >= state.max_turns:
            state.status = "paused"
            state.paused_reason = f"turn budget exhausted ({state.turns_used}/{state.max_turns})"
            return self._stop(state, "paused", reason=state.paused_reason, persist=True)

        try:
            events = self._resolve_recent_events(recent_event=recent_event, recent_events=recent_events)
            if not events:
                return self._runtime_feedback_stop(state, "recent event missing")

            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="goal_event",
                data={
                    "state": {
                        "status": state.status,
                        "goal": state.goal,
                        "turns_used": state.turns_used,
                        "max_turns": state.max_turns,
                    },
                    "source": source,
                    "final_response_present": bool(final_response.strip()),
                    "events": events,
                    "resource_state": resource_state or {},
                },
            )
            snapshot = self._build_context(state, events, source=source, resource_state=resource_state)
            signals: SignalSet = self.signal_interpreter.interpret(
                task_context=snapshot.task_context,
                agent_context=snapshot.agent_context,
                events=snapshot.recent_events,
                authorization_map=getattr(snapshot, "authorization_map", None),
                relationships=getattr(snapshot, "relationships", None),
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="signal_set",
                data={
                    "task_context": snapshot.task_context,
                    "agent_context": snapshot.agent_context,
                    "diagnostics": getattr(snapshot, "diagnostics", {}),
                    "signals": signals,
                },
            )
            life_state = self._previous_life_state(state)
            life_state, life_delta = self.life_system.update(
                signals,
                previous_state=life_state,
                execution_feedback={"status": "success" if final_response.strip() else "empty"},
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="life_state",
                data={
                    "life_state": life_state,
                    "life_delta": life_delta,
                },
            )
            event_ref = signals.event_refs[0] if signals.event_refs else None
            previous_tensions = self._previous_tension_set(state)
            tension_interpretation: TensionInterpretation = self.tension_interpreter.interpret(
                event_ref,
                signals,
                snapshot.task_context,
                life_state,
                previous_tensions,
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
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
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="tension_set",
                data={
                    "tension_set": tension_set,
                    "tension_delta": tension_delta,
                },
            )
            action_potential: ActionPotential = self.action_evaluator.evaluate(
                signal_set=signals,
                life_state=life_state,
                tension_set=tension_set,
                intent_id=f"osr-ap:{self.session_id}:{state.turns_used + 1}",
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="action_potential",
                data={"action_potential": action_potential},
            )
            self_prompt: SelfPrompt = self.self_prompt_compiler.compile(
                task_context=snapshot.task_context,
                agent_context=snapshot.agent_context,
                life_state=life_state,
                tension_set=tension_set,
                tension_explanation=tension_interpretation,
                action_potential=action_potential,
                constraints=[
                    "no tool execution",
                    "no world publish",
                    "continuation must be ordinary user-role text",
                ],
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="self_prompt",
                data={"self_prompt": self_prompt},
            )
            intent: OpenIntent = self.intent_generator.generate(
                self_prompt=self_prompt,
                action_potential=action_potential,
                event_content=events,
                tension_field={
                    "tension_set": tension_set,
                    "tension_interpretation": tension_interpretation,
                },
                prefer_llm=self.config.use_llm_intent,
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="open_intent",
                data={"intent": intent},
            )
            arbitration: ArbitrationResult = self.arbiter.arbitrate(
                intent=intent,
                self_prompt=self_prompt,
                action_potential=action_potential,
                available_tools=[],
                allow_auto_execute=False,
            )
            log_pipeline_step(
                surface="driver",
                session_id=self.session_id,
                phase="after_turn",
                step="arbiter",
                data={"arbitration": arbitration},
            )
            self._capture_evidence(
                state,
                events=events,
                life_state=life_state,
                tension_set=tension_set,
                tension_interpretation=tension_interpretation,
                action_potential=action_potential,
                self_prompt=self_prompt,
                intent=intent,
                arbitration=arbitration,
                extra={
                    "life_delta": _safe_to_dict(life_delta),
                    "tension_delta": _safe_to_dict(tension_delta),
                },
            )

            if state.status == "passive" or self.config.mode == "passive":
                return self._stop(state, "passive", reason="passive mode records state only", persist=True)
            if state.status != "assisted":
                return self._stop(state, state.status, reason="not in assisted mode", persist=True)
            if not state.goal.strip():
                state.status = "paused"
                state.paused_reason = "missing goal"
                return self._stop(state, "paused", reason=state.paused_reason, persist=True)
            if not self._arbitration_allows_continuation(arbitration, intent, action_potential):
                state.status = "paused"
                state.paused_reason = f"arbitration denied: {arbitration.decision.value}"
                return self._stop(state, "paused", reason=state.paused_reason, persist=True)

            state.turns_used += 1
            prompt = self._continuation_prompt(state, intent, arbitration)
            try:
                repo = self._event_repository()
                repo.append(
                    OSRuntimeEvent(
                        event_id=f"osr-cont-{uuid.uuid4().hex}",
                        event_type="os_runtime_continuation",
                        source=EventSource.HERMES_CONVERSATION,
                        session_id=self.session_id,
                        summary=prompt[:240],
                        metadata={
                            "goal": state.goal,
                            "turns_used": state.turns_used,
                            "max_turns": state.max_turns,
                            "synthetic": True,
                        },
                    )
                )
            except Exception as exc:
                logger.debug("os_runtime continuation event projection failed: %s", exc)
            state.last_decision_reason = arbitration.rationale or "low-risk assisted continuation"
            save_state(self.session_id, state)
            return OSRuntimeDecision(
                status=state.status,
                should_continue=True,
                continuation_prompt=prompt,
                reason=state.last_decision_reason,
                message=f"↻ OS Runtime continuing ({state.turns_used}/{state.max_turns}): {state.last_decision_reason}",
                trace_ids=self._trace_ids(state),
            )
        except Exception as exc:
            logger.debug("os_runtime driver failed closed: %s", exc, exc_info=True)
            return self._runtime_feedback_stop(state, f"driver error: {type(exc).__name__}")

    def _resolve_recent_events(self, *, recent_event: Any, recent_events: list[Any] | None) -> list[Any]:
        if recent_events is not None:
            return list(recent_events)
        if recent_event is not None:
            return [recent_event]
        repo = self.event_repository
        if repo is not None and self.session_id:
            return repo.list_by_session(self.session_id, limit=5)
        return []

    def _build_context(
        self,
        state: OSRuntimeState,
        events: list[Any],
        *,
        source: str,
        resource_state: dict[str, Any] | None,
    ) -> Any:
        adapter = self.context_adapter
        if adapter is None:
            adapter = ContextAdapter(
                event_repository=self.event_repository,
                config=self.config,
            )
        return adapter.build_context(
            session_id=self.session_id,
            user_goal=state.goal,
            active_goal=state.goal,
            task_id=f"os-runtime:{self.session_id}",
            recent_events=events,
            resource_state=resource_state or {"source": source},
        )

    def _event_repository(self) -> OSRuntimeEventRepository:
        if self.event_repository is None:
            self.event_repository = OSRuntimeEventRepository(enabled=self.config.enabled)
        return self.event_repository

    def _previous_life_state(self, state: OSRuntimeState) -> LifeState | None:
        if not state.life_state:
            return None
        try:
            return LifeState.from_dict(state.life_state)
        except Exception:
            return None

    def _previous_tension_set(self, state: OSRuntimeState) -> TensionSet | None:
        if not state.tension_set:
            return None
        try:
            return TensionSet.from_dict(state.tension_set)
        except Exception:
            return None

    def _capture_evidence(self, state: OSRuntimeState, **kwargs: Any) -> None:
        events = kwargs.get("events") or []
        event_ref = _event_ref(events[0]) if events else None
        if event_ref is not None:
            state.last_world_event_id = getattr(event_ref, "event_id", "") or ""
            state.last_world_event = _safe_to_dict(event_ref)
        tension_interpretation = kwargs["tension_interpretation"]
        action_potential = kwargs["action_potential"]
        self_prompt = kwargs["self_prompt"]
        intent = kwargs["intent"]
        arbitration = kwargs["arbitration"]
        state.last_tension_interpretation_id = getattr(tension_interpretation, "event_id", "") or f"tension:{state.last_world_event_id}"
        state.last_action_potential_id = getattr(action_potential, "intent_id", "") or ""
        state.last_self_prompt_id = getattr(self_prompt, "prompt_id", "") or ""
        state.last_intent_id = getattr(intent, "intent_id", "") or ""
        state.last_arbitration = _safe_to_dict(arbitration)
        state.life_state = _safe_to_dict(kwargs["life_state"])
        state.tension_set = _safe_to_dict(kwargs["tension_set"])
        state.last_arbitration.setdefault("runtime_extra", kwargs.get("extra") or {})

    def _arbitration_allows_continuation(
        self,
        arbitration: ArbitrationResult,
        intent: OpenIntent,
        action_potential: ActionPotential,
    ) -> bool:
        if arbitration.decision == ArbitrationDecision.REPORT_ONLY:
            return True
        if arbitration.decision != ArbitrationDecision.AUTO_EXECUTE:
            return False
        if intent.tools_needed or intent.proposed_new_tools:
            return False
        if intent.risk_level != RiskLevel.LOW or arbitration.risk_level != RiskLevel.LOW:
            return False
        if action_potential.recommended_depth not in {RecommendedDepth.REPORT, RecommendedDepth.DRAFT, RecommendedDepth.CONTINUE_TURN, RecommendedDepth.NONE}:
            return False
        return True

    def _continuation_prompt(self, state: OSRuntimeState, intent: OpenIntent, arbitration: ArbitrationResult) -> str:
        why_now = (intent.why_now or arbitration.rationale or "continue the low-risk draft/report task").strip()
        success = (intent.success_condition or "Produce the next useful natural-language step.").strip()
        stop = (intent.stop_condition or "Stop before tools, publishing, approvals, or external side effects.").strip()
        return (
            f"{OS_RUNTIME_CONTINUATION_MARKER}\n"
            f"Goal: {state.goal}\n"
            f"Why now: {why_now}\n"
            f"Success condition: {success}\n"
            f"Stop condition: {stop}\n\n"
            "Continue with the next low-risk natural-language or draft step only. "
            "Do not call tools, publish events, or perform external side effects."
        )

    def _stop(
        self,
        state: OSRuntimeState,
        status: str,
        *,
        reason: str,
        persist: bool = False,
    ) -> OSRuntimeDecision:
        state.last_decision_reason = reason
        if persist:
            save_state(self.session_id, state)
        return OSRuntimeDecision(
            status=status,
            should_continue=False,
            reason=reason,
            message=self._status_message(state, reason),
            trace_ids=self._trace_ids(state),
        )

    def _runtime_feedback_stop(self, state: OSRuntimeState, reason: str) -> OSRuntimeDecision:
        try:
            repo = self._event_repository()
            event = repo.append(
                {
                    "event_id": f"osr-feedback-{uuid.uuid4().hex}",
                    "event_type": "runtime_feedback",
                    "source": EventSource.RUNTIME_FEEDBACK.value,
                    "session_id": self.session_id,
                    "summary": reason,
                    "metadata": {"driver": "os_runtime", "fail_closed": True},
                }
            )
            if event:
                state.last_world_event_id = event.event_id
        except Exception as exc:
            logger.debug("os_runtime runtime feedback projection failed: %s", exc)
        state.paused_reason = reason if state.status == "assisted" else state.paused_reason
        return self._stop(state, state.status, reason=reason, persist=True)

    def _status_message(self, state: OSRuntimeState, reason: str) -> str:
        if not reason:
            return ""
        return f"OS Runtime {state.status}: {reason}"

    def _trace_ids(self, state: OSRuntimeState) -> dict[str, str]:
        return {
            "tension_interpretation": state.last_tension_interpretation_id,
            "action_potential": state.last_action_potential_id,
            "self_prompt": state.last_self_prompt_id,
            "intent": state.last_intent_id,
            "world_event": state.last_world_event_id,
        }


def _event_ref(event: Any) -> Any:
    if hasattr(event, "to_ref"):
        return event.to_ref()
    return event


def _safe_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {"value": data}
    if isinstance(value, dict):
        return dict(value)
    try:
        return asdict(value)
    except Exception:
        return {"value": str(value)}


def is_os_runtime_continuation_event(event_or_text: Any) -> bool:
    text = getattr(event_or_text, "text", event_or_text) or ""
    if str(text).startswith(OS_RUNTIME_CONTINUATION_MARKER):
        return True
    metadata = getattr(event_or_text, "metadata", None)
    if isinstance(metadata, dict):
        return bool(metadata.get("os_runtime_synthetic"))
    return False


__all__ = [
    "DEFAULT_MAX_TURNS",
    "OS_RUNTIME_CONTINUATION_MARKER",
    "OSRuntimeDecision",
    "OSRuntimeDriver",
    "OSRuntimeState",
    "clear_state",
    "is_os_runtime_continuation_event",
    "load_state",
    "save_state",
]
