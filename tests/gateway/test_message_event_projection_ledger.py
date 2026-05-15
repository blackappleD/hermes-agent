from __future__ import annotations

from gateway.config import Platform
from gateway.event_projection_store import EventProjectionStore
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


def test_message_event_projection_records_source_payload_status_and_session(tmp_path):
    store = EventProjectionStore(root=tmp_path / "home")
    try:
        event = MessageEvent(
            text="hello from gateway",
            message_type=MessageType.TEXT,
            source=SessionSource(
                platform=Platform.SLACK,
                chat_id="C123",
                chat_name="ops",
                user_id="U123",
                user_name="Ada",
                message_id="166000.100",
            ),
            raw_message={"message_id": "166000.100", "payload": {"text": "hello from gateway"}},
            message_id="166000.100",
        )

        record_id = store.record_message_event_projected(
            event,
            session_id="session-slack-1",
            session_key="slack:C123:U123",
            session_message_ref="166000.100",
        )

        detail = store.get_record(record_id)

        assert detail is not None
        assert detail["record"]["source_category"] == "slack"
        assert detail["record"]["event_id"] == "166000.100"
        assert "hello from gateway" in detail["record"]["payload_summary"]
        assert detail["record"]["projection_status"] == "projected"
        assert detail["projection"]["message_event_id"] == "166000.100"
        assert detail["projection"]["message_type"] == "text"
        assert detail["projection"]["session_id"] == "session-slack-1"
        assert detail["projection"]["session_key"] == "slack:C123:U123"
        assert detail["projection"]["session_message_ref"] == "166000.100"
    finally:
        store.close()
