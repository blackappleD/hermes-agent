"""Receipt adapters for existing Hermes tool and final-response hooks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import EventSource, ExecutionReceipt

from .events import (
    EventProjectionAdapter,
    ProjectionResult,
    _with_runtime_adapter,
    bounded_summary,
    stable_hash,
)
from .session_store import OSRuntimeEventRepository


ReceiptSink = Callable[[ExecutionReceipt], Any]


@dataclass
class ReceiptRecordResult:
    status: str
    receipt: ExecutionReceipt | None = None
    event: Any = None
    error: str = ""

    @property
    def written(self) -> bool:
        return self.status == "written"


def build_tool_receipt(
    *,
    tool_name: str,
    args: Any,
    result: Any,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    duration_ms: int = 0,
    runtime_context: dict[str, Any] | None = None,
    max_summary_chars: int = 1024,
) -> ExecutionReceipt:
    context = dict(runtime_context or {})
    event_id = str(context.get("event_id") or context.get("source_event_id") or "")
    intent_id = str(context.get("intent_id") or "")
    arbitration_id = str(context.get("arbitration_id") or "")
    ticket_id = str(context.get("permission_ticket_id") or context.get("ticket_id") or "")
    started_at = str(context.get("started_at") or "")
    completed_at = str(context.get("completed_at") or utc_now_iso())
    input_summary, input_ref = bounded_summary(args, max_chars=max_summary_chars)
    output_summary, output_ref = bounded_summary(result, max_chars=max_summary_chars)
    missing = _missing_context(
        {
            "event_id": event_id,
            "intent_id": intent_id,
            "arbitration_id": arbitration_id,
            "permission_ticket_id": ticket_id,
        }
    )
    status = _infer_tool_status(result, context.get("error"))
    receipt_hash = stable_hash(
        {
            "type": "tool",
            "tool_name": tool_name,
            "session_id": session_id,
            "task_id": task_id,
            "tool_call_id": tool_call_id,
            "args_hash": stable_hash(args),
            "result_hash": stable_hash(result),
        }
    )[:24]
    metadata = {
        "tool_name": tool_name,
        "arguments_hash": stable_hash(args),
        "result_hash": stable_hash(result),
        "diagnostics": missing,
    }
    if input_ref:
        metadata["input_ref"] = input_ref
    if output_ref:
        metadata["output_ref"] = output_ref
    if context:
        metadata["runtime_context"] = {
            key: value
            for key, value in context.items()
            if key
            not in {
                "event_id",
                "source_event_id",
                "intent_id",
                "arbitration_id",
                "permission_ticket_id",
                "ticket_id",
                "started_at",
                "completed_at",
                "error",
            }
        }

    return ExecutionReceipt(
        receipt_id=f"receipt_tool_{receipt_hash}",
        receipt_type="tool",
        ticket_id=ticket_id,
        intent_id=intent_id,
        event_id=event_id,
        arbitration_id=arbitration_id,
        session_id=session_id or "",
        task_id=task_id or "",
        tool_call_id=tool_call_id or "",
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=max(0, int(duration_ms or 0)),
        input_summary=input_summary,
        output_summary=output_summary,
        error=_error_summary(result, context.get("error"), max_summary_chars=max_summary_chars),
        payload_hash=stable_hash({"args": args, "result": result}),
        content_ref=output_ref,
        metadata=metadata,
    )


def build_final_response_receipt(
    *,
    assistant_response: str,
    session_id: str = "",
    event_id: str = "",
    intent_id: str = "",
    arbitration_id: str = "",
    ticket_id: str = "",
    model: str = "",
    platform: str = "",
    turn_exit_reason: str = "",
    token_usage: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    max_summary_chars: int = 1024,
) -> ExecutionReceipt:
    output_summary, content_ref = bounded_summary(
        assistant_response or "",
        max_chars=max_summary_chars,
        content_ref=f"final_response:{stable_hash(assistant_response)[:16]}",
    )
    missing = _missing_context(
        {
            "event_id": event_id,
            "intent_id": intent_id,
            "arbitration_id": arbitration_id,
            "permission_ticket_id": ticket_id,
        }
    )
    receipt_hash = stable_hash(
        {
            "type": "final_response",
            "session_id": session_id,
            "event_id": event_id,
            "intent_id": intent_id,
            "response_hash": stable_hash(assistant_response),
        }
    )[:24]
    receipt_metadata = {
        "model": model,
        "platform": platform,
        "turn_exit_reason": turn_exit_reason,
        "token_usage": token_usage or {},
        "cost": cost or {},
        "diagnostics": missing,
    }
    receipt_metadata.update(metadata or {})
    return ExecutionReceipt(
        receipt_id=f"receipt_final_{receipt_hash}",
        receipt_type="final_response",
        ticket_id=ticket_id,
        intent_id=intent_id,
        event_id=event_id,
        arbitration_id=arbitration_id,
        session_id=session_id or "",
        status="succeeded",
        completed_at=utc_now_iso(),
        output_summary=output_summary,
        payload_hash=stable_hash(assistant_response),
        content_ref=content_ref,
        metadata=receipt_metadata,
    )


def record_post_tool_call(
    *,
    tool_name: str,
    args: Any,
    result: Any,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    duration_ms: int = 0,
    runtime_context: dict[str, Any] | None = None,
    repository: OSRuntimeEventRepository | None = None,
    sink: ReceiptSink | None = None,
    config: OSRuntimeConfig | dict[str, Any] | None = None,
) -> ReceiptRecordResult:
    runtime_config = _coerce_config(config)
    if not runtime_config.enabled:
        return ReceiptRecordResult(status="skipped")
    try:
        receipt = build_tool_receipt(
            tool_name=tool_name,
            args=args,
            result=result,
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            duration_ms=duration_ms,
            runtime_context=runtime_context,
        )
        return _record_receipt(
            receipt,
            source=EventSource.TOOL_RESULT,
            repository=repository,
            sink=sink,
            config=runtime_config,
        )
    except Exception as exc:
        return ReceiptRecordResult(status="error", error=f"{type(exc).__name__}: {exc}")


def record_final_response(
    *,
    assistant_response: str,
    session_id: str = "",
    event_id: str = "",
    intent_id: str = "",
    arbitration_id: str = "",
    ticket_id: str = "",
    model: str = "",
    platform: str = "",
    turn_exit_reason: str = "",
    token_usage: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    repository: OSRuntimeEventRepository | None = None,
    sink: ReceiptSink | None = None,
    config: OSRuntimeConfig | dict[str, Any] | None = None,
) -> ReceiptRecordResult:
    runtime_config = _coerce_config(config)
    if not runtime_config.enabled:
        return ReceiptRecordResult(status="skipped")
    try:
        receipt = build_final_response_receipt(
            assistant_response=assistant_response,
            session_id=session_id,
            event_id=event_id,
            intent_id=intent_id,
            arbitration_id=arbitration_id,
            ticket_id=ticket_id,
            model=model,
            platform=platform,
            turn_exit_reason=turn_exit_reason,
            token_usage=token_usage,
            cost=cost,
            metadata=metadata,
        )
        return _record_receipt(
            receipt,
            source=EventSource.HERMES_CONVERSATION,
            repository=repository,
            sink=sink,
            config=runtime_config,
        )
    except Exception as exc:
        return ReceiptRecordResult(status="error", error=f"{type(exc).__name__}: {exc}")


def project_post_tool_receipt(**kwargs: Any) -> ReceiptRecordResult:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return ReceiptRecordResult(status="skipped")
    repo, _adapter = runtime
    try:
        return record_post_tool_call(repository=repo, config=OSRuntimeConfig(enabled=True), **kwargs)
    finally:
        repo.close()


def project_final_response_receipt(**kwargs: Any) -> ReceiptRecordResult:
    runtime = _with_runtime_adapter()
    if runtime is None:
        return ReceiptRecordResult(status="skipped")
    repo, _adapter = runtime
    try:
        return record_final_response(repository=repo, config=OSRuntimeConfig(enabled=True), **kwargs)
    finally:
        repo.close()


def _record_receipt(
    receipt: ExecutionReceipt,
    *,
    source: EventSource,
    repository: OSRuntimeEventRepository | None,
    sink: ReceiptSink | None,
    config: OSRuntimeConfig,
) -> ReceiptRecordResult:
    if sink is not None:
        sink(receipt)
        return ReceiptRecordResult(status="written", receipt=receipt)
    if repository is None:
        return ReceiptRecordResult(status="built", receipt=receipt)
    projection = EventProjectionAdapter(repository, config).project(
        event_type="execution_receipt",
        source=source,
        summary=receipt.output_summary or receipt.input_summary or receipt.status,
        trace_id=receipt.event_id or receipt.intent_id or receipt.task_id or receipt.session_id,
        session_id=receipt.session_id,
        event_id=f"osr_receipt_{receipt.receipt_id}",
        metadata={"receipt": receipt.to_dict()},
        payload=receipt.to_dict(),
        status=receipt.status or "recorded",
    )
    if projection.status == "written":
        return ReceiptRecordResult(status="written", receipt=receipt, event=projection.event)
    return ReceiptRecordResult(status=projection.status, receipt=receipt, error=projection.error)


def _coerce_config(config: OSRuntimeConfig | dict[str, Any] | None) -> OSRuntimeConfig:
    if isinstance(config, OSRuntimeConfig):
        return config
    if isinstance(config, dict):
        return OSRuntimeConfig.from_dict(config)
    return default_os_runtime_config()


def _missing_context(values: dict[str, str]) -> list[str]:
    return [f"missing_{key}" for key, value in values.items() if not value]


def _infer_tool_status(result: Any, explicit_error: Any = None) -> str:
    if explicit_error:
        return "error"
    parsed = _parse_jsonish(result)
    if isinstance(parsed, dict):
        status = str(parsed.get("status") or parsed.get("state") or "").lower()
        if status in {"error", "failed", "failure", "rejected"}:
            return "failed"
        if parsed.get("ok") is False or parsed.get("success") is False:
            return "failed"
        if parsed.get("error") or parsed.get("exception"):
            return "failed"
        exit_code = parsed.get("exit_code", parsed.get("returncode"))
        if isinstance(exit_code, int) and exit_code != 0:
            return "failed"
    return "succeeded"


def _error_summary(result: Any, explicit_error: Any = None, *, max_summary_chars: int = 1024) -> str:
    if explicit_error:
        return bounded_summary(explicit_error, max_chars=max_summary_chars)[0]
    parsed = _parse_jsonish(result)
    if isinstance(parsed, dict):
        for key in ("error", "exception", "message", "stderr"):
            if parsed.get(key):
                return bounded_summary(parsed.get(key), max_chars=max_summary_chars)[0]
    return ""


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value
    return value


__all__ = [
    "ReceiptRecordResult",
    "build_final_response_receipt",
    "build_tool_receipt",
    "project_final_response_receipt",
    "project_post_tool_receipt",
    "record_final_response",
    "record_post_tool_call",
]
