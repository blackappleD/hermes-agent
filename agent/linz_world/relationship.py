"""Linz World relationship operations."""

from __future__ import annotations

from .api_client import LinzWorldServiceError, default_service
from .event_state import LinzStateRepository
from .governance import preflight_side_effect
from .models import RelationshipRecord, to_plain


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


def add_active_relationship(
    counterparty_id: str,
    summary: str = "",
    repository: LinzStateRepository | None = None,
    service=None,
    relation_type: str = "OTHER",
) -> dict:
    counterparty_id = str(counterparty_id or "").strip()
    relation_type = str(relation_type or "OTHER").strip() or "OTHER"
    summary = str(summary or "").strip() or "手动添加关系"
    if not counterparty_id:
        return {
            "success": False,
            "error": {"code": "counterparty_missing", "message": "counterparty_id is required to add a relationship."},
        }
    repo = repository or LinzStateRepository()
    svc = service or default_service()
    governance = preflight_side_effect(capability="relationship", repository=repo, service=svc)
    if not governance.allowed:
        return {"success": False, "error": {"code": governance.code, "message": governance.message}}
    try:
        identity = repo.get_identity()
        result = svc.add_active_relationship(
            identity.__dict__ if identity else {},
            repo.get_login().token_ref,
            counterparty_id,
            summary,
            relation_type,
        )
    except LinzWorldServiceError as exc:
        return {"success": False, "error": {"code": exc.code, "message": exc.message}}
    record = RelationshipRecord(
        relationship_id=str(result.get("relationship_id") or result.get("id") or ""),
        counterparty_id=str(result.get("counterparty_id") or result.get("target_os_id") or counterparty_id),
        state=str(result.get("state") or result.get("status") or "ACTIVE"),
        summary=str(result.get("summary") or summary),
        relation_type=str(result.get("relation_type") or result.get("relationType") or relation_type),
    )
    repo.append_list("relationships", record)
    return {"success": True, "relationship": to_plain(record)}
