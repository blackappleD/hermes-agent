"""Linz World relationship operations."""

from __future__ import annotations

from .api_client import LinzWorldServiceError, default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import RelationshipRecord


def read_relationships(counterparty_id: str = "", repository: LinzStateRepository | None = None, service=None) -> dict:
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    try:
        identity = repo.get_identity()
        result = svc.read_relationships(identity.__dict__ if identity else {}, repo.get_login().token_ref, counterparty_id)
        return {
            "success": True,
            "relationships": list(result.get("relationships") or []),
            "projection": dict(result.get("projection") or {}),
        }
    except Exception:
        return {"success": True, "relationships": repo.relationships(), "projection": {}}


def add_active_relationship(counterparty_id: str, summary: str = "", repository: LinzStateRepository | None = None, service=None) -> dict:
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    governance = preflight_side_effect(capability="relationship", repository=repo, service=svc)
    if not governance.allowed:
        return {"success": False, "error": {"code": governance.code, "message": governance.message}}
    try:
        result = svc.add_active_relationship(repo.get_login().token_ref, counterparty_id, summary)
    except LinzWorldServiceError as exc:
        return {"success": False, "error": {"code": exc.code, "message": exc.message}}
    record = RelationshipRecord(
        relationship_id=str(result.get("relationship_id") or ""),
        counterparty_id=str(result.get("counterparty_id") or counterparty_id),
        state=str(result.get("state") or "ACTIVE"),
        summary=str(result.get("summary") or summary),
    )
    repo.append_list("relationships", record)
    return {"success": True, "relationship": record.__dict__}
