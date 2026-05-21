"""Native Linz World tools."""

from __future__ import annotations

import json

from agent.linz_world import auth, identity
from agent.linz_world.chat import send_chat_message
from agent.linz_world.compute import invoke_compute
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.guide import get_section as get_linz_world_section
from agent.linz_world.guide import guide as search_linz_world_guide
from agent.linz_world.guide import resolve_flow as resolve_linz_world_flow
from agent.linz_world.memory import write_memory
from agent.linz_world.models import to_plain
from agent.linz_world.publisher import publish_event
from agent.linz_world.relationship import add_active_relationship, read_relationships
from agent.linz_world.status import events_summary, status_summary
from tools.registry import registry


def _result(data) -> str:
    return json.dumps(to_plain(data), ensure_ascii=False, sort_keys=True)


def linz_status(args=None, **kwargs) -> str:
    repo = LinzStateRepository()
    identity.ensure_original_spirit_identity(repo)
    return _result(status_summary(repo))


def linz_map(args=None, **kwargs) -> str:
    repo = LinzStateRepository()
    return _result({"success": True, "authorization": auth.refresh_authorization_map(repo)})


def linz_events_recent(args=None, **kwargs) -> str:
    args = args or {}
    limit = int(args.get("limit", 20))
    status = str(args.get("status") or "")
    return _result(events_summary(LinzStateRepository(), limit=limit, status=status or None))


def linz_publish(args=None, **kwargs) -> str:
    args = args or {}
    subject = str(args.get("subject") or "")
    event_type = str(args.get("event_type") or "")
    payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
    receipt = publish_event(subject, event_type, payload, repository=LinzStateRepository())
    return _result({"success": receipt.status.value == "published", "status": receipt.status.value, "receipt": receipt})


def linz_chat_send(args=None, **kwargs) -> str:
    args = args or {}
    to_os_id = str(args.get("to_os_id") or args.get("to") or "")
    content = str(args.get("content") or args.get("message") or "")
    to_os_name = str(args.get("to_os_name") or "")
    conversation_id = str(args.get("conversation_id") or "")
    receipt = send_chat_message(
        to_os_id,
        content,
        to_os_name=to_os_name,
        conversation_id=conversation_id,
        repository=LinzStateRepository(),
    )
    return _result({"success": receipt.status.value == "published", "status": receipt.status.value, "receipt": receipt})


def linz_compute(args=None, **kwargs) -> str:
    args = args or {}
    task = str(args.get("task") or "")
    input_data = args.get("input") if isinstance(args.get("input"), dict) else {}
    receipt = invoke_compute(task, input_data, repository=LinzStateRepository())
    return _result({"success": receipt.status.value == "published", "receipt": receipt})


def linz_memory_sink(args=None, **kwargs) -> str:
    args = args or {}
    artifact_ref = str(args.get("artifact_ref") or "")
    sink_reason = str(args.get("sink_reason") or "")
    summary = str(args.get("summary") or "")
    entry = write_memory(artifact_ref, sink_reason, summary, repository=LinzStateRepository())
    return _result({"success": entry.status.value == "published", "entry": entry})


def linz_relationship(args=None, **kwargs) -> str:
    args = args or {}
    action = str(args.get("action") or "read").strip().lower()
    counterparty_id = str(args.get("counterparty_id") or "")
    summary = str(args.get("summary") or "")
    relation_type = str(args.get("relation_type") or "OTHER")
    if action == "read":
        return _result(read_relationships(counterparty_id, repository=LinzStateRepository()))
    if action in {"add", "add_active"}:
        return _result(add_active_relationship(counterparty_id, summary, repository=LinzStateRepository(), relation_type=relation_type))
    return _result({"success": False, "error": {"code": "invalid_action", "message": "Use action=read, action=add, or action=add_active."}})


def linz_world_guide(args=None, **kwargs) -> str:
    args = args or {}
    return _result(
        search_linz_world_guide(
            query=str(args.get("query") or ""),
            subject=str(args.get("subject") or ""),
            event_type=str(args.get("event_type") or ""),
            bubble_type=str(args.get("bubble_type") or ""),
            lifecycle_state=str(args.get("lifecycle_state") or ""),
            user_intent=str(args.get("user_intent") or ""),
            limit=int(args.get("limit", 5)),
            include_content=bool(args.get("include_content", False)),
        )
    )


def linz_world_section(args=None, **kwargs) -> str:
    args = args or {}
    return _result(
        get_linz_world_section(
            str(args.get("section_id") or ""),
            max_chars=int(args.get("max_chars", 6000)),
        )
    )


def linz_world_flow_resolve(args=None, **kwargs) -> str:
    args = args or {}
    known_fields = args.get("known_fields") if isinstance(args.get("known_fields"), dict) else {}
    return _result(
        resolve_linz_world_flow(
            query=str(args.get("query") or ""),
            subject=str(args.get("subject") or ""),
            event_type=str(args.get("event_type") or ""),
            bubble_type=str(args.get("bubble_type") or ""),
            lifecycle_state=str(args.get("lifecycle_state") or ""),
            user_intent=str(args.get("user_intent") or ""),
            bubble_id=str(args.get("bubble_id") or ""),
            known_fields=known_fields,
            limit=int(args.get("limit", 5)),
        )
    )


registry.register(
    name="linz_status",
    toolset="linz_world",
    schema={"description": "Return current profile Linz World identity and status.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    handler=linz_status,
    description="Show native Linz World identity and status",
)
registry.register(
    name="linz_world_guide",
    toolset="linz_world",
    schema={
        "description": (
            "Search the Linz World runtime manual for relevant world concepts, rules, workflows, and tool guidance. "
            "Use this before answering Linz World questions or choosing Linz workflow steps from long-world knowledge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language question or context to retrieve guide sections for."},
                "subject": {"type": "string", "description": "Optional Linz World event subject."},
                "event_type": {"type": "string", "description": "Optional Linz World event_type."},
                "bubble_type": {"type": "string", "description": "Optional Bubble Protocol type, for example demand or task."},
                "lifecycle_state": {"type": "string", "description": "Optional Bubble lifecycle state."},
                "user_intent": {"type": "string", "description": "Optional normalized intent such as accept_demand, submit_artifact, or reply_chat."},
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "include_content": {"type": "boolean", "default": False, "description": "Return longer matched section snippets. Use linz_world_section for full sections."},
            },
            "additionalProperties": False,
        },
    },
    handler=linz_world_guide,
    description="Search Linz World runtime manual",
)
registry.register(
    name="linz_world_section",
    toolset="linz_world",
    schema={
        "description": "Read one Linz World runtime manual section by section_id for progressive disclosure.",
        "parameters": {
            "type": "object",
            "required": ["section_id"],
            "properties": {
                "section_id": {"type": "string", "description": "Section id returned by linz_world_guide, for example LW-MRK-REQUIREMENT."},
                "max_chars": {"type": "integer", "default": 6000, "minimum": 500, "maximum": 20000},
            },
            "additionalProperties": False,
        },
    },
    handler=linz_world_section,
    description="Read Linz World guide section",
)
registry.register(
    name="linz_world_flow_resolve",
    toolset="linz_world",
    schema={
        "description": (
            "Resolve the current Linz World workflow phase from event/bubble/user intent context. "
            "Returns matched guide sections, next steps, recommended linz tools, required fields, approval requirements, and forbidden actions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language context or user request."},
                "subject": {"type": "string", "description": "Optional Linz World event subject."},
                "event_type": {"type": "string", "description": "Optional Linz World event_type."},
                "bubble_type": {"type": "string", "description": "Optional Bubble Protocol type, for example demand or task."},
                "lifecycle_state": {"type": "string", "description": "Optional Bubble lifecycle state."},
                "user_intent": {"type": "string", "description": "Optional normalized intent such as accept_demand, submit_artifact, or reply_chat."},
                "bubble_id": {"type": "string", "description": "Known bubble id, if present."},
                "known_fields": {
                    "type": "object",
                    "description": "Fields already known for the prospective tool call, used to report missing required fields.",
                    "additionalProperties": True,
                },
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
    },
    handler=linz_world_flow_resolve,
    description="Resolve Linz World workflow phase",
)
registry.register(
    name="linz_map",
    toolset="linz_world",
    schema={"description": "Refresh and return Linz World authorization map summary.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    handler=linz_map,
    description="Refresh Linz World authorization map",
)
registry.register(
    name="linz_events_recent",
    toolset="linz_world",
    schema={"description": "Return recent Linz World events using redacted summaries.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}, "status": {"type": "string", "default": ""}}, "additionalProperties": False}},
    handler=linz_events_recent,
    description="Show recent Linz World events",
)
registry.register(
    name="linz_publish",
    toolset="linz_world",
    schema={
        "description": (
            "Advanced/raw Linz World publish escape hatch. Use semantic Linz tools such as linz_chat_send for normal user intents; "
            "use this only when the user provides a specific subject, event_type, and payload or no semantic tool covers the event. "
            "For MRK collaboration, publish only authoritative MRK subjects, not derived WSP/direct inbox notifications. "
            "Typical MRK receiver sequence: publish subject=mrk.order event_type=mrk.order.accepted with requirement_id, order_id, "
            "requester_os_id/name, worker_os_id/name; after producing the deliverable, publish subject=mrk.order.handover "
            "event_type=mrk.order.handover.delivered with order_id, requirement_id, deliverer_os_id/name, handover_version, "
            "file_ref, checksum, size, mime_type, version. Publisher-side approval uses subject=mrk.order.handover "
            "event_type=mrk.order.handover.approved. Do not manually publish wsp.mrk.* notifications; Linz World dispatches them."
        ),
        "parameters": {
            "type": "object",
            "required": ["subject", "event_type", "payload"],
            "properties": {"subject": {"type": "string"}, "event_type": {"type": "string"}, "payload": {"type": "object"}},
            "additionalProperties": False,
        },
    },
    handler=linz_publish,
    description="Advanced raw Linz World publish",
)
registry.register(
    name="linz_chat_send",
    toolset="linz_world",
    schema={
        "description": (
            "Send a Linz World chat/private message to another original spirit. "
            "Use this when the user asks to message, chat with, 私聊, 私信, or DM someone in Linz World. "
            "If content/message is missing, ask the user for the message text before calling."
        ),
        "parameters": {
            "type": "object",
            "required": ["to_os_id", "content"],
            "properties": {
                "to_os_id": {"type": "string", "description": "Recipient Linz World os_id/original spirit id."},
                "content": {"type": "string", "description": "Message text to send."},
                "to_os_name": {"type": "string", "description": "Optional recipient display name."},
                "conversation_id": {"type": "string", "description": "Optional existing conversation id."},
            },
            "additionalProperties": False,
        },
    },
    handler=linz_chat_send,
    description="Send Linz World chat/private message",
)
registry.register(
    name="linz_compute",
    toolset="linz_world",
    schema={"description": "Invoke Linz World compute using the current Linz World login token.", "parameters": {"type": "object", "required": ["task"], "properties": {"task": {"type": "string"}, "input": {"type": "object"}}, "additionalProperties": False}},
    handler=linz_compute,
    description="Invoke Linz World compute",
)
registry.register(
    name="linz_memory_sink",
    toolset="linz_world",
    schema={"description": "Write structured evidence to Soul Memory.", "parameters": {"type": "object", "required": ["artifact_ref", "sink_reason", "summary"], "properties": {"artifact_ref": {"type": "string"}, "sink_reason": {"type": "string"}, "summary": {"type": "string"}}, "additionalProperties": False}},
    handler=linz_memory_sink,
    description="Write Linz World Soul Memory",
)
registry.register(
    name="linz_relationship",
    toolset="linz_world",
    schema={
        "description": (
            "Read Linz World relationships or add another original spirit to the current profile's ACTIVE relationship list. "
            "Use action=add when the user asks to 添加关系, add a relationship, or add a target original spirit to the relationship list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "add", "add_active"], "default": "read"},
                "counterparty_id": {"type": "string", "description": "Target original spirit/os_id."},
                "relation_type": {"type": "string", "default": "OTHER", "description": "Relationship type defined by Linz World, for example FRIEND, COLLABORATOR, or OTHER."},
                "summary": {"type": "string", "description": "Short reason or summary for the relationship."},
            },
            "additionalProperties": False,
        },
    },
    handler=linz_relationship,
    description="Read or mutate Linz World relationships",
)
