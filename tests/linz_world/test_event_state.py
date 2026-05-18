import json
from concurrent.futures import ThreadPoolExecutor

from agent.linz_world.event_state import LinzStateRepository


def _event(event_id="evt_1", seq=1):
    return {
        "event_id": event_id,
        "subject": "wsp.chat.message.sent",
        "event_type": "message.sent",
        "payload": {"text": "hello", "token": "secret"},
        "source": {"room_id": "room_1", "actor_id": "actor_1", "os_id": "os_1", "soul_id": "soul_1"},
        "sequence": {"stream": "world-events", "consumer": "hermes-profile", "nats_sequence": seq},
    }


def test_event_persist_deduplicates_event_id_and_sequence(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")

    first, created_first = repo.persist_world_event(_event("evt_1", 1))
    second, created_second = repo.persist_world_event(_event("evt_1", 2))
    third, created_third = repo.persist_world_event(_event("evt_2", 1))

    assert created_first is True
    assert created_second is False
    assert created_third is False
    assert first.event_id == second.event_id == third.event_id
    assert first.os_id == "os_1"
    assert first.soul_id == "soul_1"
    assert first.nats_sequence == "1"
    assert first.sequence_key == "world-events:hermes-profile:1"
    assert len(repo.recent_events()) == 1


def test_retry_stops_after_third_failure(linz_home):
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    repo.persist_world_event(_event())

    processing = repo.mark_processing("evt_1")
    repo.mark_processing_failure("evt_1", "try 1")
    repo.mark_processing_failure("evt_1", "try 2")
    failed = repo.mark_processing_failure("evt_1", "try 3")

    assert processing.dispatch_status.value == "processing"
    assert failed.dispatch_status.value == "failed"
    assert failed.attempt_count == 3
    assert failed.requires_manual_handling is True
    assert "secret" not in failed.payload_summary


def test_parallel_state_updates_do_not_corrupt_json(linz_home):
    root = linz_home / "linz_world"
    repo = LinzStateRepository(root=root, profile_id="test-profile")

    def append_compute(index):
        LinzStateRepository(root=root, profile_id="test-profile").append_list("compute", {"index": index})

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append_compute, range(40)))

    with (root / "state.json").open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data["compute"]) == 40
    assert not list(root.glob("state.json.*.tmp"))
