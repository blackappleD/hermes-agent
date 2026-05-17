"""Linz World login/session and authorization map operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .api_client import (
    LinzWorldService,
    LinzWorldServiceError,
    default_service,
    delete_runtime_secret,
    store_runtime_secret,
)
from .event_state import LinzStateRepository
from .models import AuthState, AuthorizationMap, LoginSession, LoginState, utc_now_iso


def login(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
    *,
    config: dict | None = None,
    refresh_map: bool = True,
) -> LoginSession:
    repo = repository or LinzStateRepository()
    identity = repo.get_identity()
    if not identity or not identity.is_complete():
        session = LoginSession(state=LoginState.LOGGED_OUT, last_error="Linz World identity is not registered.")
        return repo.save_login(session)
    try:
        svc = service or default_service(config)
        result = svc.login(identity.__dict__)
        token_ref = str(result.get("token_ref") or "")
        if result.get("token"):
            token_ref = store_runtime_secret("event_token", str(result["token"]))
        expires_at = str(result.get("expiresAt") or result.get("expires_at") or "")
        if not expires_at:
            expires_at = _expires_in_to_iso(result.get("expiresIn") or result.get("expires_in"))
        session = LoginSession(
            state=LoginState.LOGGED_IN,
            token_ref=token_ref,
            expires_at=expires_at,
            credential_id=str(result.get("credentialId") or result.get("credential_id") or ""),
            subject_claims=list(result.get("subjectClaims") or result.get("subject_claims") or []),
            online=False,
            server_checked_at=utc_now_iso(),
        )
    except Exception as exc:
        session = LoginSession(state=LoginState.LOGGED_OUT, last_error=f"Linz World login failed: {exc}")
        return repo.save_login(session)
    saved = repo.save_login(session)
    if refresh_map:
        refresh_authorization_map(repo, svc)
    return saved


def ensure_login_session(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
    *,
    config: dict | None = None,
    check_server: bool = True,
) -> LoginSession:
    """Ensure the current profile has an active Linz World login session.

    Agent startup should not merely validate a missing or expired cached
    session. Once identity exists, logging in is the safe prerequisite for
    later governed tools such as chat, compute, memory, and relationship
    mutation. Transient verification failures that leave a token in
    ``UNVERIFIED`` state are preserved instead of discarding the cached token.
    """

    repo = repository or LinzStateRepository()
    session = validate_login_session(repo, service, config=config, check_server=check_server)
    if session.state == LoginState.LOGGED_IN and session.token_ref:
        return session
    if session.state in {LoginState.LOGGED_OUT, LoginState.EXPIRED} or not session.token_ref:
        return login(repo, service, config=config)
    return session


def logout(repository: LinzStateRepository | None = None, service: LinzWorldService | None = None) -> LoginSession:
    repo = repository or LinzStateRepository()
    current = repo.get_login()
    try:
        if current.token_ref:
            (service or default_service()).logout(current.token_ref)
    except Exception:
        pass
    delete_runtime_secret(current.token_ref)
    return repo.save_login(LoginSession(state=LoginState.LOGGED_OUT))


def refresh_authorization_map(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
    *,
    config: dict | None = None,
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
        result = (service or default_service(config)).refresh_authorization_map(identity.__dict__, session.token_ref)
        auth_map = _authorization_map_from_result(result)
    except LinzWorldServiceError as exc:
        auth_map = AuthorizationMap(state=AuthState.FAILED, last_error=exc.message)
    except Exception as exc:
        auth_map = AuthorizationMap(state=AuthState.FAILED, last_error=f"Authorization map refresh failed: {exc}")
    return repo.save_auth_map(auth_map)


def validate_login_session(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
    *,
    config: dict | None = None,
    check_server: bool = True,
) -> LoginSession:
    """Refresh the effective login state instead of trusting cached state."""

    repo = repository or LinzStateRepository()
    session = _sync_listener_liveness(repo)
    if session.state not in {LoginState.LOGGED_IN, LoginState.UNVERIFIED}:
        return session
    if _session_is_expired(session):
        session.state = LoginState.EXPIRED
        session.token_ref = ""
        session.last_error = "Linz World login session has expired."
        session.online = False
        session.listener_pid = 0
        session.listener_started_at = ""
        session.listener_last_error = ""
        return repo.save_login(session)
    if not check_server:
        return session
    identity = repo.get_identity()
    if not identity or not identity.is_complete():
        session.state = LoginState.LOGGED_OUT
        session.token_ref = ""
        session.last_error = "Linz World identity is not registered."
        return repo.save_login(session)
    try:
        result = (service or default_service(config)).refresh_authorization_map(identity.__dict__, session.token_ref)
    except LinzWorldServiceError as exc:
        repo.save_auth_map(AuthorizationMap(state=AuthState.FAILED, last_error=exc.message))
        session.server_checked_at = utc_now_iso()
        session.last_error = f"Linz World login verification failed: {exc.message}"
        if _is_invalid_session_error(exc):
            session.state = LoginState.EXPIRED
            session.token_ref = ""
            session.online = False
            session.listener_pid = 0
            session.listener_started_at = ""
            session.listener_last_error = ""
        else:
            session.state = LoginState.UNVERIFIED
        return repo.save_login(session)
    except Exception as exc:
        repo.save_auth_map(
            AuthorizationMap(
                state=AuthState.FAILED,
                last_error=f"Authorization map refresh failed: {exc}",
            )
        )
        session.state = LoginState.UNVERIFIED
        session.server_checked_at = utc_now_iso()
        session.last_error = f"Linz World login verification failed: {exc}"
        return repo.save_login(session)

    repo.save_auth_map(_authorization_map_from_result(result))
    session.state = LoginState.LOGGED_IN
    session.server_checked_at = utc_now_iso()
    session.last_error = ""
    return repo.save_login(session)


def _authorization_map_from_result(result: dict) -> AuthorizationMap:
    return AuthorizationMap(
        state=AuthState.CURRENT,
        map_version=str(result.get("map_version") or ""),
        allowed_publish_subjects=list(result.get("allowed_publish_subjects") or []),
        allowed_publish_event_types=list(result.get("allowed_publish_event_types") or []),
        allowed_subscribe_subjects=list(result.get("allowed_subscribe_subjects") or []),
        allowed_subscribe_event_types=list(result.get("allowed_subscribe_event_types") or []),
        allowed_capabilities=list(result.get("allowed_capabilities") or []),
        last_refresh_at=utc_now_iso(),
    )


def _sync_listener_liveness(repo: LinzStateRepository) -> LoginSession:
    session = repo.get_login()
    changed = False
    if session.listener_pid:
        if _pid_exists(session.listener_pid):
            if not session.online:
                session.online = True
                changed = True
        else:
            session.online = False
            session.listener_pid = 0
            session.listener_started_at = ""
            session.listener_last_error = "Linz World listener process is no longer running."
            changed = True
    elif session.online:
        session.online = False
        session.listener_last_error = "Linz World listener process is no longer running."
        changed = True
    return repo.save_login(session) if changed else session


def _pid_exists(pid: int) -> bool:
    if not pid:
        return False
    try:
        from gateway.status import _pid_exists as gateway_pid_exists

        return bool(gateway_pid_exists(int(pid)))
    except Exception:
        return False


def _session_is_expired(session: LoginSession) -> bool:
    expires_at = _parse_datetime(session.expires_at)
    if not expires_at:
        return False
    return expires_at <= datetime.now(timezone.utc)


def _parse_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expires_in_to_iso(value) -> str:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=seconds))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _is_invalid_session_error(exc: LinzWorldServiceError) -> bool:
    code = str(getattr(exc, "code", "") or "").lower()
    message = str(getattr(exc, "message", "") or "").lower()
    if code in {"401", "403", "login_missing", "login_secret_missing", "invalid_token", "token_expired"}:
        return True
    return "token" in message and any(marker in message for marker in ("missing", "invalid", "expired", "unavailable"))
