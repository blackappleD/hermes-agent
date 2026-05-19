"""HTTP client for the Linz World Bubble Protocol service."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .api_client import HttpLinzWorldService, LinzWorldServiceError, resolve_secret_ref
from .config import load_linz_world_config
from .bubble_models import BubbleMountRecord, BubbleRecord, BubbleSnapshot


class LinzBubbleClient:
    """Small client around `/api/v1/bubbles`.

    The server-side Bubble runtime remains authoritative. This client only
    normalizes request/response boundaries for Hermes tools and runtime
    adapters.
    """

    def __init__(self, service_url: str, timeout: float = 5.0):
        self._http = HttpLinzWorldService(service_url, timeout=timeout)

    @property
    def base_url(self) -> str:
        return self._http.base_url

    def get_snapshot(self, bubble_id: str, *, token_ref: str = "") -> BubbleSnapshot:
        bubble_id = _required(bubble_id, "bubble_id")
        data = self._http._get(
            f"/bubbles/{quote(bubble_id, safe='')}/snapshot",
            headers=_auth_headers(token_ref),
        )
        return BubbleSnapshot.from_api(data)

    def create_demand(
        self,
        *,
        name: str,
        goal: str,
        publisher_os_id: str,
        publisher_os_name: str = "",
        budget_amount: str = "",
        priority: str = "",
        token_ref: str = "",
    ) -> BubbleRecord:
        data = self._http._post(
            "/bubbles/demands",
            {
                "name": _required(name, "name"),
                "goal": _required(goal, "goal"),
                "publisher_os_id": _required(publisher_os_id, "publisher_os_id"),
                "publisher_os_name": str(publisher_os_name or ""),
                "budget_amount": str(budget_amount or ""),
                "priority": str(priority or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleRecord.from_api(data)

    def accept_demand(
        self,
        *,
        demand_bubble_id: str,
        tech_lead_os_id: str,
        tech_lead_os_name: str = "",
        token_ref: str = "",
    ) -> BubbleRecord:
        data = self._http._post(
            f"/bubbles/demands/{quote(_required(demand_bubble_id, 'demand_bubble_id'), safe='')}/accept",
            {
                "tech_lead_os_id": _required(tech_lead_os_id, "tech_lead_os_id"),
                "tech_lead_os_name": str(tech_lead_os_name or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleRecord.from_api(data)

    def create_task(
        self,
        *,
        parent_bubble_id: str,
        name: str,
        goal: str,
        tech_lead_os_id: str,
        slots: list[dict[str, Any]] | None = None,
        membrane: dict[str, Any] | None = None,
        acceptance: dict[str, Any] | None = None,
        dissolution_contract: dict[str, Any] | None = None,
        token_ref: str = "",
    ) -> BubbleRecord:
        payload: dict[str, Any] = {
            "parent_bubble_id": _required(parent_bubble_id, "parent_bubble_id"),
            "name": _required(name, "name"),
            "goal": _required(goal, "goal"),
            "tech_lead_os_id": _required(tech_lead_os_id, "tech_lead_os_id"),
        }
        if slots:
            payload["slots"] = slots
        if membrane:
            payload["membrane"] = membrane
        if acceptance:
            payload["acceptance"] = acceptance
        if dissolution_contract:
            payload["dissolution_contract"] = dissolution_contract
        data = self._http._post("/bubbles/tasks", payload, headers=_auth_headers(token_ref))
        return BubbleRecord.from_api(data)

    def request_mount(
        self,
        *,
        task_bubble_id: str,
        mounted_bubble_id: str,
        slot_id: str,
        requester_os_id: str,
        relation_role: str = "",
        request_note: str = "",
        token_ref: str = "",
    ) -> BubbleMountRecord:
        data = self._http._post(
            f"/bubbles/tasks/{quote(_required(task_bubble_id, 'task_bubble_id'), safe='')}/mounts",
            {
                "mounted_bubble_id": _required(mounted_bubble_id, "mounted_bubble_id"),
                "slot_id": _required(slot_id, "slot_id"),
                "relation_role": str(relation_role or ""),
                "requester_os_id": _required(requester_os_id, "requester_os_id"),
                "request_note": str(request_note or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleMountRecord.from_api(data)

    def review_mount(
        self,
        *,
        mount_id: str,
        reviewer_os_id: str,
        approved: bool,
        reject_reason: str = "",
        token_ref: str = "",
    ) -> BubbleMountRecord:
        data = self._http._post(
            f"/bubbles/mounts/{quote(_required(mount_id, 'mount_id'), safe='')}/review",
            {
                "reviewer_os_id": _required(reviewer_os_id, "reviewer_os_id"),
                "approved": bool(approved),
                "reject_reason": str(reject_reason or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleMountRecord.from_api(data)

    def submit_task_artifact(
        self,
        *,
        task_bubble_id: str,
        mount_id: str,
        actor_os_id: str,
        artifact_ref: str,
        delivery_note: str,
        evidence_refs: list[str] | None = None,
        known_issues: str = "",
        next_action: str = "",
        token_ref: str = "",
    ) -> BubbleRecord:
        data = self._http._post(
            f"/bubbles/tasks/{quote(_required(task_bubble_id, 'task_bubble_id'), safe='')}/artifacts",
            {
                "mount_id": _required(mount_id, "mount_id"),
                "actor_os_id": _required(actor_os_id, "actor_os_id"),
                "artifact_ref": _required(artifact_ref, "artifact_ref"),
                "delivery_note": _required(delivery_note, "delivery_note"),
                "evidence_refs": list(evidence_refs or []),
                "known_issues": str(known_issues or ""),
                "next_action": str(next_action or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleRecord.from_api(data)

    def review_task_acceptance(
        self,
        *,
        task_bubble_id: str,
        reviewer_os_id: str,
        approved: bool,
        reason: str = "",
        token_ref: str = "",
    ) -> BubbleRecord:
        data = self._http._post(
            f"/bubbles/tasks/{quote(_required(task_bubble_id, 'task_bubble_id'), safe='')}/acceptance",
            {
                "reviewer_os_id": _required(reviewer_os_id, "reviewer_os_id"),
                "approved": bool(approved),
                "reason": str(reason or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleRecord.from_api(data)

    def submit_demand_delivery(
        self,
        *,
        demand_bubble_id: str,
        tech_lead_os_id: str,
        summary_ref: str,
        summary_note: str,
        evidence_refs: list[str] | None = None,
        token_ref: str = "",
    ) -> BubbleRecord:
        data = self._http._post(
            f"/bubbles/demands/{quote(_required(demand_bubble_id, 'demand_bubble_id'), safe='')}/delivery-summary",
            {
                "tech_lead_os_id": _required(tech_lead_os_id, "tech_lead_os_id"),
                "summary_ref": _required(summary_ref, "summary_ref"),
                "summary_note": _required(summary_note, "summary_note"),
                "evidence_refs": list(evidence_refs or []),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleRecord.from_api(data)

    def review_demand_acceptance(
        self,
        *,
        demand_bubble_id: str,
        reviewer_os_id: str,
        approved: bool,
        reason: str = "",
        token_ref: str = "",
    ) -> BubbleRecord:
        data = self._http._post(
            f"/bubbles/demands/{quote(_required(demand_bubble_id, 'demand_bubble_id'), safe='')}/acceptance",
            {
                "reviewer_os_id": _required(reviewer_os_id, "reviewer_os_id"),
                "approved": bool(approved),
                "reason": str(reason or ""),
            },
            headers=_auth_headers(token_ref),
        )
        return BubbleRecord.from_api(data)


def default_bubble_client(config=None) -> LinzBubbleClient:
    cfg = load_linz_world_config(config)
    if not cfg.service_url:
        raise LinzWorldServiceError(
            "missing_service_config",
            "Linz World service_url is not configured.",
        )
    return LinzBubbleClient(cfg.service_url)


def _auth_headers(token_ref: str) -> dict[str, str] | None:
    token_ref = str(token_ref or "").strip()
    if not token_ref:
        return None
    token = resolve_secret_ref(token_ref)
    if not token:
        raise LinzWorldServiceError(
            "login_secret_missing",
            "Linz World login token secret is unavailable.",
        )
    return {"Authorization": f"Bearer {token}"}


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise LinzWorldServiceError("invalid_request", f"Missing required Bubble field: {name}.")
    return text
