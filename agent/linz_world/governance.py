"""Governance preflight helpers for Linz World side effects."""

from __future__ import annotations

from .auth import refresh_authorization_map
from .event_catalog import is_forbidden_direct_settlement_transfer, is_formal_event
from .event_state import LinzStateRepository
from .models import AuthState, GovernanceResult, GovernanceStatus, LoginState


def reject(code: str, message: str, next_action: str = "") -> GovernanceResult:
    return GovernanceResult(GovernanceStatus.REJECTED, code, message, next_action)


def allow() -> GovernanceResult:
    return GovernanceResult(GovernanceStatus.ALLOWED, "allowed", "Allowed.")


def preflight_side_effect(
    *,
    capability: str,
    repository: LinzStateRepository | None = None,
    service=None,
    subject: str = "",
    event_type: str = "",
    payload=None,
) -> GovernanceResult:
    repo = repository or LinzStateRepository()
    identity = repo.get_identity()
    if not identity or not identity.is_complete():
        return reject("identity_missing", "Linz World identity is not registered.", "Register identity before external side effects.")
    session = repo.get_login()
    if session.state != LoginState.LOGGED_IN or not session.token_ref:
        return reject("login_missing", "Linz World login session is missing.", "Run hermes linz login.")
    if capability == "publish":
        if not isinstance(payload, dict):
            return reject("invalid_payload", "World event payload must be a structured object.")
        if not is_formal_event(subject, event_type):
            return reject("unknown_event", "Unknown Linz World subject/event_type; external publish blocked.")
        if is_forbidden_direct_settlement_transfer(subject, event_type):
            return reject("forbidden_settlement_transfer", "Settlement transfer events require human governance.")
    auth_map = refresh_authorization_map(repo, service)
    if auth_map.state != AuthState.CURRENT:
        return reject(
            "authorization_refresh_failed",
            "Authorization map refresh failed; external side effect blocked.",
            "Retry after Linz World authorization service is reachable.",
        )
    if not auth_map.allows_capability(capability):
        return reject("capability_not_authorized", f"Linz World capability is not authorized: {capability}")
    if capability == "publish" and not auth_map.allows_event(subject, event_type):
        return reject("event_not_authorized", "Linz World subject/event_type is not authorized for publish.")
    return allow()
