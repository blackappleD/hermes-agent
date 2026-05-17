"""Persistent approval requests for autonomous os_runtime actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.adapters.events import stable_hash
from agent.os_runtime.adapters.session_store import OSRuntimeEvent, OSRuntimeEventRepository
from agent.os_runtime.domain import ArbitrationResult, EventSource, OpenIntent, PermissionTicket, SelfPrompt


APPROVAL_REQUEST_EVENT = "os_runtime_approval_request"
APPROVAL_RESOLUTION_EVENT = "os_runtime_approval_resolution"


@dataclass
class ApprovalRequest:
    approval_id: str
    session_id: str = ""
    profile_id: str = ""
    intent_id: str = ""
    arbitration_id: str = ""
    ticket_id: str = ""
    status: str = "pending"
    requested_at: str = ""
    resolved_at: str = ""
    resolver: str = ""
    reason: str = ""
    event_ids: list[str] = field(default_factory=list)
    task_id: str = ""
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "intent_id": self.intent_id,
            "arbitration_id": self.arbitration_id,
            "ticket_id": self.ticket_id,
            "status": self.status,
            "requested_at": self.requested_at,
            "resolved_at": self.resolved_at,
            "resolver": self.resolver,
            "reason": self.reason,
            "event_ids": list(self.event_ids),
            "task_id": self.task_id,
            "summary": self.summary,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        return cls(
            approval_id=str(data.get("approval_id") or ""),
            session_id=str(data.get("session_id") or ""),
            profile_id=str(data.get("profile_id") or ""),
            intent_id=str(data.get("intent_id") or ""),
            arbitration_id=str(data.get("arbitration_id") or ""),
            ticket_id=str(data.get("ticket_id") or ""),
            status=str(data.get("status") or "pending"),
            requested_at=str(data.get("requested_at") or ""),
            resolved_at=str(data.get("resolved_at") or ""),
            resolver=str(data.get("resolver") or ""),
            reason=str(data.get("reason") or ""),
            event_ids=[str(item) for item in data.get("event_ids") or []],
            task_id=str(data.get("task_id") or ""),
            summary=str(data.get("summary") or ""),
            payload=dict(data.get("payload") or {}),
            metadata=dict(data.get("metadata") or {}),
        )


class OSRuntimeApprovalStore:
    def __init__(self, repository: OSRuntimeEventRepository):
        self.repository = repository

    def request(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        ticket: PermissionTicket,
        event_ids: list[str],
        session_id: str,
        task_id: str = "",
        profile_id: str = "",
        self_prompt: SelfPrompt | None = None,
        summary: str = "",
    ) -> ApprovalRequest:
        arbitration_id = str(arbitration.metadata.get("arbitration_id") or ticket.arbitration_id or "")
        approval_id = f"approval_{stable_hash([session_id, intent.intent_id, arbitration_id, event_ids])[:24]}"
        request = ApprovalRequest(
            approval_id=approval_id,
            session_id=session_id,
            profile_id=profile_id,
            intent_id=intent.intent_id,
            arbitration_id=arbitration_id,
            ticket_id=ticket.ticket_id,
            status="pending",
            requested_at=utc_now_iso(),
            event_ids=list(event_ids),
            task_id=task_id,
            summary=summary or arbitration.rationale or intent.why_now,
            payload={
                "intent": intent.to_dict(),
                "arbitration": arbitration.to_dict(),
                "ticket": ticket.to_dict(),
                "self_prompt": self_prompt.to_dict() if self_prompt else {},
            },
            metadata={"required_approvals": list(arbitration.required_approvals)},
        )
        event = OSRuntimeEvent(
            event_id=f"osr_{approval_id}",
            event_type=APPROVAL_REQUEST_EVENT,
            source=EventSource.SYSTEM,
            trace_id=event_ids[0] if event_ids else intent.intent_id,
            session_id=session_id,
            timestamp=request.requested_at,
            summary=request.summary,
            metadata={"approval_request": request.to_dict()},
            status="pending",
        )
        self.repository.append(event)
        return self.get(approval_id, session_id=session_id) or request

    def resolve(
        self,
        approval_id: str,
        *,
        approved: bool,
        session_id: str = "",
        resolver: str = "",
        reason: str = "",
    ) -> ApprovalRequest | None:
        request = self.get(approval_id, session_id=session_id)
        if request is None:
            return None
        status = "approved" if approved else "denied"
        resolved = ApprovalRequest.from_dict(
            {
                **request.to_dict(),
                "status": status,
                "resolved_at": utc_now_iso(),
                "resolver": resolver,
                "reason": reason,
            }
        )
        event = OSRuntimeEvent(
            event_id=f"osr_approval_resolution_{approval_id}_{status}",
            event_type=APPROVAL_RESOLUTION_EVENT,
            source=EventSource.SYSTEM,
            trace_id=request.event_ids[0] if request.event_ids else request.intent_id,
            session_id=request.session_id,
            timestamp=resolved.resolved_at,
            summary=f"Approval {status}: {approval_id}",
            metadata={"approval_request": resolved.to_dict(), "approval_id": approval_id},
            status=status,
        )
        self.repository.append(event)
        return resolved

    def is_approved(self, *, intent_id: str = "", arbitration_id: str = "", session_id: str = "") -> bool:
        for request in self.list(session_id=session_id, limit=500):
            if request.status != "approved":
                continue
            if intent_id and request.intent_id != intent_id:
                continue
            if arbitration_id and request.arbitration_id != arbitration_id:
                continue
            return True
        return False

    def get(self, approval_id: str, *, session_id: str = "") -> ApprovalRequest | None:
        for request in self.list(session_id=session_id, limit=500):
            if request.approval_id == approval_id:
                return request
        return None

    def list(self, *, session_id: str = "", status: str = "", limit: int = 50) -> list[ApprovalRequest]:
        events = (
            self.repository.list_by_session(session_id, limit=limit)
            if session_id
            else self.repository.list_recent(limit=limit)
        )
        by_id: dict[str, ApprovalRequest] = {}
        resolved_ids: set[str] = set()
        for event in events:
            if event.event_type not in {APPROVAL_REQUEST_EVENT, APPROVAL_RESOLUTION_EVENT}:
                continue
            payload = event.metadata.get("approval_request") if isinstance(event.metadata, dict) else None
            if not isinstance(payload, dict):
                continue
            request = ApprovalRequest.from_dict(payload)
            if not request.approval_id:
                continue
            if event.event_type == APPROVAL_RESOLUTION_EVENT:
                if request.approval_id in resolved_ids:
                    continue
                by_id[request.approval_id] = request
                resolved_ids.add(request.approval_id)
                continue
            if request.approval_id not in by_id:
                by_id[request.approval_id] = request
        requests = sorted(by_id.values(), key=lambda item: item.requested_at or item.resolved_at, reverse=True)
        if status:
            requests = [item for item in requests if item.status == status]
        return requests[: max(1, min(int(limit), 500))]


__all__ = [
    "APPROVAL_REQUEST_EVENT",
    "APPROVAL_RESOLUTION_EVENT",
    "ApprovalRequest",
    "OSRuntimeApprovalStore",
]
