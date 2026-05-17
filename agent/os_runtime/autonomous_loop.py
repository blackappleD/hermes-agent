"""One-shot resident autonomous runtime loop."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.adapters.context import ContextAdapter
from agent.os_runtime.adapters.events import EventProjectionAdapter
from agent.os_runtime.adapters.runtime_queue import RuntimeQueueRepository
from agent.os_runtime.adapters.session_store import OSRuntimeEvent, OSRuntimeEventRepository
from agent.os_runtime.action_executor import (
    AutonomousActionExecutor,
    is_chat_reply_intent,
    is_chat_reply_send_intent,
    is_world_publish_intent,
    publish_payload_from_intent,
)
from agent.os_runtime.autonomous_scheduler import AutonomousScheduler
from agent.os_runtime.autonomous_state import (
    AutonomousRuntimeState,
    AutonomousRuntimeStatus,
    AutonomousWakeRecord,
)
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.debug_log import log_pipeline_step
from agent.os_runtime.domain import (
    ArbitrationDecision,
    EventSource,
    LifeState,
    RecommendedDepth,
    TensionSet,
)
from agent.os_runtime.engine import BoYueArbiter, OpenIntentGenerator, SelfPromptCompiler, TensionFieldEngine, TensionInterpreter
from agent.os_runtime.engine.action_potential import ActionPotentialEvaluator
from agent.os_runtime.engine.life_state import LifeStateSystem
from agent.os_runtime.engine.signals import SignalInterpreter

logger = logging.getLogger(__name__)


@dataclass
class AutonomousRunResult:
    ran: bool
    status: str
    reason: str = ""
    wake_record: AutonomousWakeRecord | None = None
    state: AutonomousRuntimeState | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


class AutonomousRuntimeLoop:
    def __init__(
        self,
        session_id: str,
        *,
        profile_id: str = "",
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        event_repository: OSRuntimeEventRepository | None = None,
        queue_repository: RuntimeQueueRepository | None = None,
        scheduler: AutonomousScheduler | None = None,
        context_adapter: Any = None,
        signal_interpreter: Any = None,
        life_system: Any = None,
        tension_interpreter: Any = None,
        tension_engine: Any = None,
        action_evaluator: Any = None,
        self_prompt_compiler: Any = None,
        intent_generator: Any = None,
        arbiter: Any = None,
        action_executor: Any = None,
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
        self.scheduler = scheduler or AutonomousScheduler(
            session_id,
            profile_id=profile_id,
            config=self.config,
            repository=self.queue_repository,
        )
        self.context_adapter = context_adapter
        self.signal_interpreter = signal_interpreter or SignalInterpreter(config=self.config)
        self.life_system = life_system or LifeStateSystem()
        self.tension_interpreter = tension_interpreter or TensionInterpreter()
        self.tension_engine = tension_engine or TensionFieldEngine()
        self.action_evaluator = action_evaluator or ActionPotentialEvaluator()
        self.self_prompt_compiler = self_prompt_compiler or SelfPromptCompiler()
        self.intent_generator = intent_generator or OpenIntentGenerator(model_task=self.config.model_task)
        self.arbiter = arbiter or BoYueArbiter()
        self.action_executor = action_executor or AutonomousActionExecutor(
            config=self.config,
            repository=self.event_repository,
        )

    def run_once(
        self,
        *,
        wake_reason: str,
        event_ref: Any = None,
    ) -> AutonomousRunResult:
        event_id = _event_id(event_ref)
        decision = self.scheduler.wake(reason=wake_reason, event_id=event_id)
        if not decision.allowed:
            return AutonomousRunResult(False, "skipped", decision.reason, state=decision.state)

        wake = AutonomousWakeRecord(
            wake_id=f"wake-{uuid.uuid4().hex}",
            session_id=self.session_id,
            profile_id=self.profile_id,
            wake_reason=wake_reason,
            event_id=event_id,
        )
        try:
            events = self._events(wake_reason=wake_reason, event_ref=event_ref)
            state = self.queue_repository.load_state(self.session_id) or decision.state or AutonomousRuntimeState(
                session_id=self.session_id,
                profile_id=self.profile_id,
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="goal_event",
                data={
                    "wake": wake,
                    "wake_reason": wake_reason,
                    "event_ref": event_ref,
                    "events": events,
                    "state": {
                        "status": state.status,
                        "last_wake_reason": state.last_wake_reason,
                        "last_intent_id": state.last_intent_id,
                    },
                },
                trace_id=wake.wake_id,
            )
            snapshot = self._context(events, wake_reason=wake_reason)
            signals = self.signal_interpreter.interpret(
                task_context=snapshot.task_context,
                agent_context=snapshot.agent_context,
                # Autonomous wakes must be judged against the event that woke
                # the runtime.  Historical context is still available through
                # the snapshot, but feeding it into the signal layer makes old
                # tool/code risks look like current-event risks.
                events=events,
                authorization_map=getattr(snapshot, "authorization_map", None),
                relationships=getattr(snapshot, "relationships", None),
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="signal_set",
                data={
                    "task_context": snapshot.task_context,
                    "agent_context": snapshot.agent_context,
                    "diagnostics": getattr(snapshot, "diagnostics", {}),
                    "signals": signals,
                },
                trace_id=wake.wake_id,
            )
            life_state, life_delta = self.life_system.update(
                signals,
                previous_state=_life_state(state),
                execution_feedback={"status": "autonomous_wake", "wake_reason": wake_reason},
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="life_state",
                data={
                    "life_state": life_state,
                    "life_delta": life_delta,
                },
                trace_id=wake.wake_id,
            )
            signal_ref = events[0].to_ref() if events else (signals.event_refs[0] if signals.event_refs else None)
            previous_tensions = _tension_set(state)
            tension_interpretation = self.tension_interpreter.interpret(
                signal_ref,
                signals,
                snapshot.task_context,
                life_state,
                previous_tensions,
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="tension_operation",
                data={
                    "event_ref": signal_ref,
                    "previous_tensions": previous_tensions,
                    "tension_interpretation": tension_interpretation,
                    "operations": tension_interpretation.operations,
                },
                trace_id=wake.wake_id,
            )
            tension_set, tension_delta = self.tension_engine.update(
                previous_tensions,
                tension_interpretation.operations,
                signals,
                life_state,
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="tension_set",
                data={
                    "tension_set": tension_set,
                    "tension_delta": tension_delta,
                },
                trace_id=wake.wake_id,
            )
            action_potential = self.action_evaluator.evaluate(
                signal_set=signals,
                life_state=life_state,
                tension_set=tension_set,
                intent_id=f"autonomous-ap:{self.session_id}:{wake.wake_id}",
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="action_potential",
                data={"action_potential": action_potential},
                trace_id=wake.wake_id,
            )
            self_prompt = self.self_prompt_compiler.compile(
                task_context=snapshot.task_context,
                agent_context=snapshot.agent_context,
                life_state=life_state,
                tension_set=tension_set,
                tension_explanation=tension_interpretation,
                action_potential=action_potential,
                constraints=[
                    "autonomous low-risk mode",
                    "no external side effects by default",
                    "no world publish without policy, catalog, authorization, STVB, evidence, and approval",
                ],
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="self_prompt",
                data={"self_prompt": self_prompt},
                trace_id=wake.wake_id,
            )
            intent = self.intent_generator.generate(
                self_prompt=self_prompt,
                action_potential=action_potential,
                event_content={
                    "current_events": events,
                    "recent_events": snapshot.recent_events,
                },
                tension_field={
                    "tension_set": tension_set,
                    "tension_interpretation": tension_interpretation,
                },
                prefer_llm=self.config.use_llm_intent,
            )
            _prepare_chat_reply_intent(intent, config=self.config)
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="open_intent",
                data={"intent": intent},
                trace_id=wake.wake_id,
            )
            arbitration = self.arbiter.arbitrate(
                intent=intent,
                self_prompt=self_prompt,
                action_potential=action_potential,
                available_tools=_available_tools(self_prompt),
                allow_auto_execute=self.config.autonomous.allow_tool_execution,
                approval_granted=False,
                policy_preflight=_policy_preflight(intent, config=self.config),
                event_catalog_preflight=_catalog_preflight(intent),
                authorization_summary=_authorization_summary(
                    snapshot,
                    intent,
                    config=self.config,
                ),
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="arbiter",
                data={"arbitration": arbitration},
                trace_id=wake.wake_id,
            )
            execution = self.action_executor.execute(
                intent=intent,
                arbitration=arbitration,
                self_prompt=self_prompt,
                event_ids=[event.event_id for event in events],
                session_id=self.session_id,
                task_id=f"autonomous:{self.session_id}:{wake_reason}",
                profile_id=self.profile_id,
            )
            log_pipeline_step(
                surface="autonomous_loop",
                session_id=self.session_id,
                profile_id=self.profile_id,
                phase="run_once",
                step="action_execution",
                data={"execution": execution.to_dict()},
                trace_id=wake.wake_id,
            )
            action_summary = execution.action_summary or _action_summary(arbitration.decision, action_potential.recommended_depth)
            evidence = {
                "wake_reason": wake_reason,
                "event_ids": [event.event_id for event in events],
                "life_state": life_state.to_dict(),
                "life_delta": _safe_to_dict(life_delta),
                "tension_set": tension_set.to_dict(),
                "tension_delta": _safe_to_dict(tension_delta),
                "action_potential": action_potential.to_dict(),
                "self_prompt": self_prompt.to_dict(),
                "open_intent": intent.to_dict(),
                "arbitration": arbitration.to_dict(),
                "execution": execution.to_dict(),
                "execution_feedback": execution.feedback,
                "evidence_package": execution.evidence_package.to_dict() if execution.evidence_package else {},
                "action_summary": action_summary,
                "stop_reason": "bounded single wake completed",
            }
            state.status = AutonomousRuntimeStatus.SLEEPING.value
            state.last_wake_reason = wake_reason
            state.last_wake_event_id = event_id
            state.last_intent_id = intent.intent_id
            state.last_arbitration = arbitration.to_dict()
            state.last_action_summary = action_summary
            state.life_state = life_state.to_dict()
            state.tension_set = tension_set.to_dict()
            state.action_potential = action_potential.to_dict()
            state.self_prompt = self_prompt.to_dict()
            state.evidence = evidence
            self.queue_repository.save_state(state)

            wake.status = "completed"
            wake.finished_at = utc_now_iso()
            wake.turns_used = min(1, decision.max_turns or 1)
            wake.stop_reason = evidence["stop_reason"]
            wake.intent_id = intent.intent_id
            wake.arbitration = arbitration.to_dict()
            wake.action_summary = action_summary
            wake.evidence = evidence
            self.queue_repository.append_wake(wake)
            state = self.scheduler.finish_wake(action_summary=action_summary)
            return AutonomousRunResult(True, "completed", action_summary, wake, state, evidence)
        except Exception as exc:
            logger.debug("autonomous runtime loop failed closed: %s", exc, exc_info=True)
            wake.status = "failed"
            wake.finished_at = utc_now_iso()
            wake.stop_reason = f"loop error: {type(exc).__name__}"
            self.queue_repository.append_wake(wake)
            state = self.scheduler.finish_wake(
                status=AutonomousRuntimeStatus.PAUSED.value,
                action_summary=wake.stop_reason,
            )
            return AutonomousRunResult(False, "failed", wake.stop_reason, wake, state)

    def _events(self, *, wake_reason: str, event_ref: Any) -> list[OSRuntimeEvent]:
        if isinstance(event_ref, OSRuntimeEvent):
            stored = self.event_repository.append(event_ref)
            return [stored or event_ref]
        if hasattr(event_ref, "to_ref") or isinstance(event_ref, dict):
            event = OSRuntimeEvent.from_dict(_event_payload(event_ref, wake_reason=wake_reason, session_id=self.session_id))
            stored = self.event_repository.append(event)
            return [stored or event]
        adapter = EventProjectionAdapter(self.event_repository, self.config)
        result = adapter.project(
            event_type="runtime_tick" if wake_reason in {"tick", "manual_tick"} else "runtime_feedback",
            source=EventSource.RUNTIME_FEEDBACK,
            summary=f"autonomous wake: {wake_reason}",
            session_id=self.session_id,
            trace_id=self.session_id,
            event_id=f"osr-autonomous-{uuid.uuid4().hex}",
            metadata={"wake_reason": wake_reason, "no_user_goal": True},
        )
        if result.written and result.event:
            return [result.event]
        return [
            OSRuntimeEvent(
                event_id=f"osr-autonomous-{uuid.uuid4().hex}",
                event_type="runtime_feedback",
                source=EventSource.RUNTIME_FEEDBACK,
                session_id=self.session_id,
                summary=f"autonomous wake: {wake_reason}",
                metadata={"wake_reason": wake_reason},
            )
        ]

    def _context(self, events: list[OSRuntimeEvent], *, wake_reason: str) -> Any:
        adapter = self.context_adapter or ContextAdapter(
            event_repository=self.event_repository,
            config=self.config,
        )
        recent_events = self._recent_context_events(events)
        return adapter.build_context(
            session_id=self.session_id,
            user_goal="",
            active_goal="",
            task_id=f"autonomous:{self.session_id}:{wake_reason}",
            profile_name=self.profile_id,
            recent_events=recent_events,
            resource_state={"source": "autonomous_loop", "wake_reason": wake_reason},
        )

    def _recent_context_events(self, events: list[OSRuntimeEvent]) -> list[OSRuntimeEvent]:
        merged: list[OSRuntimeEvent] = []
        seen: set[str] = set()
        for event in events:
            if event.event_id not in seen:
                seen.add(event.event_id)
                merged.append(event)
        try:
            history = self.event_repository.list_by_session(self.session_id, limit=20)
        except Exception:
            history = []
        for event in history:
            event_id = getattr(event, "event_id", "")
            if event_id and event_id not in seen:
                seen.add(event_id)
                merged.append(event)
        return merged


def _event_payload(event_ref: Any, *, wake_reason: str, session_id: str) -> dict[str, Any]:
    if hasattr(event_ref, "to_dict"):
        data = event_ref.to_dict()
    elif isinstance(event_ref, dict):
        data = dict(event_ref)
    else:
        data = {}
    metadata = dict(data.get("metadata") or {})
    metadata.setdefault("wake_reason", wake_reason)
    return {
        "event_id": str(data.get("event_id") or f"osr-autonomous-{uuid.uuid4().hex}"),
        "event_type": str(data.get("event_type") or ("world_event" if wake_reason == "world_event" else "runtime_feedback")),
        "source": str(data.get("source") or (EventSource.LINZ_WORLD.value if wake_reason == "world_event" else EventSource.RUNTIME_FEEDBACK.value)),
        "trace_id": str(data.get("trace_id") or data.get("event_id") or ""),
        "session_id": str(data.get("session_id") or session_id),
        "timestamp": str(data.get("timestamp") or utc_now_iso()),
        "summary": str(data.get("summary") or "autonomous wake event"),
        "metadata": metadata,
        "content_ref": str(data.get("content_ref") or ""),
        "payload_hash": str(data.get("payload_hash") or ""),
        "status": str(data.get("status") or "recorded"),
    }


def _event_id(event_ref: Any) -> str:
    if event_ref is None:
        return ""
    if isinstance(event_ref, dict):
        return str(event_ref.get("event_id") or "")
    return str(getattr(event_ref, "event_id", "") or "")


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


def _policy_preflight(intent: Any, *, config: OSRuntimeConfig) -> dict[str, Any]:
    if not is_world_publish_intent(intent) and not is_chat_reply_send_intent(intent):
        return {}
    publish = publish_payload_from_intent(intent)
    subject = str(publish.get("subject") or "")
    event_type = str(publish.get("event_type") or "")
    payload = publish.get("payload") if isinstance(publish.get("payload"), dict) else {}
    try:
        from agent.linz_world.governance import preflight_side_effect

        result = preflight_side_effect(
            capability="publish",
            subject=subject,
            event_type=event_type,
            payload=payload,
        )
    except Exception as exc:
        return {
            "decision": "deny",
            "status": "failed",
            "code": "policy_preflight_error",
            "message": f"{type(exc).__name__}: {exc}",
            "subject": subject,
            "event_type": event_type,
        }
    return {
        "decision": "allow" if getattr(result, "allowed", False) else "deny",
        "status": getattr(getattr(result, "status", None), "value", getattr(result, "status", "")),
        "code": str(getattr(result, "code", "") or ""),
        "message": str(getattr(result, "message", "") or ""),
        "next_action": str(getattr(result, "next_action", "") or ""),
        "subject": subject,
        "event_type": event_type,
        "requires_approval": bool(config.autonomous.require_approval_for_world_publish),
    }


def _catalog_preflight(intent: Any) -> dict[str, Any]:
    if not is_world_publish_intent(intent) and not is_chat_reply_send_intent(intent):
        return {"status": "not_requested", "reason": "catalog publish path not requested"}
    publish = publish_payload_from_intent(intent)
    subject = str(publish.get("subject") or "")
    event_type = str(publish.get("event_type") or "")
    try:
        from agent.linz_world.event_catalog import is_formal_event

        confirmed = is_formal_event(subject, event_type)
    except Exception as exc:
        return {
            "status": "failed",
            "subject": subject,
            "event_type": event_type,
            "subject_confirmed": False,
            "event_type_confirmed": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "status": "allowed" if confirmed else "denied",
        "subject": subject,
        "event_type": event_type,
        "subject_confirmed": confirmed,
        "event_type_confirmed": confirmed,
    }


def _authorization_summary(
    snapshot: Any,
    intent: Any | None = None,
    *,
    config: OSRuntimeConfig | None = None,
) -> dict[str, Any]:
    auth = getattr(getattr(snapshot, "task_context", None), "metadata", {}).get("authorization", {})
    data = dict(auth) if isinstance(auth, dict) else {}
    if intent is None or (not is_world_publish_intent(intent) and not is_chat_reply_send_intent(intent)):
        return data
    publish = publish_payload_from_intent(intent)
    subject = str(publish.get("subject") or "")
    event_type = str(publish.get("event_type") or "")
    auth_map = getattr(snapshot, "authorization_map", None)
    allows_event = False
    if auth_map is not None and hasattr(auth_map, "allows_event"):
        try:
            allows_event = bool(auth_map.allows_event(subject, event_type))
        except Exception:
            allows_event = False
    else:
        allows_event = _matches_allowed(subject, data.get("allowed_publish_subjects", [])) and _matches_allowed(
            event_type,
            data.get("allowed_publish_event_types", []),
        )
    allows_capability = "publish" in set(str(item) for item in data.get("allowed_capabilities", []) or [])
    auth_current = str(data.get("state") or "").lower() == "current"
    login_active = str(data.get("login_state") or "").lower() == "logged_in"
    allowed = bool(auth_current and login_active and allows_capability and allows_event)
    data.update(
        {
            "decision": "allow" if allowed else "deny",
            "status": "allowed" if allowed else "denied",
            "subject": subject,
            "event_type": event_type,
            "allows_event": allows_event,
            "allows_publish_capability": allows_capability,
            "requires_approval": bool(config.autonomous.require_approval_for_world_publish) if config else True,
        }
    )
    return data


def _prepare_chat_reply_intent(intent: Any, *, config: OSRuntimeConfig) -> None:
    if not is_chat_reply_intent(intent):
        return
    metadata = getattr(intent, "metadata", None)
    if not isinstance(metadata, dict):
        return
    reply = metadata.get("reply")
    if not isinstance(reply, dict):
        return
    suppressed = _chat_reply_suppressed(metadata, reply)
    send_requested = bool(
        not suppressed
        and config.autonomous.allow_chat_reply_auto_send
        and str(reply.get("draft_text") or "").strip()
    )
    reply["send_requested"] = send_requested
    metadata["chat_reply_send_requested"] = send_requested
    metadata["should_reply"] = not suppressed
    if suppressed:
        reply["should_reply"] = False
        reply["suppress_reply"] = True
        metadata["reply_control"] = {
            "should_reply": False,
            "suppress_reply": True,
            "reason": str(reply.get("suppress_reason") or "conversation_closing_context"),
        }
    metadata["execution_permitted"] = False


def _chat_reply_suppressed(metadata: dict[str, Any], reply: dict[str, Any]) -> bool:
    if reply.get("should_reply") is False or metadata.get("should_reply") is False:
        return True
    return _truthy(reply.get("suppress_reply")) or _truthy(reply.get("conversation_end_detected")) or _truthy(
        metadata.get("suppress_reply")
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _available_tools(self_prompt: Any) -> list[str]:
    tools = []
    metadata = getattr(self_prompt, "metadata", {}) or {}
    if isinstance(metadata, dict):
        tools.extend(str(item) for item in metadata.get("available_tools") or [])
    open_space = getattr(self_prompt, "open_space", None)
    open_metadata = getattr(open_space, "metadata", {}) if open_space is not None else {}
    if isinstance(open_metadata, dict):
        tools.extend(str(item) for item in open_metadata.get("available_tools") or [])
    seen = set()
    result = []
    for tool in tools:
        if not tool or tool in seen:
            continue
        seen.add(tool)
        result.append(tool)
        if tool == "linz_publish" and "linz_world.publish" not in seen:
            seen.add("linz_world.publish")
            result.append("linz_world.publish")
    return result


def _matches_allowed(value: str, patterns: Any) -> bool:
    text = str(value or "")
    for pattern in patterns or []:
        item = str(pattern or "")
        if item == "*" or item == text:
            return True
        if item.endswith(".*") and text.startswith(item[:-1]):
            return True
    return False


def _action_summary(decision: ArbitrationDecision, depth: RecommendedDepth) -> str:
    if decision == ArbitrationDecision.REQUIRE_APPROVAL:
        return "require_approval"
    if decision == ArbitrationDecision.REPORT_ONLY:
        return "report_only"
    if depth == RecommendedDepth.DRAFT:
        return "draft_only"
    return f"{decision.value}:{depth.value}"


def _safe_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {"value": data}
    if isinstance(value, dict):
        return dict(value)
    return {"value": str(value)}


__all__ = ["AutonomousRunResult", "AutonomousRuntimeLoop"]
