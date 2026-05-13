"""Profile-scoped Linz identity field helpers."""

from __future__ import annotations

from .event_state import LinzStateRepository
from .models import WorldIdentity


def load_world_identity(repository: LinzStateRepository | None = None) -> WorldIdentity | None:
    return (repository or LinzStateRepository()).get_identity()


def save_world_identity(identity: WorldIdentity, repository: LinzStateRepository | None = None) -> WorldIdentity:
    return (repository or LinzStateRepository()).save_identity(identity)
