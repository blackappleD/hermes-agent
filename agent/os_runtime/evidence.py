"""Evidence package aggregation for os_runtime autonomous continuations."""

from __future__ import annotations

from typing import Any

from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import ArbitrationResult, EvidencePackage, ExecutionReceipt, OpenIntent
from agent.os_runtime.domain import EventSource

from .adapters.events import EventProjectionAdapter, ProjectionResult, bounded_summary, stable_hash
from .adapters.session_store import OSRuntimeEventRepository


def command_evidence(
    *,
    command: str,
    exit_status: int,
    output: Any = "",
    kind: str = "command",
    metadata: dict[str, Any] | None = None,
    max_summary_chars: int = 1024,
) -> dict[str, Any]:
    summary, content_ref = bounded_summary(output, max_chars=max_summary_chars)
    data = {
        "kind": kind,
        "command": command,
        "exit_status": int(exit_status),
        "output_summary": summary,
        "output_hash": stable_hash(output),
        "status": "succeeded" if int(exit_status) == 0 else "failed",
        "metadata": dict(metadata or {}),
    }
    if content_ref:
        data["content_ref"] = content_ref
    return data


def build_evidence_package(
    *,
    evidence_id: str = "",
    trace_id: str = "",
    session_id: str = "",
    event_id: str = "",
    event_ids: list[str] | None = None,
    intent: OpenIntent | dict[str, Any] | None = None,
    arbitration: ArbitrationResult | dict[str, Any] | None = None,
    receipts: list[ExecutionReceipt | dict[str, Any]] | None = None,
    commands: list[dict[str, Any]] | None = None,
    known_risks: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    receipt_objects = [_coerce_receipt(item) for item in receipts or []]
    intent_data = _to_dict(intent)
    arbitration_data = _to_dict(arbitration)
    intent_id = str(intent_data.get("intent_id") or _first_non_empty([item.intent_id for item in receipt_objects]))
    arbitration_id = str(
        arbitration_data.get("arbitration_id")
        or _first_non_empty([item.arbitration_id for item in receipt_objects])
        or arbitration_data.get("metadata", {}).get("arbitration_id", "")
    )
    events = list(event_ids or [])
    if event_id:
        events.append(event_id)
    for item in receipt_objects:
        if item.event_id:
            events.append(item.event_id)
    events = _dedupe(events)
    receipt_ids = _dedupe([item.receipt_id for item in receipt_objects if item.receipt_id])
    command_items = list(commands or [])
    diagnostics = _diagnostics(
        intent_id=intent_id,
        arbitration_id=arbitration_id,
        receipts=receipt_objects,
        event_ids=events,
    )
    risks = list(known_risks or [])
    for item in command_items:
        if int(item.get("exit_status", 0)) != 0:
            risks.append(f"command_failed:{item.get('command', '')}")
    risks.extend(diagnostics)
    risks = _dedupe(risks)
    complete = not diagnostics and all(
        item.ticket_id and item.intent_id and item.arbitration_id and item.event_id
        for item in receipt_objects
    )
    package_id = evidence_id or f"evidence_{stable_hash({'trace_id': trace_id, 'receipts': receipt_ids})[:24]}"
    evidence = [
        {"kind": "intent", "value": intent_data},
        {"kind": "arbitration", "value": arbitration_data},
    ]
    evidence.extend({"kind": "receipt", "value": item.to_dict()} for item in receipt_objects)
    evidence.extend(command_items)
    return EvidencePackage(
        evidence_id=package_id,
        trace_id=trace_id,
        session_id=session_id,
        intent_id=intent_id,
        arbitration_id=arbitration_id,
        event_ids=events,
        receipt_ids=receipt_ids,
        summary=_summary(intent_id, arbitration_id, receipt_objects, complete),
        evidence=evidence,
        receipts=receipt_objects,
        commands=command_items,
        known_risks=risks,
        diagnostics=diagnostics,
        complete=complete,
        metadata=dict(metadata or {}),
    )


def record_evidence_package(
    package: EvidencePackage,
    *,
    repository: OSRuntimeEventRepository,
    config: OSRuntimeConfig | dict[str, Any] | None = None,
) -> ProjectionResult:
    runtime_config = _coerce_config(config)
    if not runtime_config.enabled:
        return ProjectionResult(status="skipped")
    return EventProjectionAdapter(repository, runtime_config).project(
        event_type="evidence_package",
        source=EventSource.SYSTEM,
        summary=package.summary,
        trace_id=package.trace_id,
        session_id=package.session_id,
        event_id=f"osr_evidence_{package.evidence_id}",
        metadata={"evidence_package": package.to_dict()},
        payload=package.to_dict(),
        status="complete" if package.complete else "incomplete",
    )


def _coerce_receipt(value: ExecutionReceipt | dict[str, Any]) -> ExecutionReceipt:
    if isinstance(value, ExecutionReceipt):
        return value
    return ExecutionReceipt.from_dict(value)


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    return {"value": str(value)}


def _diagnostics(
    *,
    intent_id: str,
    arbitration_id: str,
    receipts: list[ExecutionReceipt],
    event_ids: list[str],
) -> list[str]:
    diagnostics = []
    if not intent_id:
        diagnostics.append("missing_intent")
    if not arbitration_id:
        diagnostics.append("missing_arbitration")
    if not receipts:
        diagnostics.append("missing_receipts")
    if not event_ids:
        diagnostics.append("missing_event")
    for item in receipts:
        if not item.ticket_id:
            diagnostics.append(f"missing_ticket:{item.receipt_id}")
        if not item.event_id:
            diagnostics.append(f"orphan_receipt:{item.receipt_id}")
        for diagnostic in item.metadata.get("diagnostics", []) if isinstance(item.metadata, dict) else []:
            diagnostics.append(str(diagnostic))
    return _dedupe(diagnostics)


def _summary(
    intent_id: str,
    arbitration_id: str,
    receipts: list[ExecutionReceipt],
    complete: bool,
) -> str:
    status = "complete" if complete else "incomplete"
    receipt_types = ",".join(_dedupe([item.receipt_type or "unknown" for item in receipts])) or "none"
    return (
        f"EvidencePackage {status}: intent={intent_id or 'missing'} "
        f"arbitration={arbitration_id or 'missing'} receipts={len(receipts)} types={receipt_types}"
    )


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _dedupe(values: list[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _coerce_config(config: OSRuntimeConfig | dict[str, Any] | None) -> OSRuntimeConfig:
    if isinstance(config, OSRuntimeConfig):
        return config
    if isinstance(config, dict):
        return OSRuntimeConfig.from_dict(config)
    return default_os_runtime_config()


__all__ = [
    "build_evidence_package",
    "command_evidence",
    "record_evidence_package",
]
