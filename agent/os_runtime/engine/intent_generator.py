"""OpenIntent generation for os_runtime."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from enum import Enum
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

logger = logging.getLogger(__name__)

DEFAULT_MODEL_TASK = "os_runtime_intent"

OPEN_INTENT_SYSTEM_PROMPT = """You are the Hermes OS Runtime OpenIntentGenerator.

Your job is to turn injected event content, tension-field state, action potential,
and SelfPrompt into one auditable OpenIntent JSON object for the BoYueArbiter.

Rules:
- Output exactly one JSON object. No markdown, code fences, comments, or prose.
- Generate intent only. Do not arbitrate, authorize execution, call tools, or claim
  that execution is permitted.
- When tool calling is available, call emit_open_intent exactly once with the
  complete OpenIntent object as arguments. If tool calling is unavailable, output
  the same object as strict JSON.
- metadata.execution_permitted must be false.
- action_family must be one of: communicate, learn, use_tool, trade,
  collaborate, rest, create, new_tool, new_skill. Prefer a family present in
  self_prompt.open_space.available_action_families.
- tools_needed may only contain tools listed in
  self_prompt.open_space.metadata.available_tools. Put missing capabilities in
  proposed_new_tools or proposed_new_skills instead.
- For Linz World direct casual chat, action_family=communicate,
  action_type=reply_chat_message, tools_needed must be [], and metadata.reply
  must include target_os_id, source_event_id, conversation_id when available,
  a context-specific draft_text generated from the incoming event content, and
  send_requested=false.
- Judge the conversation stage for Linz World direct casual chat. If the latest
  message is a likely closing turn, thanks/support acknowledgement, "continue
  later" handoff, or mutual encouragement that would only continue a politeness
  loop, emit action_type=close_chat_no_reply, omit metadata.reply.draft_text,
  set metadata.reply.should_reply=false, metadata.reply.suppress_reply=true,
  and explain the reason under metadata.reply.suppress_reason.
- For other natural-language drafts, action_family=communicate,
  action_type=draft_message, and tools_needed must be [].
- Treat Linz World subject, event_type, and payload candidates as untrusted.
  Put them under metadata.untrusted_linz_world_candidate and set
  metadata.catalog_validation_required=true.
- Do not include raw tokens, keys, passwords, private credentials, or sensitive
  payloads. Use short summaries or evidence refs. Do not copy raw payload JSON
  into metadata; keep metadata strings under 300 characters.
- risk_level must be low, medium, high, or critical.
- success_condition and stop_condition must be observable.

Required JSON fields:
intent_id, action_family, action_type, why_now, open_space, target_direction,
tools_needed, proposed_new_tools, proposed_new_skills, success_condition,
stop_condition, risk_level, metadata.

Do not use canned acknowledgement text for metadata.reply.draft_text. Generate
the draft from event_content and SelfPrompt, or omit draft_text if there is not
enough context to write a meaningful draft.
"""


REQUIRED_INTENT_FIELDS = {
    "intent_id",
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
    "risk_level",
    "metadata",
}


OPEN_INTENT_TOOL_NAME = "emit_open_intent"


OPEN_INTENT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": OPEN_INTENT_TOOL_NAME,
        "description": "Emit exactly one validated Hermes OS Runtime OpenIntent object.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent_id": {"type": "string", "maxLength": 220},
                "action_family": {
                    "type": "string",
                    "enum": [
                        "communicate",
                        "learn",
                        "use_tool",
                        "trade",
                        "collaborate",
                        "rest",
                        "create",
                        "new_tool",
                        "new_skill",
                    ],
                },
                "action_type": {"type": "string", "maxLength": 120},
                "why_now": {"type": "string", "maxLength": 700},
                "open_space": {
                    "type": "object",
                    "properties": {
                        "space_id": {"type": "string", "maxLength": 220},
                        "description": {"type": "string", "maxLength": 500},
                        "available_action_families": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 12,
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 240},
                            "maxItems": 16,
                        },
                        "metadata": {"type": "object"},
                    },
                    "required": ["space_id", "available_action_families", "constraints", "metadata"],
                },
                "target_direction": {
                    "type": "object",
                    "properties": {
                        "direction_id": {"type": "string", "maxLength": 220},
                        "description": {"type": "string", "maxLength": 500},
                        "success_condition": {"type": "string", "maxLength": 500},
                        "stop_condition": {"type": "string", "maxLength": 500},
                        "priority": {"type": "number"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["description", "success_condition", "stop_condition"],
                },
                "tools_needed": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 80},
                    "maxItems": 8,
                },
                "proposed_new_tools": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 120},
                    "maxItems": 8,
                },
                "proposed_new_skills": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 120},
                    "maxItems": 8,
                },
                "success_condition": {"type": "string", "maxLength": 600},
                "stop_condition": {"type": "string", "maxLength": 600},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "metadata": {"type": "object"},
            },
            "required": [
                "intent_id",
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
                "risk_level",
                "metadata",
            ],
        },
    },
}


class OpenIntentGenerator:
    """Generate auditable intents without producing execution permission."""

    rule_version = "open_intent_generator.v1"

    def __init__(
        self,
        *,
        model_task: str = DEFAULT_MODEL_TASK,
        llm_caller: Callable[..., Any] | None = None,
        prefer_llm: bool = False,
        max_tokens: int = 3000,
        timeout: float = 30.0,
    ) -> None:
        self.model_task = model_task or DEFAULT_MODEL_TASK
        self.llm_caller = llm_caller
        self.prefer_llm = prefer_llm
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(
        self,
        *,
        self_prompt: SelfPrompt,
        action_potential: ActionPotential | None = None,
        llm_json: str | dict[str, Any] | None = None,
        prefer_llm: bool | None = None,
        event_content: Any = None,
        tension_field: Any = None,
    ) -> OpenIntent:
        potential = action_potential or ActionPotential()
        use_llm = self.prefer_llm if prefer_llm is None else prefer_llm
        if use_llm:
            llm_raw_response = None
            if llm_json is None:
                try:
                    llm_json = self._call_llm(
                        self_prompt=self_prompt,
                        action_potential=potential,
                        event_content=event_content,
                        tension_field=tension_field,
                    )
                except Exception as exc:
                    logger.debug("os_runtime OpenIntent LLM call failed: %s", exc, exc_info=True)
                    return self._rule_intent(
                        self_prompt,
                        potential,
                        event_content=event_content,
                        fallback_reason=f"llm_call_failed:{type(exc).__name__}",
                    )
            llm_raw_response = _raw_response_for_metadata(llm_json)
            parsed = self._from_llm_json(
                self_prompt,
                potential,
                llm_json,
                llm_raw_response=llm_raw_response,
                event_content=event_content,
            )
            if isinstance(parsed, OpenIntent):
                return parsed
            return self._rule_intent(
                self_prompt,
                potential,
                event_content=event_content,
                fallback_reason=parsed,
                llm_raw_response=llm_raw_response,
            )
        return self._rule_intent(self_prompt, potential, event_content=event_content)

    def _from_llm_json(
        self,
        self_prompt: SelfPrompt,
        potential: ActionPotential,
        llm_json: str | dict[str, Any],
        *,
        llm_raw_response: str = "",
        event_content: Any = None,
    ) -> OpenIntent | str:
        try:
            data = _decode_json_object(llm_json)
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
        allowed_families = set((self_prompt.open_space or OpenSpace()).available_action_families)
        if allowed_families and action_family not in allowed_families:
            return f"action_family_not_allowed:{action_family.value}"
        tools_needed = _string_list(data["tools_needed"])
        allowed_tools = set(_allowed_tools(self_prompt.open_space or open_space))
        unknown_tools = [tool for tool in tools_needed if tool not in allowed_tools]
        if unknown_tools:
            return f"tools_not_allowed:{','.join(unknown_tools)}"
        if action_family == OpenActionFamily.COMMUNICATE and tools_needed:
            return "tools_not_allowed_for_communicate"
        if not isinstance(data.get("metadata"), dict):
            return "invalid_metadata"

        metadata = _sanitize_metadata(data)
        action_type = str(data["action_type"])
        reply = _reply_candidate_from_events(event_content)
        if reply and action_family == OpenActionFamily.COMMUNICATE and action_type in {
            "draft_message",
            "reply_chat_message",
            "close_chat_no_reply",
            "no_reply_chat_message",
        }:
            metadata["reply"] = _merge_reply_metadata(metadata.get("reply"), reply)
            action_type = "close_chat_no_reply" if _reply_suppressed(metadata["reply"]) else "reply_chat_message"
        if isinstance(metadata.get("reply"), dict) and _reply_suppressed(metadata["reply"]):
            action_type = "close_chat_no_reply"
        if isinstance(metadata.get("reply"), dict):
            metadata["reply_control"] = _reply_control_metadata(metadata["reply"])
            metadata["should_reply"] = metadata["reply_control"]["should_reply"]
        metadata.update(
            {
                "source": "llm_candidate",
                "rule_version": self.rule_version,
                "execution_permitted": False,
                "self_prompt_id": self_prompt.prompt_id,
                "action_potential_id": potential.intent_id,
                "evidence_refs": list(self_prompt.metadata.get("evidence_refs") or []),
            }
        )
        if llm_raw_response:
            metadata["llm_response"] = {
                "parse_status": "accepted",
                "raw": llm_raw_response,
            }
        return OpenIntent(
            intent_id=str(data.get("intent_id") or f"intent:{self_prompt.prompt_id or 'llm'}"),
            action_family=action_family,
            action_type=action_type,
            why_now=str(data["why_now"]),
            open_space=open_space,
            target_direction=target_direction,
            tools_needed=tools_needed,
            proposed_new_tools=_string_list(data["proposed_new_tools"]),
            proposed_new_skills=_string_list(data["proposed_new_skills"]),
            success_condition=str(data["success_condition"]),
            stop_condition=str(data["stop_condition"]),
            risk_level=_risk_level(data.get("risk_level"), potential),
            metadata=metadata,
        )

    def _call_llm(
        self,
        *,
        self_prompt: SelfPrompt,
        action_potential: ActionPotential,
        event_content: Any,
        tension_field: Any,
    ) -> str:
        messages = _build_llm_messages(
            self_prompt=self_prompt,
            action_potential=action_potential,
            event_content=event_content,
            tension_field=tension_field,
        )
        caller = self.llm_caller or _default_llm_caller
        call_kwargs = {
            "task": self.model_task,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
        }
        try:
            response = caller(
                **call_kwargs,
                tools=[OPEN_INTENT_TOOL_SCHEMA],
                tool_choice={
                    "type": "function",
                    "function": {"name": OPEN_INTENT_TOOL_NAME},
                },
            )
        except Exception as exc:
            if not _is_tool_calling_unsupported_error(exc):
                raise
            logger.debug(
                "os_runtime OpenIntent tool calling unsupported; retrying strict JSON text mode: %s",
                exc,
            )
            response = caller(**call_kwargs)
        return _response_text(response)

    def _rule_intent(
        self,
        self_prompt: SelfPrompt,
        potential: ActionPotential,
        *,
        event_content: Any = None,
        fallback_reason: str = "",
        llm_raw_response: str = "",
    ) -> OpenIntent:
        open_space = self_prompt.open_space or OpenSpace()
        reply = _reply_candidate_from_events(event_content)
        target_direction = self_prompt.target_direction or TargetDirection(
            description="Clarify the next low-risk step.",
            success_condition="Produce an auditable next-step proposal.",
            stop_condition="Stop before external side effects or missing authorization.",
        )
        family = _rule_family(open_space, potential)
        action_type = "reply_chat_message" if reply and family == OpenActionFamily.COMMUNICATE else _action_type(family, open_space)
        if reply and family == OpenActionFamily.COMMUNICATE and _reply_suppressed(reply):
            action_type = "close_chat_no_reply"
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
        if reply and family == OpenActionFamily.COMMUNICATE:
            metadata["reply"] = reply
            metadata["reply_control"] = _reply_control_metadata(reply)
            metadata["should_reply"] = metadata["reply_control"]["should_reply"]
            metadata["catalog_validation_required"] = True
        if fallback_reason:
            metadata["fallback_reason"] = fallback_reason
        if llm_raw_response:
            metadata["llm_response"] = {
                "parse_status": fallback_reason or "fallback",
                "raw": llm_raw_response,
            }
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


def _build_llm_messages(
    *,
    self_prompt: SelfPrompt,
    action_potential: ActionPotential,
    event_content: Any,
    tension_field: Any,
) -> list[dict[str, str]]:
    payload = {
        "event_content": _json_value(event_content),
        "tension_field": _json_value(tension_field),
        "action_potential": action_potential.to_dict(),
        "self_prompt": self_prompt.to_dict(),
    }
    return [
        {"role": "system", "content": OPEN_INTENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def _default_llm_caller(**kwargs: Any) -> Any:
    from agent.auxiliary_client import call_llm

    return call_llm(**kwargs)


def _is_tool_calling_unsupported_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "tool_choice",
            "tools",
            "function_call",
            "function calling",
            "unsupported_parameter",
            "unsupported parameter",
            "unrecognized request argument",
        )
    )


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return str(response)
        tool_args = _tool_call_arguments(message)
        if tool_args:
            return tool_args
        return str(message.get("content") or "")
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, TypeError):
        return str(response)
    tool_args = _tool_call_arguments(message)
    if tool_args:
        return tool_args
    content = getattr(message, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(getattr(item, "text", "") or getattr(item, "content", "") or item))
        return "".join(parts)
    return str(content or "")


def _tool_call_arguments(message: Any) -> str:
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls") or []
    else:
        tool_calls = getattr(message, "tool_calls", None) or []
    for call in tool_calls:
        function = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
        if not function:
            continue
        if isinstance(function, dict):
            name = str(function.get("name") or "")
            arguments = function.get("arguments")
        else:
            name = str(getattr(function, "name", "") or "")
            arguments = getattr(function, "arguments", None)
        if name and name != OPEN_INTENT_TOOL_NAME:
            continue
        if arguments is None:
            continue
        if isinstance(arguments, dict):
            return json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return str(arguments)
    return ""


def _raw_response_for_metadata(value: Any, *, max_chars: int = 8000) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    text = text.strip()
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def _decode_json_object(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        raise TypeError("llm_json must be a string or dict")
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise TypeError("OpenIntent JSON must decode to an object")
    return data


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _sanitize_metadata(data: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = dict(data.get("metadata") or {})
    raw_metadata.pop("execution_permitted", None)
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


def _reply_candidate_from_events(event_content: Any) -> dict[str, Any]:
    all_events = _event_dicts(event_content)
    for event in _event_dicts(event_content, current_only=True):
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        source = str(event.get("source") or "").lower()
        subject = str(metadata.get("subject") or "")
        world_event_type = str(metadata.get("event_type") or event.get("event_type") or "")
        if source != "linz_world":
            continue
        if not _is_linz_world_chat_event(subject, world_event_type):
            continue
        target_os_id = _first_text(
            metadata.get("os_id"),
            metadata.get("from"),
            metadata.get("from_os_id"),
            metadata.get("sender_os_id"),
            _nested_text(metadata.get("source"), "os_id"),
            _nested_text(metadata.get("identity"), "os_id"),
        )
        if not target_os_id:
            continue
        summary = _bounded_text(event.get("summary") or metadata.get("payload_summary") or "", 300)
        conversation_id = _first_text(
            metadata.get("conversation_id"),
            metadata.get("chat_id"),
            metadata.get("thread_id"),
            metadata.get("message_id"),
        )
        reply = {
            "target_os_id": _bounded_text(target_os_id, 120),
            "target_os_name": _bounded_text(_first_text(metadata.get("os_name"), metadata.get("from_os_name")), 120),
            "conversation_id": _bounded_text(conversation_id, 180),
            "source_event_id": _bounded_text(str(event.get("event_id") or metadata.get("event_id") or ""), 180),
            "source_subject": _bounded_text(subject, 180),
            "source_event_type": _bounded_text(world_event_type, 180),
            "incoming_summary": summary,
            "send_requested": False,
        }
        close_signal = _conversation_close_signal(event, all_events)
        if close_signal:
            reply.update(close_signal)
        return reply
    return {}


def _event_dicts(value: Any, *, current_only: bool = False) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        if "current_events" in value:
            current = _event_dicts(value.get("current_events"))
            if current_only:
                return current
            recent = _event_dicts(value.get("recent_events"))
            return [*current, *recent]
        if "event_id" in value or "metadata" in value or "event_type" in value:
            return [_event_dict(value)]
        if "events" in value:
            return _event_dicts(value.get("events"))
        return [_event_dict(value)]
    if isinstance(value, (list, tuple)):
        return [_event_dict(item) for item in value]
    return [_event_dict(value)]


def _event_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    metadata = getattr(value, "metadata", {}) or {}
    return {
        "event_id": getattr(value, "event_id", ""),
        "event_type": getattr(value, "event_type", ""),
        "source": getattr(getattr(value, "source", ""), "value", getattr(value, "source", "")),
        "summary": getattr(value, "summary", ""),
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def _is_linz_world_chat_event(subject: str, event_type: str) -> bool:
    if subject == "wsp.chat.message.sent" and event_type == "message.sent":
        return True
    return subject.startswith("wsp.") and subject.count(".") == 1 and subject.removeprefix("wsp.") not in {"chat", "sys", "task", "mrk"} and event_type == "wsp.chat.message.sent"


def _merge_reply_metadata(existing: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    reply = dict(fallback)
    if isinstance(existing, dict):
        existing_suppressed = _truthy(existing.get("suppress_reply")) or _truthy(existing.get("conversation_end_detected"))
        for key in ("draft_text", "target_os_name", "conversation_id"):
            value = _bounded_text(existing.get(key), 600 if key == "draft_text" else 180)
            if value:
                reply[key] = value
        if existing_suppressed:
            _apply_reply_suppression(
                reply,
                reason=_bounded_text(existing.get("suppress_reason") or "llm_candidate_requested_no_reply", 180),
                cues=_string_list(existing.get("detected_cues") or ["llm_candidate_requested_no_reply"]),
                confidence=_float_value(existing.get("confidence"), 0.72),
            )
    if _truthy(reply.get("suppress_reply")):
        _apply_reply_suppression(
            reply,
            reason=_bounded_text(reply.get("suppress_reason") or "conversation_closing_context", 180),
            cues=_string_list(reply.get("detected_cues") or ["conversation_closing_context"]),
            confidence=_float_value(reply.get("confidence"), 0.72),
        )
    reply["send_requested"] = False
    return reply


def _reply_suppressed(reply: dict[str, Any]) -> bool:
    return _truthy(reply.get("suppress_reply")) or _truthy(reply.get("conversation_end_detected")) or reply.get("should_reply") is False


def _reply_control_metadata(reply: dict[str, Any]) -> dict[str, Any]:
    suppressed = _reply_suppressed(reply)
    return {
        "should_reply": not suppressed,
        "suppress_reply": suppressed,
        "conversation_stage": str(reply.get("conversation_stage") or ("closing" if suppressed else "open")),
        "reason": str(reply.get("suppress_reason") or ("conversation_closing_context" if suppressed else "")),
        "confidence": reply.get("confidence", 0.0),
        "detected_cues": list(reply.get("detected_cues") or []),
    }


def _conversation_close_signal(current_event: dict[str, Any], all_events: list[dict[str, Any]]) -> dict[str, Any]:
    text = _chat_text(current_event)
    if not text:
        return {}
    normalized = _normalize_chat_text(text)
    if not normalized or _has_reply_worthy_request(normalized):
        return {}
    cues = _closing_cues(normalized)
    if not cues:
        return {}
    recent_chat_count = sum(1 for event in all_events if _is_linz_world_chat_event_from_dict(event))
    confidence = 0.78
    if recent_chat_count >= 3:
        confidence += 0.08
    if any(cue in {"explicit_no_reply", "goodbye", "continue_later"} for cue in cues):
        confidence += 0.08
    return {
        "should_reply": False,
        "suppress_reply": True,
        "conversation_end_detected": True,
        "conversation_stage": "closing",
        "suppress_reason": "conversation_closing_context",
        "detected_cues": cues,
        "confidence": round(min(confidence, 0.96), 2),
    }


def _apply_reply_suppression(
    reply: dict[str, Any],
    *,
    reason: str,
    cues: list[str],
    confidence: float,
) -> None:
    reply.pop("draft_text", None)
    reply["should_reply"] = False
    reply["suppress_reply"] = True
    reply["conversation_end_detected"] = True
    reply["conversation_stage"] = "closing"
    reply["suppress_reason"] = reason or "conversation_closing_context"
    reply["detected_cues"] = cues or ["conversation_closing_context"]
    reply["confidence"] = round(max(0.0, min(float(confidence), 1.0)), 2)
    reply["send_requested"] = False


def _chat_text(event: dict[str, Any]) -> str:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    values = [
        event.get("summary"),
        metadata.get("payload_summary"),
        metadata.get("text"),
        metadata.get("content"),
        metadata.get("message"),
        metadata.get("payload"),
    ]
    parts: list[str] = []
    for value in values:
        parts.extend(_text_fragments(value))
    return " ".join(part for part in parts if part).strip()


def _text_fragments(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "message", "body", "value"):
            if key in value:
                parts.extend(_text_fragments(value.get(key)))
        if not parts:
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return parts
    if isinstance(value, list):
        parts: list[str] = []
        for item in value[:10]:
            parts.extend(_text_fragments(item))
        return parts
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("{") or text.startswith("["):
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [text]
        return _text_fragments(decoded)
    return [text]


def _normalize_chat_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _has_reply_worthy_request(normalized: str) -> bool:
    if "?" in normalized or "？" in normalized:
        return True
    return _contains_any(
        normalized,
        (
            "can you",
            "could you",
            "please",
            "help me",
            "what ",
            "why ",
            "how ",
            "when ",
            "where ",
            "let's",
            "lets ",
            "go ahead",
            "proceed",
            "帮我",
            "请",
            "需要",
            "怎么",
            "如何",
            "什么",
            "吗",
            "么",
            "任务",
            "目标",
            "需求",
            "实现",
            "修复",
            "分析",
            "解释",
            "开始",
            "开工",
            "继续讨论",
            "继续聊",
        ),
    )


def _closing_cues(normalized: str) -> list[str]:
    cues: list[str] = []
    groups = {
        "explicit_no_reply": ("no need to reply", "do not reply", "不用回复", "无需回复", "不用回"),
        "goodbye": ("goodbye", "bye", "see you", "take care", "再见", "拜拜", "晚安", "先这样", "先到这", "不打扰"),
        "continue_later": (
            "talk later",
            "catch up later",
            "reach out again",
            "feel free to reach out",
            "continue later",
            "future context",
            "not dive into",
            "回头聊",
            "下次聊",
            "以后再聊",
            "之后再聊",
            "以后继续",
            "后续再",
        ),
        "gratitude_ack": (
            "thanks",
            "thank you",
            "appreciate",
            "谢谢",
            "感谢",
            "收到",
            "辛苦",
        ),
        "encouragement_ack": (
            "加油",
            "保持动力",
            "保持学习",
            "继续保持",
            "一起成长",
            "期待你的好消息",
            "有进展",
            "及时同步",
            "随时准备继续交流",
        ),
    }
    for cue, needles in groups.items():
        if _contains_any(normalized, needles):
            cues.append(cue)
    return _dedupe_strings(cues)


def _is_linz_world_chat_event_from_dict(event: dict[str, Any]) -> bool:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    return str(event.get("source") or "").lower() == "linz_world" and _is_linz_world_chat_event(
        str(metadata.get("subject") or ""),
        str(metadata.get("event_type") or event.get("event_type") or ""),
    )


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = str(text or "").lower()
    return any(needle.lower() in lower for needle in needles)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "")
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _nested_text(value: Any, key: str) -> str:
    if isinstance(value, dict):
        return str(value.get(key) or "").strip()
    return ""


def _bounded_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _allowed_tools(open_space: OpenSpace) -> list[str]:
    return _string_list(open_space.metadata.get("available_tools") or [])


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    return [str(item) for item in value]
