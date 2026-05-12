"""Linz World relationship operations."""

from __future__ import annotations

from .api_client import default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import RelationshipRecord


def read_relationships(counterparty_id: str = "", repository: LinzStateRepository | None = None, service=None) -> list[dict]:
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    try:
        result = svc.read_relationships(repo.get_login().token_ref, counterparty_id)
        return list(result.get("relationships") or [])
    except Exception:
        return repo.relationships()


def add_active_relationship(counterparty_id: str, summary: str = "", repository: LinzStateRepository | None = None, service=None) -> dict:
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    governance = preflight_side_effect(capability="relationship", repository=repo, service=svc)
    if not governance.allowed:
        return {"success": False, "error": {"code": governance.code, "message": governance.message}}
    result = svc.add_active_relationship(repo.get_login().token_ref, counterparty_id, summary)
    record = RelationshipRecord(
        relationship_id=str(result.get("relationship_id") or ""),
        counterparty_id=str(result.get("counterparty_id") or counterparty_id),
        state=str(result.get("state") or "ACTIVE"),
        summary=str(result.get("summary") or summary),
    )
    repo.append_list("relationships", record)
    return {"success": True, "relationship": record.__dict__}
