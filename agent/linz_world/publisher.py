"""Governed Linz World event publishing."""

from __future__ import annotations

import uuid

from .api_client import default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import PublishReceipt, ReceiptStatus
from .redaction import payload_summary


def publish_event(
    subject: str,
    event_type: str,
    payload: dict,
    repository: LinzStateRepository | None = None,
    service=None,
    *,
    os_runtime_context: dict | None = None,
) -> PublishReceipt:
    repo = repository or LinzStateRepository()
    request_id = uuid.uuid4().hex
    summary = payload_summary(payload)
    auth_map_version = ""
    governance = preflight_side_effect(
        capability="publish",
        repository=repo,
        service=service,
        subject=subject,
        event_type=event_type,
        payload=payload,
    )
    try:
        auth_map_version = repo.get_auth_map().map_version
    except Exception:
        auth_map_version = ""
    if not governance.allowed:
        receipt = PublishReceipt(
            request_id=request_id,
            subject=subject,
            event_type=event_type,
            payload_summary=summary,
            status=ReceiptStatus.REJECTED,
            governance_code=governance.code,
            message=governance.message,
        )
        repo.append_list("receipts", receipt)
        _record_os_runtime_world_receipt(
            receipt,
            authorization_map_version=auth_map_version,
            os_runtime_context=os_runtime_context,
        )
        return receipt
    session = repo.get_login()
    svc = service or default_service()
    try:
        result = svc.publish_event(session.token_ref, subject, event_type, payload)
    except Exception as exc:
        receipt = PublishReceipt(
            request_id=request_id,
            subject=subject,
            event_type=event_type,
            payload_summary=summary,
            status=ReceiptStatus.FAILED,
            message=f"Linz World publish failed: {exc}",
        )
        repo.append_list("receipts", receipt)
        _record_os_runtime_world_receipt(
            receipt,
            authorization_map_version=auth_map_version,
            os_runtime_context=os_runtime_context,
        )
        return receipt
    receipt = PublishReceipt(
        request_id=request_id,
        subject=subject,
        event_type=event_type,
        payload_summary=summary,
        status=ReceiptStatus.PUBLISHED,
        world_event_id=str(result.get("world_event_id") or ""),
        receipt=result,
    )
    try:
        repo.append_list("receipts", receipt)
    except Exception as exc:
        uncertain = PublishReceipt(
            request_id=request_id,
            subject=subject,
            event_type=event_type,
            payload_summary=summary,
            status=ReceiptStatus.UNCERTAIN,
            world_event_id=receipt.world_event_id,
            message=f"World publish succeeded but local receipt persistence failed: {exc}",
            receipt=result,
        )
        _record_os_runtime_world_receipt(
            uncertain,
            authorization_map_version=auth_map_version,
            os_runtime_context=os_runtime_context,
        )
        return uncertain
    _record_os_runtime_world_receipt(
        receipt,
        authorization_map_version=auth_map_version,
        os_runtime_context=os_runtime_context,
    )
    return receipt


def _record_os_runtime_world_receipt(
    receipt: PublishReceipt,
    *,
    authorization_map_version: str = "",
    os_runtime_context: dict | None = None,
) -> None:
    try:
        from agent.os_runtime.adapters.linz_world import project_world_publish_receipt
        context = dict(os_runtime_context or {})
        project_world_publish_receipt(
            receipt,
            event_id=str(context.get("event_id") or ""),
            intent_id=str(context.get("intent_id") or ""),
            arbitration_id=str(context.get("arbitration_id") or ""),
            ticket_id=str(context.get("permission_ticket_id") or context.get("ticket_id") or ""),
            session_id=str(context.get("session_id") or ""),
            authorization_map_version=authorization_map_version,
            metadata={"context_source": "publisher.os_runtime_context" if context else "publisher"},
        )
    except Exception:
        return
