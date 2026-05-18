from experiment.events.library import REQUIRED_ENVELOPE_FIELDS, load_events, validate_event_envelope


def test_event_library_uses_formal_envelope() -> None:
    events = load_events()
    assert events
    for event in events.values():
        assert REQUIRED_ENVELOPE_FIELDS <= set(event)
        assert validate_event_envelope(event) == []
        assert isinstance(event["payload"], dict)
        assert event["subject"]
        assert event["event_type"]


def test_event_library_covers_required_phase_tags() -> None:
    events = load_events()
    tags = {tag for event in events.values() for tag in event.get("tags", [])}
    assert {"P0", "P1", "P2", "P3", "P4", "P5"} <= tags
