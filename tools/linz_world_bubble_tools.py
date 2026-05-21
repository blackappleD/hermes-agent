"""Semantic tools for Linz World Bubble Protocol operations."""

from __future__ import annotations

import json
import re
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
from agent.linz_world.publisher import publish_event
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


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _safe_int(value: Any, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sanitize_id_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return text or uuid.uuid4().hex[:12]


def _generated_order_id(requirement_id: str) -> str:
    return f"ORD-{_sanitize_id_part(requirement_id)}-{uuid.uuid4().hex[:8]}"


def _requirement_from_task_id(task_bubble_id: str, actor_os_id: str = "") -> str:
    task_bubble_id = str(task_bubble_id or "").strip()
    if not task_bubble_id.startswith("task_"):
        return ""
    body = task_bubble_id.removeprefix("task_")
    actor_part = _sanitize_id_part(actor_os_id) if actor_os_id else ""
    suffix = f"_{actor_part}" if actor_part else ""
    if suffix and body.endswith(suffix):
        return body[: -len(suffix)]
    return ""


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


def _prepare(action: str, args: dict[str, Any], *, mutation: bool, require_client: bool = True):
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
    client = None
    if require_client:
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
    action = "mrk.requirement.published"
    prepared, error = _prepare(action, args, mutation=True, require_client=False)
    if error:
        return error
    current_identity = prepared["identity"]
    requirement_id = _first_text(args.get("requirement_id"), args.get("demand_bubble_id"), args.get("bubble_id"), f"REQ-{uuid.uuid4().hex[:12]}")
    payload: dict[str, Any] = {
        "requirement_id": requirement_id,
        "publisher_os_id": _first_text(args.get("publisher_os_id"), current_identity.os_id),
        "publisher_os_name": _first_text(args.get("publisher_os_name"), current_identity.os_name),
        "title": _first_text(args.get("title"), args.get("name")),
        "description": _first_text(args.get("description"), args.get("goal")),
        "budget_amount": _first_text(args.get("budget_amount"), "0"),
    }
    for key in ("budget_unit", "deadline_at", "target_os_id", "target_os_name"):
        value = _first_text(args.get(key))
        if value:
            payload[key] = value
    receipt = publish_event("mrk.requirement.published", "mrk.requirement.published", payload, repository=prepared["repo"])
    status = receipt.status
    bubble_receipt = BubbleReceipt(
        request_id=receipt.request_id,
        action=action,
        status=status,
        bubble_id=requirement_id,
        lifecycle_state="produced" if status == ReceiptStatus.PUBLISHED else "",
        governance_code=receipt.governance_code,
        message=receipt.message,
        result_summary="published MRK requirement; DemandBubble is bridged by Linz World" if status == ReceiptStatus.PUBLISHED else receipt.message,
        receipt={
            "bridge": "mrk_publish",
            "subject": "mrk.requirement.published",
            "event_type": "mrk.requirement.published",
            "world_event_id": receipt.world_event_id,
            "publish_receipt": to_plain(receipt),
        },
    )
    _append_receipt(prepared["repo"], bubble_receipt)
    return _result(
        {
            "success": status == ReceiptStatus.PUBLISHED,
            "status": status.value,
            "receipt": bubble_receipt,
            "publish_receipt": receipt,
            "bubble_id": requirement_id,
            "bridge": "mrk_publish",
            "subject": "mrk.requirement.published",
            "event_type": "mrk.requirement.published",
        }
    )


def linz_bubble_accept_demand(args=None, **kwargs) -> str:
    args = args or {}
    action = "mrk.order.accepted"
    prepared, error = _prepare(action, args, mutation=True, require_client=False)
    if error:
        return error
    current_identity = prepared["identity"]
    requirement_id = _first_text(args.get("requirement_id"), args.get("demand_bubble_id"), args.get("bubble_id"))
    requester_os_id = _first_text(args.get("requester_os_id"), args.get("publisher_os_id"))
    requester_os_name = _first_text(args.get("requester_os_name"), args.get("publisher_os_name"), requester_os_id)
    worker_os_id = _first_text(args.get("worker_os_id"), args.get("tech_lead_os_id"), current_identity.os_id)
    worker_os_name = _first_text(args.get("worker_os_name"), args.get("tech_lead_os_name"), current_identity.os_name)
    if not requirement_id or not requester_os_id:
        return _reject(
            action,
            "invalid_request",
            "MRK order acceptance requires requirement_id/demand_bubble_id and requester_os_id/publisher_os_id.",
            repo=prepared["repo"],
        )
    order_id = _first_text(args.get("order_id"), _generated_order_id(requirement_id))
    payload = {
        "requirement_id": requirement_id,
        "order_id": order_id,
        "requester_os_id": requester_os_id,
        "requester_os_name": requester_os_name,
        "worker_os_id": worker_os_id,
        "worker_os_name": worker_os_name,
    }
    receipt = publish_event("mrk.order", "mrk.order.accepted", payload, repository=prepared["repo"])
    status = receipt.status
    bubble_receipt = BubbleReceipt(
        request_id=receipt.request_id,
        action=action,
        status=status,
        bubble_id=requirement_id,
        lifecycle_state="active" if status == ReceiptStatus.PUBLISHED else "",
        governance_code=receipt.governance_code,
        message=receipt.message,
        result_summary="published MRK order acceptance; DemandBubble/TaskBubble bridge is handled by Linz World" if status == ReceiptStatus.PUBLISHED else receipt.message,
        receipt={
            "bridge": "mrk_publish",
            "subject": "mrk.order",
            "event_type": "mrk.order.accepted",
            "order_id": order_id,
            "world_event_id": receipt.world_event_id,
            "publish_receipt": to_plain(receipt),
        },
    )
    _append_receipt(prepared["repo"], bubble_receipt)
    return _result(
        {
            "success": status == ReceiptStatus.PUBLISHED,
            "status": status.value,
            "receipt": bubble_receipt,
            "publish_receipt": receipt,
            "bubble_id": requirement_id,
            "order_id": order_id,
            "bridge": "mrk_publish",
            "subject": "mrk.order",
            "event_type": "mrk.order.accepted",
        }
    )


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
    actor_os_id = _first_text(args.get("actor_os_id"), args.get("deliverer_os_id"))
    requirement_id = _first_text(
        args.get("requirement_id"),
        args.get("demand_bubble_id"),
        _requirement_from_task_id(str(args.get("task_bubble_id") or args.get("bubble_id") or ""), actor_os_id),
    )
    order_id = _first_text(args.get("order_id"))
    if requirement_id and order_id:
        action = "mrk.order.handover.delivered"
        prepared, error = _prepare(action, args, mutation=True, require_client=False)
        if error:
            return error
        current_identity = prepared["identity"]
        deliverer_os_id = _first_text(actor_os_id, args.get("deliverer_os_id"), current_identity.os_id)
        payload = {
            "order_id": order_id,
            "requirement_id": requirement_id,
            "deliverer_os_id": deliverer_os_id,
            "handover_version": _safe_int(args.get("handover_version") or args.get("version_no"), 1),
        }
        optional = {
            "deliverer_os_name": _first_text(args.get("deliverer_os_name"), current_identity.os_name),
            "file_ref": _first_text(args.get("file_ref"), args.get("artifact_ref")),
            "file_name": _first_text(args.get("file_name")),
            "artifact_id": _first_text(args.get("artifact_id")),
            "artifact_endpoint": _first_text(args.get("artifact_endpoint")),
            "checksum": _first_text(args.get("checksum")),
            "size": args.get("size"),
            "mime_type": _first_text(args.get("mime_type")),
            "language": _first_text(args.get("language")),
            "version": _first_text(args.get("artifact_version"), args.get("version")),
        }
        for key, value in optional.items():
            if value not in ("", None):
                payload[key] = value
        receipt = publish_event("mrk.order.handover", "mrk.order.handover.delivered", payload, repository=prepared["repo"])
        status = receipt.status
        task_id = _first_text(args.get("task_bubble_id"), args.get("bubble_id"))
        bubble_receipt = BubbleReceipt(
            request_id=receipt.request_id,
            action=action,
            status=status,
            bubble_id=task_id,
            lifecycle_state="reviewing" if status == ReceiptStatus.PUBLISHED else "",
            governance_code=receipt.governance_code,
            message=receipt.message,
            result_summary="published MRK handover delivery; TaskBubble bridge is handled by Linz World" if status == ReceiptStatus.PUBLISHED else receipt.message,
            receipt={
                "bridge": "mrk_publish",
                "subject": "mrk.order.handover",
                "event_type": "mrk.order.handover.delivered",
                "order_id": order_id,
                "requirement_id": requirement_id,
                "world_event_id": receipt.world_event_id,
                "publish_receipt": to_plain(receipt),
            },
        )
        _append_receipt(prepared["repo"], bubble_receipt)
        return _result(
            {
                "success": status == ReceiptStatus.PUBLISHED,
                "status": status.value,
                "receipt": bubble_receipt,
                "publish_receipt": receipt,
                "bridge": "mrk_publish",
                "subject": "mrk.order.handover",
                "event_type": "mrk.order.handover.delivered",
            }
        )

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
    requirement_id = _first_text(args.get("requirement_id"), args.get("demand_bubble_id"))
    order_id = _first_text(args.get("order_id"))
    if requirement_id and order_id:
        approved = bool(args.get("approved"))
        action = "mrk.order.handover.approved" if approved else "mrk.order.handover.rejected"
        prepared, error = _prepare(action, args, mutation=True, require_client=False)
        if error:
            return error
        current_identity = prepared["identity"]
        payload = {
            "order_id": order_id,
            "requirement_id": requirement_id,
            "reviewer_os_id": _first_text(args.get("reviewer_os_id"), current_identity.os_id),
            "reviewer_os_name": _first_text(args.get("reviewer_os_name"), current_identity.os_name),
            "handover_version": _safe_int(args.get("handover_version") or args.get("version_no"), 1),
        }
        if not approved:
            payload["rejection_reason"] = _first_text(args.get("reject_reason"), args.get("reason"), "rejected")
        event_type = action
        receipt = publish_event("mrk.order.handover", event_type, payload, repository=prepared["repo"])
        status = receipt.status
        bubble_receipt = BubbleReceipt(
            request_id=receipt.request_id,
            action=action,
            status=status,
            bubble_id=_first_text(args.get("task_bubble_id"), args.get("bubble_id")),
            lifecycle_state="archived" if approved and status == ReceiptStatus.PUBLISHED else "",
            governance_code=receipt.governance_code,
            message=receipt.message,
            result_summary=f"published {event_type}; TaskBubble acceptance bridge is handled by Linz World" if status == ReceiptStatus.PUBLISHED else receipt.message,
            receipt={
                "bridge": "mrk_publish",
                "subject": "mrk.order.handover",
                "event_type": event_type,
                "order_id": order_id,
                "requirement_id": requirement_id,
                "world_event_id": receipt.world_event_id,
                "publish_receipt": to_plain(receipt),
            },
        )
        _append_receipt(prepared["repo"], bubble_receipt)
        return _result(
            {
                "success": status == ReceiptStatus.PUBLISHED,
                "status": status.value,
                "receipt": bubble_receipt,
                "publish_receipt": receipt,
                "bridge": "mrk_publish",
                "subject": "mrk.order.handover",
                "event_type": event_type,
            }
        )

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
        "description": (
            "Create a Linz World DemandBubble by publishing the formal MRK requirement event. "
            "The Linz World backend bridges mrk.requirement.published into a DemandBubble; this mutates remote state and requires confirmation."
        ),
        "parameters": {
            "type": "object",
            "required": ["name", "goal", "confirm_mutation"],
            "properties": {
                "requirement_id": {"type": "string", "description": "Optional MRK requirement id; generated when omitted."},
                "name": {"type": "string"},
                "goal": {"type": "string"},
                "publisher_os_id": {"type": "string"},
                "publisher_os_name": {"type": "string"},
                "target_os_id": {"type": "string", "description": "Optional directed receiver original spirit id."},
                "target_os_name": {"type": "string"},
                "budget_amount": {"type": "string"},
                "budget_unit": {"type": "string"},
                "deadline_at": {"type": "string"},
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
        "description": (
            "Accept and activate a Linz World DemandBubble by publishing the formal mrk.order.accepted event. "
            "The Linz World backend persists the order, activates the DemandBubble, and creates/links the default MRK TaskBubble. "
            "Requires the requester/publisher identity from the requirement event."
        ),
        "parameters": {
            "type": "object",
            "required": ["demand_bubble_id", "requester_os_id", "confirm_mutation"],
            "properties": {
                "demand_bubble_id": {"type": "string"},
                "requirement_id": {"type": "string"},
                "order_id": {"type": "string"},
                "requester_os_id": {"type": "string", "description": "The original requirement publisher os_id."},
                "requester_os_name": {"type": "string"},
                "publisher_os_id": {"type": "string", "description": "Alias accepted by the handler for requester_os_id."},
                "publisher_os_name": {"type": "string"},
                "worker_os_id": {"type": "string"},
                "worker_os_name": {"type": "string"},
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
        "description": (
            "Create a TaskBubble under an active DemandBubble. This mutates remote Bubble Protocol state and requires confirmation. "
            "For an MRK requirement flow, prefer publishing the formal mrk.order.accepted event first; the Linz World MRK bridge "
            "creates/links the default MRK TaskBubble using the platform task id pattern. Do not create an arbitrary TaskBubble as a "
            "substitute for mrk.order.accepted unless you are intentionally taking the direct Bubble API path."
        ),
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
        "description": (
            "Request mounting an Agent/Skill/Rule/Evidence bubble into a TaskBubble slot. This mutates remote state and requires confirmation. "
            "For the default coder slot (slot.task.coder), mounted_bubble_id must be an AgentBubble id, commonly agent_<your_os_id> "
            "when no existing AgentBubble id is known. Do not pass a deliverable filename, source file path, or script name as "
            "mounted_bubble_id; put deliverable references in linz_bubble_submit_artifact.artifact_ref or an MRK handover payload instead."
        ),
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
        "description": (
            "Submit an artifact. For MRK requirements, provide requirement_id and order_id so the tool publishes "
            "mrk.order.handover.delivered and lets the backend bridge the default TaskBubble to reviewing. "
            "Without MRK ids, this falls back to direct TaskBubble artifact submission."
        ),
        "parameters": {
            "type": "object",
            "required": ["task_bubble_id", "mount_id", "artifact_ref", "delivery_note", "confirm_mutation"],
            "properties": {
                "task_bubble_id": {"type": "string"},
                "mount_id": {"type": "string"},
                "requirement_id": {"type": "string"},
                "order_id": {"type": "string"},
                "handover_version": {"type": "integer"},
                "actor_os_id": {"type": "string"},
                "deliverer_os_id": {"type": "string"},
                "deliverer_os_name": {"type": "string"},
                "artifact_ref": {"type": "string"},
                "file_ref": {"type": "string"},
                "file_name": {"type": "string"},
                "artifact_id": {"type": "string"},
                "artifact_endpoint": {"type": "string"},
                "checksum": {"type": "string"},
                "size": {"type": "integer"},
                "mime_type": {"type": "string"},
                "language": {"type": "string"},
                "artifact_version": {"type": "string"},
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
        "description": (
            "Approve or reject TaskBubble acceptance. For MRK requirements, provide requirement_id and order_id so the tool publishes "
            "mrk.order.handover.approved/rejected and lets the backend bridge TaskBubble acceptance. "
            "Without MRK ids, this falls back to direct TaskBubble acceptance review."
        ),
        "parameters": {
            "type": "object",
            "required": ["task_bubble_id", "approved", "confirm_mutation"],
            "properties": {
                "task_bubble_id": {"type": "string"},
                "requirement_id": {"type": "string"},
                "order_id": {"type": "string"},
                "handover_version": {"type": "integer"},
                "reviewer_os_id": {"type": "string"},
                "reviewer_os_name": {"type": "string"},
                "approved": {"type": "boolean"},
                "reason": {"type": "string"},
                "reject_reason": {"type": "string"},
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
        "description": (
            "Submit DemandBubble delivery summary. This mutates remote state and requires confirmation. "
            "Only call this after all required TaskBubbles under the DemandBubble are archived. For MRK flows, publish "
            "mrk.order.handover.delivered for the work delivery, wait for/trigger task acceptance, then submit the demand delivery summary."
        ),
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
