"""Linz World Bubble receipt projection into os_runtime execution receipts."""

from __future__ import annotations

from typing import Any, Callable

from agent.linz_world.bubble_receipts import BubbleReceipt
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import EventSource, ExecutionReceipt

from .events import EventProjectionAdapter, _with_runtime_adapter, bounded_summary, stable_hash
from .session_store import OSRuntimeEventRepository
from .tools import ReceiptRecordResult


ReceiptSink = Callable[[ExecutionReceipt], Any]


def build_bubble_receipt(
    receipt: BubbleReceipt | dict[str, Any],
    *,
    event_id: str = "",
    intent_id: str = "",
    arbitration_id: str = "",
    ticket_id: str = "",
    session_id: str = "",
    metadata: dict[str, Any] | None = None,
    max_summary_chars: int = 1024,
) -> ExecutionReceipt:
    data = _receipt_data(receipt)
    status = _normalize_status(data.get("status", ""))
    action = str(data.get("action") or "")
    output = data.get("result_summary") or action or status
    output_summary, content_ref = bounded_summary(str(output), max_chars=max_summary_chars)
    error = "" if status == "succeeded" else bounded_summary(
        str(data.get("message") or data.get("governance_code") or status),
        max_chars=max_summary_chars,
    )[0]
    request_id = str(data.get("request_id") or "")
    receipt_metadata = {
        "request_id": request_id,
        "action": action,
        "bubble_id": str(data.get("bubble_id") or ""),
        "target_bubble_id": str(data.get("target_bubble_id") or ""),
        "mount_id": str(data.get("mount_id") or ""),
        "lifecycle_state": str(data.get("lifecycle_state") or ""),
        "governance_code": str(data.get("governance_code") or ""),
        "message": str(data.get("message") or ""),
    }
    receipt_metadata.update(metadata or {})
    receipt_hash = stable_hash(
        {
            "type": "linz_bubble",
            "request_id": request_id,
            "action": action,
            "status": status,
        }
    )[:24]
    return ExecutionReceipt(
        receipt_id=f"receipt_bubble_{receipt_hash}",
        receipt_type="linz_bubble",
        ticket_id=ticket_id,
        intent_id=intent_id,
        event_id=event_id,
        arbitration_id=arbitration_id,
        session_id=session_id,
        status=status,
        completed_at=str(data.get("recorded_at") or ""),
        output_summary=output_summary,
        error=error,
        payload_hash=stable_hash(data),
        content_ref=content_ref,
        metadata=receipt_metadata,
    )


def record_bubble_receipt(
    receipt: BubbleReceipt | dict[str, Any],
    *,
    event_id: str = "",
    intent_id: str = "",
    arbitration_id: str = "",
    ticket_id: str = "",
    session_id: str = "",
    metadata: dict[str, Any] | None = None,
    repository: OSRuntimeEventRepository | None = None,
    sink: ReceiptSink | None = None,
    config: OSRuntimeConfig | dict[str, Any] | None = None,
) -> ReceiptRecordResult:
    runtime_config = _coerce_config(config)
    if not runtime_config.enabled:
        return ReceiptRecordResult(status="skipped")
    try:
        execution_receipt = build_bubble_receipt(
            receipt,
            event_id=event_id,
            intent_id=intent_id,
            arbitration_id=arbitration_id,
            ticket_id=ticket_id,
            session_id=session_id,
            metadata=metadata,
        )
        if sink is not None:
            sink(execution_receipt)
            return ReceiptRecordResult(status="written", receipt=execution_receipt)
        if repository is None:
            return ReceiptRecordResult(status="built", receipt=execution_receipt)
        projection = EventProjectionAdapter(repository, runtime_config).project(
            event_type="execution_receipt",
            source=EventSource.LINZ_WORLD,
            summary=execution_receipt.output_summary or execution_receipt.status,
            trace_id=execution_receipt.event_id
            or execution_receipt.intent_id
            or execution_receipt.metadata.get("bubble_id", ""),
            session_id=session_id,
            event_id=f"osr_receipt_{execution_receipt.receipt_id}",
            metadata={"receipt": execution_receipt.to_dict()},
            payload=execution_receipt.to_dict(),
            status=execution_receipt.status or "recorded",
        )
        if projection.status == "written":
            return ReceiptRecordResult(status="written", receipt=execution_receipt, event=projection.event)
        return ReceiptRecordResult(
            status=projection.status,
            receipt=execution_receipt,
            error=projection.error,
        )
    except Exception as exc:
        return ReceiptRecordResult(status="error", error=f"{type(exc).__name__}: {exc}")


def project_bubble_receipt(receipt: BubbleReceipt | dict[str, Any], **kwargs: Any) -> ReceiptRecordResult:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return ReceiptRecordResult(status="skipped")
    repo, _adapter = runtime
    try:
        return record_bubble_receipt(
            receipt,
            repository=repo,
            config=OSRuntimeConfig(enabled=True),
            **kwargs,
        )
    finally:
        repo.close()


def _receipt_data(receipt: BubbleReceipt | dict[str, Any]) -> dict[str, Any]:
    if isinstance(receipt, dict):
        return dict(receipt)
    status = getattr(receipt, "status", "")
    return {
        "request_id": getattr(receipt, "request_id", ""),
        "action": getattr(receipt, "action", ""),
        "status": getattr(status, "value", status),
        "bubble_id": getattr(receipt, "bubble_id", ""),
        "target_bubble_id": getattr(receipt, "target_bubble_id", ""),
        "mount_id": getattr(receipt, "mount_id", ""),
        "lifecycle_state": getattr(receipt, "lifecycle_state", ""),
        "governance_code": getattr(receipt, "governance_code", ""),
        "message": getattr(receipt, "message", ""),
        "result_summary": getattr(receipt, "result_summary", ""),
        "receipt": getattr(receipt, "receipt", {}) or {},
        "recorded_at": getattr(receipt, "recorded_at", ""),
    }


def _normalize_status(status: Any) -> str:
    value = str(getattr(status, "value", status) or "").lower()
    if value == "published":
        return "succeeded"
    if value in {"rejected", "failed", "uncertain"}:
        return value
    return value or "uncertain"


def _coerce_config(config: OSRuntimeConfig | dict[str, Any] | None) -> OSRuntimeConfig:
    if isinstance(config, OSRuntimeConfig):
        return config
    if isinstance(config, dict):
        return OSRuntimeConfig.from_dict(config)
    return default_os_runtime_config()


__all__ = [
    "build_bubble_receipt",
    "project_bubble_receipt",
    "record_bubble_receipt",
]
