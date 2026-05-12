"""Linz World login/session and authorization map operations."""

from __future__ import annotations

from .api_client import LinzWorldService, LinzWorldServiceError, default_service
from .event_state import LinzStateRepository
from .models import AuthState, AuthorizationMap, LoginSession, LoginState, utc_now_iso


def login(repository: LinzStateRepository | None = None, service: LinzWorldService | None = None) -> LoginSession:
    repo = repository or LinzStateRepository()
    identity = repo.get_identity()
    if not identity or not identity.is_complete():
        session = LoginSession(state=LoginState.LOGGED_OUT, last_error="Linz World identity is not registered.")
        return repo.save_login(session)
    try:
        result = (service or default_service()).login(identity.__dict__)
        session = LoginSession(
            state=LoginState.LOGGED_IN,
            token_ref=str(result.get("token_ref") or ""),
            expires_at=str(result.get("expires_at") or ""),
        )
    except Exception as exc:
        session = LoginSession(state=LoginState.LOGGED_OUT, last_error=f"Linz World login failed: {exc}")
    return repo.save_login(session)


def logout(repository: LinzStateRepository | None = None, service: LinzWorldService | None = None) -> LoginSession:
    repo = repository or LinzStateRepository()
    current = repo.get_login()
    try:
        if current.token_ref:
            (service or default_service()).logout(current.token_ref)
    finally:
        return repo.save_login(LoginSession(state=LoginState.LOGGED_OUT))


def refresh_authorization_map(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
) -> AuthorizationMap:
    repo = repository or LinzStateRepository()
    identity = repo.get_identity()
    session = repo.get_login()
    if not identity or not identity.is_complete():
        auth_map = AuthorizationMap(state=AuthState.FAILED, last_error="Linz World identity is not registered.")
        return repo.save_auth_map(auth_map)
    if session.state != LoginState.LOGGED_IN or not session.token_ref:
        auth_map = AuthorizationMap(state=AuthState.FAILED, last_error="Linz World login session is missing.")
        return repo.save_auth_map(auth_map)
    try:
        result = (service or default_service()).refresh_authorization_map(identity.__dict__, session.token_ref)
        auth_map = AuthorizationMap(
            state=AuthState.CURRENT,
            map_version=str(result.get("map_version") or ""),
            allowed_subjects=list(result.get("allowed_subjects") or []),
            allowed_event_types=list(result.get("allowed_event_types") or []),
            allowed_capabilities=list(result.get("allowed_capabilities") or []),
            last_refresh_at=utc_now_iso(),
        )
    except LinzWorldServiceError as exc:
        auth_map = AuthorizationMap(state=AuthState.FAILED, last_error=exc.message)
    except Exception as exc:
        auth_map = AuthorizationMap(state=AuthState.FAILED, last_error=f"Authorization map refresh failed: {exc}")
    return repo.save_auth_map(auth_map)
