"""Governed Linz World compute invocation."""

from __future__ import annotations

import uuid

from .api_client import default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import ComputeReceipt, ReceiptStatus
from .redaction import payload_summary


def invoke_compute(task: str, input_data: dict | None = None, repository: LinzStateRepository | None = None, service=None) -> ComputeReceipt:
    if input_data and any(str(k).lower() in {"token", "api_key", "secret"} for k in input_data):
        return ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.REJECTED, message="Explicit credentials are not accepted.")
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    governance = preflight_side_effect(capability="compute", repository=repo, service=svc)
    if not governance.allowed:
        return ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.REJECTED, message=governance.message)
    try:
        result = svc.invoke_compute(repo.get_login().token_ref, task, input_data or {})
        receipt = ComputeReceipt(
            uuid.uuid4().hex,
            ReceiptStatus.PUBLISHED,
            provider_summary=str(result.get("provider_summary") or ""),
            result_summary=payload_summary(result.get("result") or {}),
            receipt=str(result.get("receipt") or ""),
        )
    except Exception as exc:
        receipt = ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.FAILED, message=f"Linz World compute failed: {exc}")
    repo.append_list("compute", receipt)
    return receipt
