from __future__ import annotations

import argparse
import json

import pytest

from scripts import formal_experiment_lib as formal


def test_p1_repeat_generates_three_formal_catalog_events():
    events, blocked = formal.expand_scenarios(phase="P1", run_id="formal-p1-001", repeat=3)

    assert blocked == []
    assert len(events) == 3
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert {event["subject"] for event in events} == {"wsp.mrk.requirement.published"}
    assert {event["event_type"] for event in events} == {"requirement.published"}
    for event in events:
        formal.validate_formal_event(event["subject"], event["event_type"])
        assert event["payload"]["run_id"] == "formal-p1-001"
        assert event["payload"]["phase"] == "P1"


def test_direct_inbox_requires_target_for_single_p5():
    with pytest.raises(SystemExit) as exc:
        formal.expand_scenarios(phase="P5", run_id="formal-p5", repeat=1)

    payload = json.loads(str(exc.value))
    assert payload["code"] == "target_os_id_missing"
    assert payload["status"] == "blocked"


def test_all_marks_missing_p5_target_as_blocked_without_mock_event():
    events, blocked = formal.expand_scenarios(phase="all", run_id="formal-all", repeat=1)

    assert events
    assert blocked == [
        {
            "phase": "P5",
            "scenario_id": "P5-direct-inbox-interaction",
            "code": "target_os_id_missing",
            "message": "Direct inbox scenario requires --target-os-id.",
            "status": "blocked",
        }
    ]
    assert all(not event["subject"].startswith("linz.") for event in events)


def test_dry_run_prints_events_and_does_not_prepare_or_publish(tmp_path, capsys):
    args = argparse.Namespace(
        profile="default",
        hermes_home=str(tmp_path / "hermes"),
        phase="P1",
        run_id="dry-run",
        repeat=3,
        interval_seconds=0,
        target_os_id="",
        seed_id="seed-1",
        persona="persona-a",
        dry_run=True,
        no_live_check=True,
    )

    code = formal.run_experiment(args)

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert len(output["events"]) == 3
    assert output["events"][0]["payload_summary"]


def test_catalog_rejects_legacy_event():
    with pytest.raises(ValueError):
        formal.validate_formal_event("linz.fake", "linz.fake.created")
