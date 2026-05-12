"""Identity bootstrap for Linz World original spirits."""

from __future__ import annotations

from .api_client import LinzWorldService, LinzWorldServiceError, default_service
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
    svc = service or default_service(config)
    try:
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

    required = ("os_id", "soul_id", "os_name", "account_id")
    missing = [name for name in required if not result.get(name)]
    if missing:
        return repo.save_failed_identity(
            f"Linz World registration response missing: {', '.join(missing)}",
            "Check Linz World identity registry response and retry.",
        )
    identity = WorldIdentity(
        profile_id=repo.profile_id,
        os_id=str(result["os_id"]),
        soul_id=str(result["soul_id"]),
        os_name=str(result["os_name"]),
        account_id=str(result["account_id"]),
        registration_state=RegistrationStatus.REGISTERED,
        authorization_state=AuthState.UNKNOWN,
        last_error="",
        next_action="",
    )
    return repo.save_identity(identity)
