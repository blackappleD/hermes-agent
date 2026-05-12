from agent.linz_world.event_catalog import (
    is_forbidden_direct_settlement_transfer,
    is_formal_event,
)
from agent.linz_world.redaction import payload_summary


def test_event_catalog_rejects_unknown_and_legacy_events():
    assert is_formal_event("wsp.chat.message.sent", "message.sent")
    assert not is_formal_event("legacy.chat.message", "message.sent")
    assert not is_formal_event("wsp.chat.message.sent", "agent.made.this.up")


def test_forbidden_direct_settlement_transfer():
    assert is_forbidden_direct_settlement_transfer("wsp.mrk.settlement.completed", "settlement.completed")


def test_payload_summary_redacts_secrets():
    summary = payload_summary({"text": "hello", "token": "raw-secret", "nested": {"private_key": "key"}})
    assert "raw-secret" not in summary
    assert "private_key" in summary
    assert "[REDACTED]" in summary
