"""Governed Soul Memory writes."""

from __future__ import annotations

from .api_client import default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import ReceiptStatus, SoulMemoryEntry


def write_memory(artifact_ref: str, sink_reason: str, summary: str, repository: LinzStateRepository | None = None, service=None) -> SoulMemoryEntry:
    if not artifact_ref or not sink_reason:
        return SoulMemoryEntry(artifact_ref, sink_reason, summary, ReceiptStatus.REJECTED, message="artifact_ref and sink_reason are required.")
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    governance = preflight_side_effect(capability="memory_sink", repository=repo, service=svc)
    if not governance.allowed:
        return SoulMemoryEntry(artifact_ref, sink_reason, summary, ReceiptStatus.REJECTED, message=governance.message)
    try:
        result = svc.write_memory(repo.get_login().token_ref, artifact_ref, sink_reason, summary)
        entry = SoulMemoryEntry(artifact_ref, sink_reason, summary, ReceiptStatus.PUBLISHED, receipt=str(result.get("receipt") or ""))
    except Exception as exc:
        entry = SoulMemoryEntry(artifact_ref, sink_reason, summary, ReceiptStatus.FAILED, message=f"Linz World memory write failed: {exc}")
    repo.append_list("memory", entry)
    return entry


def sink_memory(*, artifact_ref: str, sink_reason: str, summary: str, **kwargs) -> SoulMemoryEntry:
    return write_memory(artifact_ref, sink_reason, summary, **kwargs)
