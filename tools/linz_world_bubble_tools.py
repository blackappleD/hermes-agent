"""Semantic tools for Linz World Bubble Protocol operations."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from agent.linz_world import auth, identity
from agent.linz_world.api_client import LinzWorldServiceError
from agent.linz_world.bubble_client import default_bubble_client
from agent.linz_world.bubble_models import BubbleMountRecord, BubbleRecord
from agent.linz_world.bubble_receipts import BubbleReceipt
from agent.linz_world.config import load_linz_world_config
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.models import LoginState, ReceiptStatus, to_plain
from tools.registry import registry


_MUTATION_CONFIRMATION_DESCRIPTION = (
    "Set to true only when the user explicitly approved this exact remote "
    "Bubble Protocol state mutation."
)


def _result(data: Any) -> str:
    return json.dumps(to_plain(data), ensure_ascii=False, sort_keys=True)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _mutation_confirmed(args: dict[str, Any]) -> bool:
    return bool(args.get("confirm_mutation") or args.get("user_confirmed"))


def _reject(action: str, code: str, message: str, *, repo: LinzStateRepository | None = None) -> str:
    receipt = BubbleReceipt(
        request_id=uuid.uuid4().hex,
        action=action,
        status=ReceiptStatus.REJECTED,
        governance_code=code,
        message=message,
    )
    if repo is not None:
        _append_receipt(repo, receipt)
    return _result({"success": False, "status": receipt.status.value, "receipt": receipt})


def _failure(action: str, message: str, *, repo: LinzStateRepository | None = None) -> str:
    receipt = BubbleReceipt(
        request_id=uuid.uuid4().hex,
        action=action,
        status=ReceiptStatus.FAILED,
        message=message,
    )
    if repo is not None:
        _append_receipt(repo, receipt)
    return _result({"success": False, "status": receipt.status.value, "receipt": receipt})


def _append_receipt(repo: LinzStateRepository, receipt: BubbleReceipt) -> None:
    try:
        repo.append_list("bubble_receipts", receipt)
    except Exception:
        pass
    try:
        from agent.os_runtime.adapters.bubble import project_bubble_receipt

        project_bubble_receipt(
            receipt,
            metadata={"context_source": "tools.linz_world_bubble_tools"},
        )
    except Exception:
        return


def _prepare(action: str, args: dict[str, Any], *, mutation: bool):
    cfg = load_linz_world_config()
    if not cfg.enabled:
        return None, _reject(action, "linz_world_disabled", "Linz World integration is disabled.")
    if not cfg.bubble.enabled:
        return None, _reject(action, "bubble_disabled", "Linz World Bubble Protocol integration is disabled.")
    if mutation:
        if cfg.bubble.read_only or not cfg.bubble.allow_mutations:
            return None, _reject(
                action,
                "bubble_mutations_disabled",
                "Bubble Protocol mutations are disabled by linz_world.bubble configuration.",
            )
        if cfg.bubble.require_approval_for_mutations and not _mutation_confirmed(args):
            return None, _reject(
                action,
                "bubble_mutation_approval_required",
                "Bubble Protocol mutation requires explicit user confirmation.",
            )

    repo = LinzStateRepository()
    current_identity = identity.ensure_original_spirit_identity(repo)
    if not current_identity or not current_identity.is_complete():
        return None, _reject(
            action,
            "identity_missing",
            current_identity.last_error or "Linz World identity is not registered.",
            repo=repo,
        )
    session = auth.ensure_login_session(repo)
    if session.state != LoginState.LOGGED_IN or not session.token_ref:
        return None, _reject(
            action,
            "login_missing",
            session.last_error or "Linz World login session is missing.",
            repo=repo,
        )
    try:
        client = default_bubble_client()
    except Exception as exc:
        return None, _failure(action, f"Linz World Bubble client unavailable: {exc}", repo=repo)
    return {
        "config": cfg,
        "repo": repo,
        "identity": current_identity,
        "session": session,
        "client": client,
    }, ""


def linz_bubble_snapshot(args=None, **kwargs) -> str:
    args = args or {}
    action = "bubble.snapshot"
    prepared, error = _prepare(action, args, mutation=False)
    if error:
        return error
    bubble_id = str(args.get("bubble_id") or "").strip()
    if not bubble_id:
        return _reject(action, "invalid_request", "bubble_id is required.", repo=prepared["repo"])
    try:
        snapshot = prepared["client"].get_snapshot(
            bubble_id,
            token_ref=prepared["session"].token_ref,
        )
    except Exception as exc:
        return _failure(action, f"Linz World Bubble snapshot failed: {exc}", repo=prepared["repo"])
    cfg = prepared["config"].bubble
    return _result(
        {
            "success": True,
            "bubble_id": snapshot.bubble.bubble_id or bubble_id,
            "lifecycle_state": snapshot.bubble.lifecycle_state,
            "snapshot": snapshot.summary(
                max_events=cfg.snapshot_context_max_events,
                max_residues=cfg.snapshot_context_max_residues,
            ),
        }
    )


def _execute_mutation(
    action: str,
    args: dict[str, Any],
    call: Callable[[dict[str, Any]], BubbleRecord | BubbleMountRecord],
) -> str:
    prepared, error = _prepare(action, args, mutation=True)
    if error:
        return error
    try:
        data = call(prepared)
    except LinzWorldServiceError as exc:
        return _failure(action, exc.message, repo=prepared["repo"])
    except Exception as exc:
        return _failure(action, f"Linz World Bubble mutation failed: {exc}", repo=prepared["repo"])

    receipt = _success_receipt(action, data)
    _append_receipt(prepared["repo"], receipt)
    return _result({"success": True, "status": receipt.status.value, "receipt": receipt})


def _success_receipt(action: str, data: BubbleRecord | BubbleMountRecord) -> BubbleReceipt:
    if isinstance(data, BubbleMountRecord):
        return BubbleReceipt(
            request_id=uuid.uuid4().hex,
            action=action,
            status=ReceiptStatus.PUBLISHED,
            bubble_id=data.task_bubble_id,
            target_bubble_id=data.mounted_bubble_id,
            mount_id=data.mount_id,
            result_summary=f"mount {data.mount_id} is {data.mount_state}",
            receipt=data.summary(),
        )
    return BubbleReceipt(
        request_id=uuid.uuid4().hex,
        action=action,
        status=ReceiptStatus.PUBLISHED,
        bubble_id=data.bubble_id,
        lifecycle_state=data.lifecycle_state,
        result_summary=f"bubble {data.bubble_id} is {data.lifecycle_state}",
        receipt=data.summary(),
    )


def linz_bubble_create_demand(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].create_demand(
            name=str(args.get("name") or ""),
            goal=str(args.get("goal") or ""),
            publisher_os_id=str(args.get("publisher_os_id") or current_identity.os_id),
            publisher_os_name=str(args.get("publisher_os_name") or current_identity.os_name),
            budget_amount=str(args.get("budget_amount") or ""),
            priority=str(args.get("priority") or ""),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.create_demand", args, call)


def linz_bubble_accept_demand(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].accept_demand(
            demand_bubble_id=str(args.get("demand_bubble_id") or args.get("bubble_id") or ""),
            tech_lead_os_id=str(args.get("tech_lead_os_id") or current_identity.os_id),
            tech_lead_os_name=str(args.get("tech_lead_os_name") or current_identity.os_name),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.accept_demand", args, call)


def linz_bubble_create_task(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].create_task(
            parent_bubble_id=str(args.get("parent_bubble_id") or args.get("demand_bubble_id") or ""),
            name=str(args.get("name") or ""),
            goal=str(args.get("goal") or ""),
            tech_lead_os_id=str(args.get("tech_lead_os_id") or current_identity.os_id),
            slots=_dict_list(args.get("slots")),
            membrane=args.get("membrane") if isinstance(args.get("membrane"), dict) else None,
            acceptance=args.get("acceptance") if isinstance(args.get("acceptance"), dict) else None,
            dissolution_contract=args.get("dissolution_contract") if isinstance(args.get("dissolution_contract"), dict) else None,
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.create_task", args, call)


def linz_bubble_request_mount(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        slot_id = str(args.get("slot_id") or ctx["config"].bubble.default_task_slot_id)
        return ctx["client"].request_mount(
            task_bubble_id=str(args.get("task_bubble_id") or args.get("bubble_id") or ""),
            mounted_bubble_id=str(args.get("mounted_bubble_id") or current_identity.os_id),
            slot_id=slot_id,
            requester_os_id=str(args.get("requester_os_id") or current_identity.os_id),
            relation_role=str(args.get("relation_role") or ""),
            request_note=str(args.get("request_note") or ""),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.request_mount", args, call)


def linz_bubble_review_mount(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].review_mount(
            mount_id=str(args.get("mount_id") or ""),
            reviewer_os_id=str(args.get("reviewer_os_id") or current_identity.os_id),
            approved=bool(args.get("approved")),
            reject_reason=str(args.get("reject_reason") or ""),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.review_mount", args, call)


def linz_bubble_submit_artifact(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].submit_task_artifact(
            task_bubble_id=str(args.get("task_bubble_id") or args.get("bubble_id") or ""),
            mount_id=str(args.get("mount_id") or ""),
            actor_os_id=str(args.get("actor_os_id") or current_identity.os_id),
            artifact_ref=str(args.get("artifact_ref") or ""),
            delivery_note=str(args.get("delivery_note") or ""),
            evidence_refs=_string_list(args.get("evidence_refs")),
            known_issues=str(args.get("known_issues") or ""),
            next_action=str(args.get("next_action") or ""),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.submit_artifact", args, call)


def linz_bubble_review_task_acceptance(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].review_task_acceptance(
            task_bubble_id=str(args.get("task_bubble_id") or args.get("bubble_id") or ""),
            reviewer_os_id=str(args.get("reviewer_os_id") or current_identity.os_id),
            approved=bool(args.get("approved")),
            reason=str(args.get("reason") or ""),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.review_task_acceptance", args, call)


def linz_bubble_submit_demand_delivery(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].submit_demand_delivery(
            demand_bubble_id=str(args.get("demand_bubble_id") or args.get("bubble_id") or ""),
            tech_lead_os_id=str(args.get("tech_lead_os_id") or current_identity.os_id),
            summary_ref=str(args.get("summary_ref") or ""),
            summary_note=str(args.get("summary_note") or ""),
            evidence_refs=_string_list(args.get("evidence_refs")),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.submit_demand_delivery", args, call)


def linz_bubble_review_demand_acceptance(args=None, **kwargs) -> str:
    args = args or {}

    def call(ctx):
        current_identity = ctx["identity"]
        return ctx["client"].review_demand_acceptance(
            demand_bubble_id=str(args.get("demand_bubble_id") or args.get("bubble_id") or ""),
            reviewer_os_id=str(args.get("reviewer_os_id") or current_identity.os_id),
            approved=bool(args.get("approved")),
            reason=str(args.get("reason") or ""),
            token_ref=ctx["session"].token_ref,
        )

    return _execute_mutation("bubble.review_demand_acceptance", args, call)


def _confirm_property() -> dict[str, Any]:
    return {"type": "boolean", "description": _MUTATION_CONFIRMATION_DESCRIPTION}


registry.register(
    name="linz_bubble_snapshot",
    toolset="linz_bubble",
    schema={
        "description": "Read a Linz World Bubble Protocol snapshot by known bubble_id. This is read-only.",
        "parameters": {
            "type": "object",
            "required": ["bubble_id"],
            "properties": {"bubble_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_snapshot,
    description="Read Linz World bubble snapshot",
)

registry.register(
    name="linz_bubble_create_demand",
    toolset="linz_bubble",
    schema={
        "description": "Create a remote Linz World DemandBubble. This mutates remote Bubble Protocol state and requires explicit user confirmation plus enabled mutations.",
        "parameters": {
            "type": "object",
            "required": ["name", "goal", "confirm_mutation"],
            "properties": {
                "name": {"type": "string"},
                "goal": {"type": "string"},
                "publisher_os_id": {"type": "string"},
                "publisher_os_name": {"type": "string"},
                "budget_amount": {"type": "string"},
                "priority": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_create_demand,
    description="Create Linz World DemandBubble",
)

registry.register(
    name="linz_bubble_accept_demand",
    toolset="linz_bubble",
    schema={
        "description": "Accept and activate a Linz World DemandBubble as tech lead. This mutates remote state and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["demand_bubble_id", "confirm_mutation"],
            "properties": {
                "demand_bubble_id": {"type": "string"},
                "tech_lead_os_id": {"type": "string"},
                "tech_lead_os_name": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_accept_demand,
    description="Accept Linz World DemandBubble",
)

registry.register(
    name="linz_bubble_create_task",
    toolset="linz_bubble",
    schema={
        "description": "Create a TaskBubble under an active DemandBubble. This mutates remote Bubble Protocol state and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["parent_bubble_id", "name", "goal", "confirm_mutation"],
            "properties": {
                "parent_bubble_id": {"type": "string"},
                "name": {"type": "string"},
                "goal": {"type": "string"},
                "tech_lead_os_id": {"type": "string"},
                "slots": {"type": "array", "items": {"type": "object"}},
                "membrane": {"type": "object"},
                "acceptance": {"type": "object"},
                "dissolution_contract": {"type": "object"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_create_task,
    description="Create Linz World TaskBubble",
)

registry.register(
    name="linz_bubble_request_mount",
    toolset="linz_bubble",
    schema={
        "description": "Request mounting an Agent/Skill/Rule/Evidence bubble into a TaskBubble slot. This mutates remote state and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["task_bubble_id", "mounted_bubble_id", "confirm_mutation"],
            "properties": {
                "task_bubble_id": {"type": "string"},
                "mounted_bubble_id": {"type": "string"},
                "slot_id": {"type": "string"},
                "relation_role": {"type": "string"},
                "requester_os_id": {"type": "string"},
                "request_note": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_request_mount,
    description="Request Linz World Bubble mount",
)

registry.register(
    name="linz_bubble_review_mount",
    toolset="linz_bubble",
    schema={
        "description": "Approve or reject a pending Bubble mount. This mutates remote state and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["mount_id", "approved", "confirm_mutation"],
            "properties": {
                "mount_id": {"type": "string"},
                "reviewer_os_id": {"type": "string"},
                "approved": {"type": "boolean"},
                "reject_reason": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_review_mount,
    description="Review Linz World Bubble mount",
)

registry.register(
    name="linz_bubble_submit_artifact",
    toolset="linz_bubble",
    schema={
        "description": "Submit an artifact to an active TaskBubble mount. This mutates remote state and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["task_bubble_id", "mount_id", "artifact_ref", "delivery_note", "confirm_mutation"],
            "properties": {
                "task_bubble_id": {"type": "string"},
                "mount_id": {"type": "string"},
                "actor_os_id": {"type": "string"},
                "artifact_ref": {"type": "string"},
                "delivery_note": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "known_issues": {"type": "string"},
                "next_action": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_submit_artifact,
    description="Submit Linz World TaskBubble artifact",
)

registry.register(
    name="linz_bubble_review_task_acceptance",
    toolset="linz_bubble",
    schema={
        "description": "Approve or reject TaskBubble acceptance. This can dissolve/archive the remote task and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["task_bubble_id", "approved", "confirm_mutation"],
            "properties": {
                "task_bubble_id": {"type": "string"},
                "reviewer_os_id": {"type": "string"},
                "approved": {"type": "boolean"},
                "reason": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_review_task_acceptance,
    description="Review Linz World TaskBubble acceptance",
)

registry.register(
    name="linz_bubble_submit_demand_delivery",
    toolset="linz_bubble",
    schema={
        "description": "Submit DemandBubble delivery summary. This mutates remote state and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["demand_bubble_id", "summary_ref", "summary_note", "confirm_mutation"],
            "properties": {
                "demand_bubble_id": {"type": "string"},
                "tech_lead_os_id": {"type": "string"},
                "summary_ref": {"type": "string"},
                "summary_note": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_submit_demand_delivery,
    description="Submit Linz World DemandBubble delivery",
)

registry.register(
    name="linz_bubble_review_demand_acceptance",
    toolset="linz_bubble",
    schema={
        "description": "Approve or reject DemandBubble acceptance. This can dissolve/archive the remote demand and requires confirmation.",
        "parameters": {
            "type": "object",
            "required": ["demand_bubble_id", "approved", "confirm_mutation"],
            "properties": {
                "demand_bubble_id": {"type": "string"},
                "reviewer_os_id": {"type": "string"},
                "approved": {"type": "boolean"},
                "reason": {"type": "string"},
                "confirm_mutation": _confirm_property(),
            },
            "additionalProperties": False,
        },
    },
    handler=linz_bubble_review_demand_acceptance,
    description="Review Linz World DemandBubble acceptance",
)
