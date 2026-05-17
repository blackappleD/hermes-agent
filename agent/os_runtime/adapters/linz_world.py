"""Linz World publish receipt projection into os_runtime execution receipts."""

from __future__ import annotations

from typing import Any, Callable

from agent.linz_world.models import PublishReceipt
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import EventSource, ExecutionReceipt

from .events import EventProjectionAdapter, _with_runtime_adapter, bounded_summary, stable_hash
from .session_store import OSRuntimeEventRepository
from .tools import ReceiptRecordResult


ReceiptSink = Callable[[ExecutionReceipt], Any]


def build_world_publish_receipt(
    receipt: PublishReceipt | dict[str, Any],
    *,
    event_id: str = "",
    intent_id: str = "",
    arbitration_id: str = "",
    ticket_id: str = "",
    authorization_map_version: str = "",
    session_id: str = "",
    metadata: dict[str, Any] | None = None,
    max_summary_chars: int = 1024,
) -> ExecutionReceipt:
    data = _receipt_data(receipt)
    payload_summary = data.get("payload_summary", "")
    output_summary, content_ref = bounded_summary(payload_summary, max_chars=max_summary_chars)
    status = _normalize_status(data.get("status", ""))
    world_event_id = str(data.get("world_event_id") or "")
    request_id = str(data.get("request_id") or "")
    map_version = (
        authorization_map_version
        or str(_nested_get(data.get("receipt"), "authorization_map_version") or "")
        or str(_nested_get(data.get("receipt"), "map_version") or "")
    )
    diagnostics = []
    for key, value in {
        "event_id": event_id,
        "intent_id": intent_id,
        "arbitration_id": arbitration_id,
        "permission_ticket_id": ticket_id,
        "authorization_map_version": map_version,
    }.items():
        if not value:
            diagnostics.append(f"missing_{key}")
    if status == "succeeded" and not world_event_id:
        diagnostics.append("missing_world_event_id")

    receipt_metadata = {
        "request_id": request_id,
        "subject": str(data.get("subject") or ""),
        "event_type": str(data.get("event_type") or ""),
        "world_event_id": world_event_id,
        "governance_code": str(data.get("governance_code") or ""),
        "message": str(data.get("message") or ""),
        "authorization_map_version": map_version,
        "diagnostics": diagnostics,
    }
    receipt_metadata.update(metadata or {})
    receipt_hash = stable_hash(
        {
            "type": "world_publish",
            "request_id": request_id,
            "world_event_id": world_event_id,
            "status": status,
        }
    )[:24]
    return ExecutionReceipt(
        receipt_id=f"receipt_world_{receipt_hash}",
        receipt_type="world_publish",
        ticket_id=ticket_id,
        intent_id=intent_id,
        event_id=event_id,
        arbitration_id=arbitration_id,
        session_id=session_id,
        status=status,
        completed_at=str(data.get("recorded_at") or ""),
        output_summary=output_summary,
        error=_world_error_summary(data, max_summary_chars=max_summary_chars),
        payload_hash=stable_hash(data),
        content_ref=content_ref,
        metadata=receipt_metadata,
    )


def record_world_publish(
    receipt: PublishReceipt | dict[str, Any],
    *,
    event_id: str = "",
    intent_id: str = "",
    arbitration_id: str = "",
    ticket_id: str = "",
    authorization_map_version: str = "",
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
        execution_receipt = build_world_publish_receipt(
            receipt,
            event_id=event_id,
            intent_id=intent_id,
            arbitration_id=arbitration_id,
            ticket_id=ticket_id,
            authorization_map_version=authorization_map_version,
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
            or execution_receipt.metadata.get("world_event_id", ""),
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


def project_world_publish_receipt(receipt: PublishReceipt | dict[str, Any], **kwargs: Any) -> ReceiptRecordResult:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return ReceiptRecordResult(status="skipped")
    repo, _adapter = runtime
    try:
        return record_world_publish(
            receipt,
            repository=repo,
            config=OSRuntimeConfig(enabled=True),
            **kwargs,
        )
    finally:
        repo.close()


def _receipt_data(receipt: PublishReceipt | dict[str, Any]) -> dict[str, Any]:
    if isinstance(receipt, dict):
        return dict(receipt)
    status = getattr(receipt, "status", "")
    return {
        "request_id": getattr(receipt, "request_id", ""),
        "subject": getattr(receipt, "subject", ""),
        "event_type": getattr(receipt, "event_type", ""),
        "payload_summary": getattr(receipt, "payload_summary", ""),
        "status": getattr(status, "value", status),
        "world_event_id": getattr(receipt, "world_event_id", ""),
        "governance_code": getattr(receipt, "governance_code", ""),
        "message": getattr(receipt, "message", ""),
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


def _world_error_summary(data: dict[str, Any], *, max_summary_chars: int) -> str:
    status = _normalize_status(data.get("status", ""))
    if status == "succeeded":
        return ""
    message = data.get("message") or data.get("governance_code") or status
    return bounded_summary(message, max_chars=max_summary_chars)[0]


def _nested_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _coerce_config(config: OSRuntimeConfig | dict[str, Any] | None) -> OSRuntimeConfig:
    if isinstance(config, OSRuntimeConfig):
        return config
    if isinstance(config, dict):
        return OSRuntimeConfig.from_dict(config)
    return default_os_runtime_config()


__all__ = [
    "build_world_publish_receipt",
    "project_world_publish_receipt",
    "record_world_publish",
]
