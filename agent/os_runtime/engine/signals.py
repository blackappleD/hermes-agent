"""Rule-based SignalSet generation for os_runtime contexts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from agent.linz_world.models import AuthState, LoginState
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import AgentContextView, EventSource, OSRuntimeEventRef, RiskLevel, SignalSet, TaskContextView


SIGNAL_KEYS = (
    "needs",
    "world_opportunities",
    "risks",
    "world_authorization",
    "relationships",
    "resources",
    "feedback",
    "constraints",
)


class SignalInterpreter:
    """Interpret context and recent events into deterministic, non-action signals."""

    def __init__(self, *, config: OSRuntimeConfig | dict[str, Any] | None = None, risk_config: dict[str, Any] | None = None):
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.risk_config = risk_config or self.config.risk.to_dict()

    def interpret(
        self,
        *,
        task_context: TaskContextView,
        agent_context: AgentContextView,
        events: list[Any] | None = None,
        authorization_map: Any = None,
        relationships: list[Any] | None = None,
    ) -> SignalSet:
        event_refs = [_event_ref(event) for event in (events or [])]
        event_views = [_event_view(event, ref, index) for index, (event, ref) in enumerate(zip(events or [], event_refs))]
        event_views.sort(key=lambda item: (item["timestamp"], item["index"], item["event_id"], item["event_type"]))

        signals: dict[str, list[dict[str, Any]]] = {key: [] for key in SIGNAL_KEYS}
        signals["needs"].extend(self._need_signals(task_context, event_views))
        signals["world_opportunities"].extend(self._world_opportunity_signals(event_views))
        signals["risks"].extend(self._risk_signals(task_context, event_views))
        signals["world_authorization"].extend(
            self._authorization_signals(task_context, agent_context, event_views, authorization_map)
        )
        signals["relationships"].extend(self._relationship_signals(relationships or [], event_views))
        signals["resources"].extend(self._resource_signals(task_context, agent_context))
        signals["feedback"].extend(self._feedback_signals(event_views))
        signals["constraints"].extend(self._constraint_signals(task_context, agent_context))

        for key in SIGNAL_KEYS:
            signals[key] = _stable_signals(signals[key])

        return SignalSet(
            event_refs=event_refs,
            task_context=task_context,
            agent_context=agent_context,
            signals=signals,
            metadata={
                "event_count": len(event_refs),
                "rule_version": "module2.v1",
                "signal_keys": list(SIGNAL_KEYS),
            },
        )

    def _need_signals(self, task_context: TaskContextView, event_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        if task_context.user_goal:
            signals.append(
                _signal(
                    "context_user_goal",
                    "need",
                    "medium",
                    "User goal is present in task context.",
                    metadata={"goal": task_context.user_goal},
                )
            )
        if task_context.active_goal:
            signals.append(
                _signal(
                    "context_active_goal",
                    "need",
                    "medium",
                    "Active goal is present in task context.",
                    metadata={"goal": task_context.active_goal},
                )
            )
        for event in event_views:
            text = event["text"]
            metadata = event["metadata"]
            event_type = event["event_type"]
            if event_type == "os_runtime_continuation":
                signals.append(
                    _signal(
                        "continuation_need",
                        "need",
                        "medium",
                        "Explicit runtime continuation prompt.",
                        [event["event_id"]],
                        {"event_type": event_type, "goal": str(metadata.get("goal") or "")},
                    )
                )
            elif event_type == "human_request" and _contains_any(
                text,
                ("todo", "goal", "requirement", "please", "need", "需要", "目标", "任务"),
            ):
                signals.append(
                    _signal(
                        "event_need",
                        "need",
                        "medium",
                        "Event carries a user need, TODO, or standing goal.",
                        [event["event_id"]],
                        {"event_type": event_type, "goal": str(metadata.get("goal") or "")},
                    )
                )
        return signals

    def _world_opportunity_signals(self, event_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for event in event_views:
            subject = str(event["metadata"].get("subject") or "")
            world_event_type = str(event["metadata"].get("event_type") or event["event_type"])
            text = event["text"]
            if event["source"] == EventSource.LINZ_WORLD.value and (
                subject == "wsp.mrk.requirement.published"
                or "requirement.published" in world_event_type
                or _contains_any(text, ("requirement", "broadcast", "task notification", "公开需求", "需求广播"))
            ):
                signals.append(
                    _signal(
                        "world_requirement_opportunity",
                        "world_opportunity",
                        "medium",
                        "World event advertises a requirement or task opportunity.",
                        [event["event_id"]],
                        {"subject": subject, "event_type": world_event_type},
                    )
                )
        return signals

    def _risk_signals(self, task_context: TaskContextView, event_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        task_text = f"{task_context.user_goal} {task_context.active_goal}"
        task_risk = _classify_risk(task_text, "", {})
        if task_text.strip():
            signals.append(
                _signal(
                    task_risk["code"],
                    "risk",
                    task_risk["level"],
                    task_risk["reason"],
                    metadata={"scope": "task_context", "require_approval_at": self.risk_config.get("require_approval_at", "")},
                )
            )
        for event in event_views:
            risk = _classify_risk(event["text"], event["event_type"], event["metadata"])
            if risk["code"] != "informational":
                signals.append(
                    _signal(
                        risk["code"],
                        "risk",
                        risk["level"],
                        risk["reason"],
                        [event["event_id"]],
                        {"event_type": event["event_type"]},
                    )
                )
        return signals

    def _authorization_signals(
        self,
        task_context: TaskContextView,
        agent_context: AgentContextView,
        event_views: list[dict[str, Any]],
        authorization_map: Any,
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        auth_meta = _auth_metadata(task_context, agent_context)
        login_state = auth_meta.get("login_state", LoginState.LOGGED_OUT.value)
        auth_state = _enum_value(getattr(authorization_map, "state", "")) or auth_meta.get("state", AuthState.UNKNOWN.value)

        for event in event_views:
            subject = str(event["metadata"].get("subject") or "")
            world_event_type = str(event["metadata"].get("event_type") or "")
            if event["source"] != EventSource.LINZ_WORLD.value and not subject and not world_event_type:
                continue
            if not subject or not world_event_type:
                signals.append(
                    _signal(
                        "world_authorization_unknown_subject_event_type",
                        "world_authorization",
                        "unknown",
                        "Structured subject/event_type metadata is missing.",
                        [event["event_id"]],
                        {"subject": subject, "event_type": world_event_type},
                        status="unknown",
                    )
                )
                continue
            status = "unknown"
            code = "world_authorization_unknown"
            reason = "Authorization map is unavailable or not current."
            if login_state != LoginState.LOGGED_IN.value:
                status = "blocked"
                code = "world_authorization_login_blocked"
                reason = "Linz World login is not active."
            elif auth_state != AuthState.CURRENT.value:
                status = "blocked"
                code = f"world_authorization_{auth_state}_blocked"
                reason = "Authorization map is not current."
            elif authorization_map is not None and hasattr(authorization_map, "allows_event"):
                if authorization_map.allows_event(subject, world_event_type):
                    status = "allowed"
                    code = "world_authorization_allowed"
                    reason = "Structured authorization map allows subject and event_type."
                else:
                    status = "blocked"
                    code = "world_authorization_map_blocked"
                    reason = "Structured authorization map does not allow subject and event_type."
            elif subject in auth_meta.get("allowed_publish_subjects", []) and world_event_type in auth_meta.get("allowed_publish_event_types", []):
                status = "allowed"
                code = "world_authorization_allowed"
                reason = "Context authorization metadata allows subject and event_type."
            signals.append(
                _signal(
                    code,
                    "world_authorization",
                    status,
                    reason,
                    [event["event_id"]],
                    {"subject": subject, "event_type": world_event_type, "auth_state": auth_state},
                    status=status,
                )
            )
        return signals

    def _relationship_signals(self, relationships: list[Any], event_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for item in relationships:
            rel = _plain_dict(item)
            counterparty = str(rel.get("counterparty_id") or rel.get("actor_id") or rel.get("publisher_id") or "")
            if counterparty or rel.get("relationship_id"):
                signals.append(
                    _signal(
                        "relationship_record",
                        "relationship",
                        "info",
                        "Relationship summary is available.",
                        metadata={
                            "relationship_id": str(rel.get("relationship_id") or ""),
                            "counterparty_id": counterparty,
                            "state": str(rel.get("state") or ""),
                            "summary": str(rel.get("summary") or ""),
                        },
                    )
                )
        for event in event_views:
            metadata = event["metadata"]
            counterparty = str(
                metadata.get("counterparty_id")
                or metadata.get("publisher_id")
                or metadata.get("assignee_id")
                or metadata.get("actor_id")
                or metadata.get("os_id")
                or ""
            )
            if counterparty:
                signals.append(
                    _signal(
                        "relationship_event_source",
                        "relationship",
                        "info",
                        "Event metadata identifies a relationship counterparty.",
                        [event["event_id"]],
                        {"counterparty_id": counterparty},
                    )
                )
            if (
                event["event_type"] in {"human_request", "assistant_response"}
                and _is_simple_chat_text(event["text"])
            ) or (
                _is_linz_world_chat_event(event)
                and _is_low_stakes_chat_text(event["text"])
            ):
                signals.append(
                    _signal(
                        "simple_chat_message",
                        "relationship",
                        "low",
                        "Short conversational exchange without task or side-effect intent.",
                        [event["event_id"]],
                        {
                            "event_type": event["event_type"],
                            "subject": str(metadata.get("subject") or ""),
                            "chat_kind": "linz_world_direct" if _is_linz_world_chat_event(event) else "conversation",
                        },
                    )
                )
        return signals

    def _resource_signals(self, task_context: TaskContextView, agent_context: AgentContextView) -> list[dict[str, Any]]:
        resource_state = task_context.metadata.get("resource_state", {}) if isinstance(task_context.metadata, dict) else {}
        disabled = resource_state.get("disabled_capabilities", [])
        return [
            _signal(
                "runtime_resources",
                "resource",
                "info",
                "Runtime resource state is available.",
                metadata={
                    "tool_names": sorted(task_context.tool_names),
                    "active_tools": sorted(agent_context.active_tools),
                    "capabilities": sorted(agent_context.capabilities),
                    "disabled_capabilities": sorted(str(item) for item in disabled),
                    "iteration_budget": resource_state.get("iteration_budget", {}),
                    "model_state": resource_state.get("model_state", {}),
                    "cost_state": resource_state.get("cost_state", {}),
                },
            )
        ]

    def _feedback_signals(self, event_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for event in event_views:
            text = event["text"]
            metadata = event["metadata"]
            status = str(metadata.get("status") or event["status"] or "").lower()
            event_type = event["event_type"]
            if event["source"] == EventSource.TOOL_RESULT.value and status in {"failed", "failure", "error"}:
                signals.append(
                    _signal(
                        "tool_failure_feedback",
                        "feedback",
                        "error",
                        "Tool result indicates failure.",
                        [event["event_id"]],
                        {"tool_name": str(metadata.get("tool_name") or "")},
                    )
                )
            if event_type == "runtime_feedback" or event["source"] == EventSource.RUNTIME_FEEDBACK.value:
                signals.append(
                    _signal(
                        "runtime_feedback",
                        "feedback",
                        "error" if status in {"error", "failed", "failure"} else "info",
                        "Runtime feedback event is present.",
                        [event["event_id"]],
                    )
                )
            if _contains_any(text, ("test failed", "pytest failed", "assertionerror", "失败")):
                signals.append(_signal("test_failure_feedback", "feedback", "error", "Test failure evidence is present.", [event["event_id"]]))
            if _contains_any(text, ("interrupted", "cancelled by user", "用户打断")):
                signals.append(_signal("user_interruption_feedback", "feedback", "warning", "User interruption evidence is present.", [event["event_id"]]))
            if str(metadata.get("judge_decision") or "").lower() in {"continue", "done"}:
                signals.append(
                    _signal(
                        "judge_feedback",
                        "feedback",
                        "info",
                        "Judge continuation state is present.",
                        [event["event_id"]],
                        {"decision": str(metadata.get("judge_decision"))},
                    )
                )
            if _contains_any(f"{event_type} {text}", ("settlement", "rent", "delivery", "结算", "租金", "交付")):
                signals.append(_signal("world_status_feedback", "feedback", "info", "World settlement, rent, or delivery state is present.", [event["event_id"]]))
        return signals

    def _constraint_signals(self, task_context: TaskContextView, agent_context: AgentContextView) -> list[dict[str, Any]]:
        constraints = list(task_context.constraints)
        auth_meta = _auth_metadata(task_context, agent_context)
        if auth_meta.get("state", AuthState.UNKNOWN.value) != AuthState.CURRENT.value:
            constraints.append(f"world_authorization_{auth_meta.get('state', AuthState.UNKNOWN.value)}")
        return [
            _signal(
                f"constraint_{constraint}",
                "constraint",
                "blocked",
                "Context constraint is active.",
                metadata={"constraint": constraint},
                status="blocked",
            )
            for constraint in sorted(set(constraints))
        ]


def _event_ref(event: Any) -> OSRuntimeEventRef:
    if isinstance(event, OSRuntimeEventRef):
        return event
    if hasattr(event, "to_ref"):
        return event.to_ref()
    if isinstance(event, dict):
        return OSRuntimeEventRef(
            event_id=str(event.get("event_id") or ""),
            source=_event_source(event.get("source", EventSource.SYSTEM.value)),
            trace_id=str(event.get("trace_id") or ""),
            session_id=str(event.get("session_id") or ""),
            timestamp=str(event.get("timestamp") or ""),
            summary=str(event.get("summary") or ""),
            metadata=dict(event.get("metadata") or {}),
        )
    return OSRuntimeEventRef(
        event_id=str(getattr(event, "event_id", "")),
        source=_event_source(getattr(event, "source", EventSource.SYSTEM)),
        trace_id=str(getattr(event, "trace_id", "")),
        session_id=str(getattr(event, "session_id", "")),
        timestamp=str(getattr(event, "timestamp", "")),
        summary=str(getattr(event, "summary", "")),
        metadata=dict(getattr(event, "metadata", {}) or {}),
    )


def _event_view(event: Any, ref: OSRuntimeEventRef, index: int) -> dict[str, Any]:
    metadata = dict(getattr(event, "metadata", ref.metadata) or {})
    event_type = str(getattr(event, "event_type", "") or metadata.get("event_type") or "")
    source = getattr(ref.source, "value", ref.source)
    return {
        "index": index,
        "event_id": ref.event_id,
        "event_type": event_type,
        "source": str(source),
        "timestamp": ref.timestamp,
        "summary": ref.summary,
        "text": str(ref.summary).lower(),
        "metadata": metadata,
        "status": str(getattr(event, "status", "") or metadata.get("status") or ""),
    }


def _classify_risk(text: str, event_type: str, metadata: dict[str, Any]) -> dict[str, str]:
    haystack = f"{event_type} {text} {metadata.get('tool_name', '')}".lower()
    if _contains_any(haystack, ("approval", "credential", "secret", "token", "private key", "审批")):
        return {"code": "approval_sensitive", "level": RiskLevel.CRITICAL.value, "reason": "Approval-sensitive or credential-related surface."}
    if _contains_any(haystack, ("send_message", "external message", "telegram", "discord", "slack", "world_event_published", "publish", "外部消息")):
        return {"code": "external_message", "level": RiskLevel.HIGH.value, "reason": "External platform message or world publish surface."}
    if _contains_any(haystack, ("network", "http", "browser", "web", "download", "upload", "curl")):
        return {"code": "network_send", "level": RiskLevel.HIGH.value, "reason": "Network or remote I/O surface."}
    if _contains_any(haystack, ("terminal", "shell", "command", "apply_patch", "file write", "write_file", "edit", "code", "pytest", "代码", "文件写入")):
        return {"code": "local_change", "level": RiskLevel.MEDIUM.value, "reason": "Local file, code, test, or terminal change surface."}
    if _contains_any(haystack, ("doc", "document", "summarize", "read", "explain", "文档", "摘要")):
        return {"code": "low_risk_document", "level": RiskLevel.LOW.value, "reason": "Low-risk documentation or read-only task surface."}
    return {"code": "informational", "level": RiskLevel.LOW.value, "reason": "No higher-risk surface detected."}


def _is_simple_chat_text(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if _contains_any(
        normalized,
        (
            "todo",
            "goal",
            "requirement",
            "please",
            "need",
            "http",
            "browser",
            "download",
            "upload",
            "curl",
            "terminal",
            "shell",
            "command",
            "apply_patch",
            "write_file",
            "edit",
            "code",
            "pytest",
            "delete",
            "remove",
            "commit",
            "push",
            "deploy",
            "需要",
            "目标",
            "任务",
            "代码",
            "文件",
            "删除",
            "删",
            "文件写入",
            "审批",
            "外部消息",
        ),
    ):
        return False
    if normalized in {
        "hello",
        "hi",
        "ok",
        "okay",
        "thanks",
        "thank you",
        "你好",
        "您好",
        "谢谢",
        "测试",
        "收到",
    }:
        return True
    return _contains_any(
        normalized,
        (
            "thank you",
            "你好",
            "您好",
            "谢谢",
            "测试",
            "收到",
            "正常通信",
            "可以帮你",
        ),
    )


def _is_linz_world_chat_event(event: dict[str, Any]) -> bool:
    if event["source"] != EventSource.LINZ_WORLD.value:
        return False
    metadata = event["metadata"]
    subject = str(metadata.get("subject") or "")
    event_type = str(metadata.get("event_type") or event["event_type"] or "")
    if subject == "wsp.chat.message.sent" and event_type == "message.sent":
        return True
    return _is_direct_inbox_subject(subject) and event_type == "wsp.chat.message.sent"


def _is_direct_inbox_subject(subject: str) -> bool:
    if not subject.startswith("wsp."):
        return False
    inbox_name = subject.removeprefix("wsp.")
    return subject.count(".") == 1 and bool(inbox_name) and inbox_name not in {"chat", "sys", "task", "mrk"}


def _is_low_stakes_chat_text(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    if len(normalized) > 700:
        return False
    return not _contains_any(
        normalized,
        (
            "todo",
            "goal",
            "requirement",
            "please",
            "need",
            "http",
            "browser",
            "download",
            "upload",
            "curl",
            "terminal",
            "shell",
            "command",
            "apply_patch",
            "write_file",
            "edit",
            "code",
            "pytest",
            "delete",
            "remove",
            "commit",
            "push",
            "deploy",
            "settlement",
            "rent",
            "approval",
            "credential",
            "secret",
            "token",
            "需求",
            "目标",
            "任务",
            "代码",
            "文件",
            "删除",
            "删",
            "审批",
            "结算",
            "租金",
            "凭证",
            "密钥",
            "令牌",
            "外部消息",
        ),
    )


def _auth_metadata(task_context: TaskContextView, agent_context: AgentContextView) -> dict[str, Any]:
    task_auth = task_context.metadata.get("authorization", {}) if isinstance(task_context.metadata, dict) else {}
    agent_auth = agent_context.metadata.get("authorization", {}) if isinstance(agent_context.metadata, dict) else {}
    merged = dict(task_auth)
    merged.update(agent_auth)
    return merged


def _signal(
    code: str,
    signal_type: str,
    level: str,
    reason: str,
    evidence_event_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    status: str = "",
) -> dict[str, Any]:
    payload = {
        "code": code,
        "type": signal_type,
        "level": level,
        "reason": reason,
        "evidence_event_ids": sorted(str(item) for item in (evidence_event_ids or []) if item),
        "metadata": _plain_value(metadata or {}),
    }
    if status:
        payload["status"] = status
    return payload


def _stable_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals = [_plain_value(signal) for signal in signals]
    signals.sort(
        key=lambda signal: (
            str(signal.get("code") or ""),
            ",".join(signal.get("evidence_event_ids") or []),
            str(signal.get("level") or ""),
            str(signal.get("status") or ""),
        )
    )
    return signals


def _plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {str(key): _plain_value(item) for key, item in vars(value).items() if not key.startswith("_")}
    return {"value": _plain_value(value)}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    return value


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value) if value else ""


def _event_source(value: Any) -> EventSource:
    if isinstance(value, EventSource):
        return value
    try:
        return EventSource(str(value))
    except ValueError:
        return EventSource.SYSTEM


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


__all__ = ["SIGNAL_KEYS", "SignalInterpreter"]
