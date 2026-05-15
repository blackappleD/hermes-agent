from __future__ import annotations

from gateway.config import Platform
from gateway.event_projection_store import EventProjectionStore
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


def _message_event(index: int, *, platform: Platform = Platform.TELEGRAM, subject: str | None = None) -> MessageEvent:
    raw = {"message_id": f"platform-{index}", "payload": {"index": index}}
    if subject:
        raw.update({"subject": subject, "event_type": "message.sent"})
    return MessageEvent(
        text=f"hello {index}",
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=platform,
            chat_id=f"chat-{index % 3}",
            chat_name=f"Chat {index % 3}",
            user_id=f"user-{index}",
            user_name=f"User {index}",
            message_id=f"msg-{index}",
        ),
        raw_message=raw,
        message_id=f"msg-{index}",
    )


def test_store_initializes_profile_scoped_schema_and_lists_empty(tmp_path):
    store = EventProjectionStore(root=tmp_path / "home")
    try:
        assert store.path == tmp_path / "home" / "gateway" / "message_events.db"
        result = store.list_records()
        assert result == {"records": [], "next_cursor": None}
    finally:
        store.close()


def test_store_persists_records_after_close_and_reopen(tmp_path):
    home = tmp_path / "home"
    first = EventProjectionStore(root=home)
    try:
        first.record_message_event_projected(_message_event(1), session_id="session-1", session_key="telegram:chat-1")
    finally:
        first.close()

    second = EventProjectionStore(root=home)
    try:
        result = second.list_records()
        assert len(result["records"]) == 1
        assert result["records"][0]["message_event_id"] == "msg-1"
        detail = second.get_record(result["records"][0]["record_id"])
        assert detail is not None
        assert detail["projection"]["session_id"] == "session-1"
    finally:
        second.close()


def test_list_records_filters_by_source_status_subject_type_query_and_time(tmp_path):
    store = EventProjectionStore(root=tmp_path / "home")
    try:
        linz = _message_event(1, platform=Platform.WEBHOOK, subject="wsp.chat.message.sent")
        linz.raw_message.update({"event_id": "evt-1", "nats_sequence": 42, "sequence_key": "stream:consumer:42"})
        store.record_message_event_projected(linz, consume_status="handled")
        store.record_message_event_projected(_message_event(2), consume_status="failed", projection_status="projected")

        linz_only = store.list_records(source_category="linz_world_nats")
        assert [r["event_id"] for r in linz_only["records"]] == ["evt-1"]

        failed = store.list_records(consume_status="failed")
        assert len(failed["records"]) == 1
        assert failed["records"][0]["message_event_id"] == "msg-2"

        subject = store.list_records(subject="wsp.chat.message.sent", event_type="message.sent")
        assert len(subject["records"]) == 1

        query = store.list_records(q="evt-1")
        assert len(query["records"]) == 1

        newest = store.list_records(limit=1)["records"][0]
        ranged = store.list_records(from_time=newest["consumed_at"], to_time=newest["consumed_at"])
        assert [r["record_id"] for r in ranged["records"]] == [newest["record_id"]]
    finally:
        store.close()


def test_cursor_pagination_is_stable_when_new_records_arrive(tmp_path):
    store = EventProjectionStore(root=tmp_path / "home")
    try:
        for index in range(5):
            store.record_message_event_projected(_message_event(index))

        first_page = store.list_records(limit=2)
        first_ids = {r["record_id"] for r in first_page["records"]}
        assert first_page["next_cursor"]

        store.record_message_event_projected(_message_event(99))
        second_page = store.list_records(limit=5, cursor=first_page["next_cursor"])
        second_ids = {r["record_id"] for r in second_page["records"]}

        assert first_ids.isdisjoint(second_ids)
        assert all(record_id != "telegram:msg-99" for record_id in second_ids)
    finally:
        store.close()


def test_default_limit_returns_latest_100_of_150_records(tmp_path):
    store = EventProjectionStore(root=tmp_path / "home")
    try:
        for index in range(150):
            store.record_message_event_projected(_message_event(index))

        result = store.list_records()

        assert len(result["records"]) == 100
        assert result["next_cursor"] is not None
        assert result["records"][0]["message_event_id"] == "msg-149"
    finally:
        store.close()


def test_unserializable_raw_payload_is_recorded_without_blocking(tmp_path):
    store = EventProjectionStore(root=tmp_path / "home")
    try:
        event = _message_event(1)
        record_id = store.record_message_event_projected(event, raw_payload={"bad": object()})
        detail = store.get_record(record_id)

        assert detail is not None
        assert detail["record"]["raw_payload_available"] is False
        assert "not JSON serializable" in detail["record"]["raw_payload_error"]
    finally:
        store.close()
