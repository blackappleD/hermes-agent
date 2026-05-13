"""User-visible Linz World status summaries."""

from __future__ import annotations

from . import auth
from .event_state import LinzStateRepository
from .models import LoginState, to_plain


def status_summary(repository: LinzStateRepository | None = None, service=None, *, check_live: bool = True) -> dict:
    repo = repository or LinzStateRepository()
    identity = repo.get_identity()
    login = (
        auth.validate_login_session(repo, service, check_server=check_live)
        if check_live
        else repo.get_login()
    )
    auth_map = repo.get_auth_map()
    login_verified = login.state == LoginState.LOGGED_IN and bool(login.server_checked_at) and not login.last_error
    return {
        "success": True,
        "registration_state": identity.registration_state.value if identity else "pending",
        "identity": {
            "agent_id": identity.agent_id if identity else "",
            "os_id": identity.os_id if identity else "",
            "soul_id": identity.soul_id if identity else "",
            "soul_hash": identity.soul_hash if identity else "",
            "os_name": identity.os_name if identity else "",
            "account_id": identity.account_id if identity else "",
            "compute_token_configured": bool(login.token_ref),
        },
        "login_state": login.state.value,
        "login_verified": login_verified,
        "login_status_source": "server_checked" if login_verified else "local_cache_or_failed_check",
        "login_checked_at": login.server_checked_at,
        "listener_state": "online" if login.online else "offline",
        "listener_pid": login.listener_pid or None,
        "listener_started_at": login.listener_started_at,
        "authorization_state": auth_map.state.value,
        "next_action": identity.next_action if identity else "Run hermes linz status to initialize identity.",
        "last_error": (login.last_error or identity.last_error) if identity else login.last_error,
    }


def events_summary(repository: LinzStateRepository | None = None, limit: int = 20, status: str | None = None) -> dict:
    repo = repository or LinzStateRepository()
    return {"success": True, "events": [to_plain(record) for record in repo.recent_events(limit=limit, status=status)]}
