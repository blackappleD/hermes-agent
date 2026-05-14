"""Structured daily debug logging for the os_runtime evaluation route.

The runtime route is intentionally split across small pure components.  This
module gives operators a single JSONL trace that shows each stage's compact
input/output snapshot without changing the decision path.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


PIPELINE_ROUTE = (
    "goal_event",
    "signal_set",
    "life_state",
    "tension_operation",
    "tension_set",
    "action_potential",
    "self_prompt",
    "open_intent",
    "arbiter",
)

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "bearer",
    "client_secret",
    "credential",
    "credentials",
    "id_token",
    "key_material",
    "password",
    "private_key",
    "refresh_token",
    "raw_secret",
    "secret",
    "session_token",
    "token",
}
_MAX_STRING_CHARS = 1200
_MAX_LIST_ITEMS = 40
_MAX_DEPTH = 8


def log_pipeline_step(
    *,
    surface: str,
    session_id: str,
    phase: str,
    step: str,
    data: dict[str, Any] | None = None,
    profile_id: str = "",
    trace_id: str = "",
) -> None:
    """Append one JSONL record to ``$HERMES_HOME/logs/os_runtime_YYYYMMDD.log``.

    Logging is best-effort and never raises into the runtime path.  It is on
    by default for normal runs, can be disabled with ``HERMES_OS_RUNTIME_LOG=0``,
    and is skipped under pytest unless explicitly enabled with
    ``HERMES_OS_RUNTIME_LOG=1`` to avoid writing to a developer's real home.
    """

    if not _logging_enabled():
        return

    try:
        now = datetime.now().astimezone()
        record = {
            "timestamp": now.isoformat(timespec="milliseconds"),
            "route": " -> ".join(PIPELINE_ROUTE),
            "surface": surface,
            "session_id": session_id,
            "profile_id": profile_id,
            "phase": phase,
            "step": step,
            "step_index": _step_index(step),
            "trace_id": trace_id,
            "data": _safe_value(data or {}),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        line = _redact_line(line)
        log_path = _log_path(now)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()
    except Exception:
        return


def _logging_enabled() -> bool:
    configured = os.getenv("HERMES_OS_RUNTIME_LOG", "").strip().lower()
    if configured in {"0", "false", "no", "off"}:
        return False
    if os.getenv("PYTEST_CURRENT_TEST") and configured not in {"1", "true", "yes", "on"}:
        return False
    return True


def _log_path(now: datetime) -> Path:
    return get_hermes_home() / "logs" / f"os_runtime_{now.strftime('%Y%m%d')}.log"


def _step_index(step: str) -> int:
    normalized = step.strip().lower()
    try:
        return PIPELINE_ROUTE.index(normalized) + 1
    except ValueError:
        return 0


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return _truncate(_redact_text(value))
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict"):
        try:
            return _safe_value(value.to_dict(), depth=depth + 1)
        except Exception:
            return _truncate(_redact_text(str(value)))
    if is_dataclass(value):
        return _safe_value(asdict(value), depth=depth + 1)
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if text_key.lower() in _SENSITIVE_KEYS:
                output[text_key] = "[REDACTED]"
            else:
                output[text_key] = _safe_value(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        output = [_safe_value(item, depth=depth + 1) for item in items[:_MAX_LIST_ITEMS]]
        if len(items) > _MAX_LIST_ITEMS:
            output.append(f"[TRUNCATED {len(items) - _MAX_LIST_ITEMS} ITEMS]")
        return output
    return _truncate(_redact_text(str(value)))


def _redact_line(line: str) -> str:
    try:
        from agent.redact import redact_sensitive_text

        return redact_sensitive_text(line, force=True)
    except Exception:
        return line


def _redact_text(text: str) -> str:
    return _redact_line(text)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_STRING_CHARS:
        return text
    return f"{text[: _MAX_STRING_CHARS - 32]}... [truncated {len(text)} chars]"


__all__ = ["PIPELINE_ROUTE", "log_pipeline_step"]
