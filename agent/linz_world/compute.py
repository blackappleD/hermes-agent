"""Governed Linz World compute invocation."""

from __future__ import annotations

import uuid

from .api_client import default_service, resolve_secret_ref
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import ComputeReceipt, LoginState, ReceiptStatus
from .redaction import payload_summary


def invoke_compute(task: str, input_data: dict | None = None, repository: LinzStateRepository | None = None, service=None) -> ComputeReceipt:
    if input_data and any(str(k).lower() in {"token", "api_key", "secret"} for k in input_data):
        return ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.REJECTED, message="Explicit credentials are not accepted.")
    repo = repository or LinzStateRepository()
    session = repo.get_login()
    if not session.token_ref or session.state != LoginState.LOGGED_IN:
        return ComputeReceipt(
            uuid.uuid4().hex,
            ReceiptStatus.REJECTED,
            message="Linz World login token reference is missing; compute is blocked.",
        )
    if not resolve_secret_ref(session.token_ref):
        return ComputeReceipt(
            uuid.uuid4().hex,
            ReceiptStatus.REJECTED,
            message="Linz World login token secret is unavailable; compute is blocked.",
        )
    try:
        svc = service or default_service()
    except Exception as exc:
        return ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.FAILED, message=f"Linz World compute unavailable: {exc}")
    governance = preflight_side_effect(capability="compute", repository=repo, service=svc)
    if not governance.allowed:
        return ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.REJECTED, message=governance.message)
    try:
        result = svc.invoke_compute(session.token_ref, task, input_data or {})
        receipt = ComputeReceipt(
            str(result.get("request_id") or uuid.uuid4().hex),
            ReceiptStatus.PUBLISHED,
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
            provider_summary="/".join(part for part in (str(result.get("provider") or ""), str(result.get("model") or "")) if part),
            result_summary=payload_summary({"choices": result.get("choices") or []}),
            receipt=str(result.get("request_id") or ""),
            usage=dict(result.get("usage") or {}),
            reservation=dict(result.get("reservation") or {}),
        )
    except Exception as exc:
        receipt = ComputeReceipt(uuid.uuid4().hex, ReceiptStatus.FAILED, message=f"Linz World compute failed: {exc}")
    repo.append_list("compute", receipt)
    return receipt
