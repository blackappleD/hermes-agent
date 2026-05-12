"""Identity bootstrap for Linz World original spirits."""

from __future__ import annotations

from .api_client import LinzWorldService, LinzWorldServiceError, default_service, store_runtime_secret
from .config import load_linz_world_config
from .event_state import LinzStateRepository
from .models import AuthState, RegistrationStatus, WorldIdentity


def ensure_original_spirit_identity(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
    *,
    config: dict | None = None,
) -> WorldIdentity:
    repo = repository or LinzStateRepository()
    existing = repo.get_identity()
    if existing and existing.is_complete():
        return existing

    cfg = load_linz_world_config(config)
    try:
        svc = service or default_service(config)
        result = svc.register_original_spirit(repo.profile_id, cfg.os_name)
    except LinzWorldServiceError as exc:
        return repo.save_failed_identity(
            exc.message,
            "Retry after Linz World identity registry is reachable.",
        )
    except Exception as exc:
        return repo.save_failed_identity(
            f"Linz World registration failed: {exc}",
            "Retry after Linz World identity registry is reachable.",
        )

    agent_id = str(result.get("agentId") or result.get("agent_id") or result.get("os_id") or "")
    soul_id = str(result.get("soulId") or result.get("soul_id") or "")
    soul_hash = str(result.get("soulHash") or result.get("soul_hash") or "")
    required = {"agentId": agent_id, "soulId": soul_id, "soulHash": soul_hash}
    missing = [name for name, value in required.items() if not value]
    if missing:
        return repo.save_failed_identity(
            f"Linz World registration response missing: {', '.join(missing)}",
            "Check Linz World identity registry response and retry.",
        )
    access_token_ref = str(result.get("access_token_ref") or "")
    if result.get("accessToken"):
        access_token_ref = store_runtime_secret("access_token", str(result["accessToken"]))
    expires_in = result.get("expiresIn")
    identity = WorldIdentity(
        profile_id=repo.profile_id,
        agent_id=agent_id,
        os_id=agent_id,
        soul_id=soul_id,
        soul_hash=soul_hash,
        os_name=str(result.get("os_name") or cfg.os_name),
        account_id=str(result.get("accountId") or result.get("account_id") or agent_id),
        access_token_ref=access_token_ref,
        access_token_expires_at=str(expires_in or ""),
        registered_at=str(result.get("registeredAt") or result.get("registered_at") or ""),
        compute_api_key_ref=str(result.get("compute_api_key_ref") or cfg.compute_api_key_ref or ""),
        registration_state=RegistrationStatus.REGISTERED,
        authorization_state=AuthState.UNKNOWN,
        last_error="",
        next_action="",
    )
    return repo.save_identity(identity)
