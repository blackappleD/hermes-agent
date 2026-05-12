"""User-visible Linz World status summaries."""

from __future__ import annotations

from .event_state import LinzStateRepository
from .models import to_plain


def status_summary(repository: LinzStateRepository | None = None) -> dict:
    repo = repository or LinzStateRepository()
    identity = repo.get_identity()
    login = repo.get_login()
    auth_map = repo.get_auth_map()
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
            "compute_api_key_configured": bool(identity.compute_api_key_ref) if identity else False,
        },
        "login_state": login.state.value,
        "authorization_state": auth_map.state.value,
        "next_action": identity.next_action if identity else "Run hermes linz status to initialize identity.",
        "last_error": identity.last_error if identity else "",
    }


def events_summary(repository: LinzStateRepository | None = None, limit: int = 20, status: str | None = None) -> dict:
    repo = repository or LinzStateRepository()
    return {"success": True, "events": [to_plain(record) for record in repo.recent_events(limit=limit, status=status)]}
