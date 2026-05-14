"""Runtime bridge hooks for Linz World bootstrap."""

from __future__ import annotations


def ensure_linz_identity_for_persona(*args, **kwargs):
    from .bootstrap import ensure_linz_identity_for_persona as _ensure

    return _ensure(*args, **kwargs)

__all__ = ["ensure_linz_identity_for_persona"]
