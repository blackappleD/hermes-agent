"""Identity bootstrap for Linz World original spirits."""

from __future__ import annotations

from .api_client import LinzWorldService, LinzWorldServiceError, default_service, store_runtime_secret
from .config import load_linz_world_config
from .event_state import LinzStateRepository
from .key_material import ensure_key_material
from .models import AuthState, RegistrationStatus, WorldIdentity


def ensure_original_spirit_identity(
    repository: LinzStateRepository | None = None,
    service: LinzWorldService | None = None,
    *,
    config: dict | None = None,
) -> WorldIdentity:
    repo = repository or LinzStateRepository()
    existing = repo.get_identity()
    if existing and existing.is_complete() and existing.private_key_path and existing.public_key_fingerprint:
        return existing

    cfg = load_linz_world_config(config)
    if not cfg.persona_seed:
        return repo.save_failed_identity(
            "Linz World persona_seed is not configured.",
            "Run hermes setup linz and provide a persona seed before loading this agent.",
        )
    key_material = ensure_key_material(
        repo.profile_id,
        private_key_path=existing.private_key_path if existing else "",
        public_key_path=existing.public_key_path if existing else "",
    )
    try:
        svc = service or default_service(config)
        result = svc.register_original_spirit(
            repo.profile_id,
            cfg.os_name,
            cfg.persona_seed,
            cfg.os_type,
            cfg.runtime_type,
            key_material.public_key_pem,
            key_material.public_key_type,
            key_material.fingerprint,
        )
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

    agent_id = str(
        result.get("agentId")
        or result.get("agent_id")
        or result.get("os_id")
        or result.get("osId")
        or ""
    )
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
    token = result.get("accessToken") or result.get("access_token") or result.get("token")
    if token:
        access_token_ref = store_runtime_secret("access_token", str(token))
    expires_in = result.get("expiresIn") or result.get("expires_in")
    identity = WorldIdentity(
        profile_id=repo.profile_id,
        agent_id=agent_id,
        os_id=agent_id,
        soul_id=soul_id,
        soul_hash=soul_hash,
        os_name=str(result.get("os_name") or result.get("osName") or cfg.os_name),
        account_id=str(result.get("accountId") or result.get("account_id") or agent_id),
        access_token_ref=access_token_ref,
        access_token_expires_at=str(expires_in or ""),
        registered_at=str(result.get("registeredAt") or result.get("registered_at") or ""),
        private_key_path=key_material.private_key_path,
        public_key_path=key_material.public_key_path,
        public_key_type=key_material.public_key_type,
        public_key_fingerprint=key_material.fingerprint,
        registration_state=RegistrationStatus.REGISTERED,
        authorization_state=AuthState.UNKNOWN,
        last_error="",
        next_action="",
    )
    return repo.save_identity(identity)
