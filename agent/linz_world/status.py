"""User-visible Linz World status summaries."""

from __future__ import annotations

from . import auth
from .config import load_linz_world_config
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
    cfg = load_linz_world_config()
    login_verified = login.state == LoginState.LOGGED_IN and bool(login.server_checked_at) and not login.last_error
    listener_last_error = login.listener_last_error
    if (
        not listener_last_error
        and not login.online
        and login.state == LoginState.LOGGED_IN
        and not auth_map.allowed_subscribe_subjects
    ):
        listener_last_error = "No Linz World NATS subscribe subjects are authorized."
    gateway_runtime = _gateway_runtime_summary()
    gateway_linz = gateway_runtime.get("linz_world", {})
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
        "listener_last_error": listener_last_error,
        "authorization_state": auth_map.state.value,
        "allowed_subscribe_subjects": auth_map.allowed_subscribe_subjects,
        "allowed_subscribe_event_types": auth_map.allowed_subscribe_event_types,
        "gateway_state": gateway_runtime.get("gateway_state", ""),
        "gateway_pid": gateway_runtime.get("pid"),
        "gateway_linz_platform_enabled": gateway_linz.get("enabled"),
        "gateway_linz_platform_state": gateway_linz.get("state", ""),
        "gateway_linz_platform_error": gateway_linz.get("error_message", ""),
        "bubble_protocol": {
            "enabled": cfg.bubble.enabled,
            "read_only": cfg.bubble.read_only,
            "allow_mutations": cfg.bubble.allow_mutations,
            "require_approval_for_mutations": cfg.bubble.require_approval_for_mutations,
            "default_task_slot_id": cfg.bubble.default_task_slot_id,
        },
        "next_action": identity.next_action if identity else "Run hermes linz status to initialize identity.",
        "last_error": (login.last_error or identity.last_error) if identity else login.last_error,
    }


def events_summary(repository: LinzStateRepository | None = None, limit: int = 20, status: str | None = None) -> dict:
    repo = repository or LinzStateRepository()
    return {"success": True, "events": [to_plain(record) for record in repo.recent_events(limit=limit, status=status)]}


def _gateway_runtime_summary() -> dict:
    result: dict = {}
    try:
        from gateway.status import read_runtime_status

        runtime = read_runtime_status() or {}
    except Exception:
        runtime = {}
    if isinstance(runtime, dict):
        result["gateway_state"] = str(runtime.get("gateway_state") or "")
        result["pid"] = runtime.get("pid") or None
        platforms = runtime.get("platforms") if isinstance(runtime.get("platforms"), dict) else {}
        linz_runtime = platforms.get("linz_world") if isinstance(platforms, dict) else {}
        if isinstance(linz_runtime, dict):
            result["linz_world"] = {
                "state": str(linz_runtime.get("state") or ""),
                "error_code": str(linz_runtime.get("error_code") or ""),
                "error_message": str(linz_runtime.get("error_message") or ""),
            }
    try:
        from gateway.config import Platform, load_gateway_config

        gateway_config = load_gateway_config()
        linz_platform = Platform("linz_world")
        platform_cfg = gateway_config.platforms.get(linz_platform)
        result.setdefault("linz_world", {})["enabled"] = bool(platform_cfg.enabled) if platform_cfg else False
    except Exception:
        result.setdefault("linz_world", {})["enabled"] = None
    return result
