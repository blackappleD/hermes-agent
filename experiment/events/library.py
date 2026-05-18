from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_EVENT_FILE = Path(__file__).with_name("event_library.json")
REQUIRED_ENVELOPE_FIELDS = {"subject", "event_type", "event_id", "payload"}


def load_events(path: Path = _EVENT_FILE) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        events = json.load(fh)
    return {event["event_id"]: event for event in events}


def load_event(event_id: str) -> dict[str, Any]:
    events = load_events()
    try:
        return events[event_id]
    except KeyError as exc:
        raise KeyError(f"unknown experiment event: {event_id}") from exc


def validate_event_envelope(event: dict[str, Any]) -> list[str]:
    return sorted(REQUIRED_ENVELOPE_FIELDS - set(event))
