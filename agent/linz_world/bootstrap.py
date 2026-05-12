"""Fail-closed persona bootstrap for Linz World identity."""

from __future__ import annotations

from .config import load_linz_world_config
from .event_state import LinzStateRepository
from .identity import ensure_original_spirit_identity
from .models import WorldIdentity


class LinzBootstrapError(RuntimeError):
    def __init__(self, identity: WorldIdentity):
        self.identity = identity
        message = identity.last_error or "Linz World identity is not registered."
        if identity.next_action:
            message = f"{message} Next action: {identity.next_action}"
        super().__init__(message)


def ensure_linz_identity_for_persona(
    repository: LinzStateRepository | None = None,
    service=None,
    *,
    config: dict | None = None,
) -> WorldIdentity | None:
    cfg = load_linz_world_config(config)
    if not cfg.enabled:
        return None
    identity = ensure_original_spirit_identity(repository=repository, service=service, config=config)
    if not identity.is_complete():
        raise LinzBootstrapError(identity)
    return identity
