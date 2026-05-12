"""Governed Linz World event publishing."""

from __future__ import annotations

import uuid

from .api_client import default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import PublishReceipt, ReceiptStatus
from .redaction import payload_summary


def publish_event(subject: str, event_type: str, payload: dict, repository: LinzStateRepository | None = None, service=None) -> PublishReceipt:
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    request_id = uuid.uuid4().hex
    summary = payload_summary(payload)
    governance = preflight_side_effect(
        capability="publish",
        repository=repo,
        service=svc,
        subject=subject,
        event_type=event_type,
        payload=payload,
    )
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
        return receipt
    session = repo.get_login()
    try:
        result = svc.publish_event(session.token_ref, subject, event_type, payload)
        receipt = PublishReceipt(
            request_id=request_id,
            subject=subject,
            event_type=event_type,
            payload_summary=summary,
            status=ReceiptStatus.PUBLISHED,
            world_event_id=str(result.get("world_event_id") or ""),
            receipt=result,
        )
        repo.append_list("receipts", receipt)
        return receipt
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
        return receipt
