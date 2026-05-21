from __future__ import annotations

import argparse
import json

import pytest

from tests._linz_world_script_loader import load_linz_world_script


formal = load_linz_world_script("formal_experiment_lib")


def test_p1_repeat_generates_three_formal_catalog_events():
    events, blocked = formal.expand_scenarios(phase="P1", run_id="formal-p1-001", repeat=3, target_os_id="agent-1")

    assert blocked == []
    assert len(events) == 18
    assert {event["sequence"] for event in events} == {1, 2, 3}
    assert "mrk.requirement.published.broadcast" in {event["subject"] for event in events}
    assert "wsp.agent-1" in {event["subject"] for event in events}
    assert "poca.reward" in {event["subject"] for event in events}
    assert "mrk.requirement.published.broadcast" in {event["event_type"] for event in events}
    assert "wsp.chat.message.sent" in {event["event_type"] for event in events}
    assert "wsp.sys.rent.failed" in {event["event_type"] for event in events}
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
    assert blocked
    assert {item["code"] for item in blocked} == {"target_os_id_missing"}
    assert any(item["phase"] == "P5" for item in blocked)
    assert all(not event["subject"].startswith("linz.") for event in events)


def test_dry_run_prints_events_and_does_not_prepare_or_publish(tmp_path, capsys):
    args = argparse.Namespace(
        profile="default",
        hermes_home=str(tmp_path / "hermes"),
        phase="P1",
        run_id="dry-run",
        repeat=3,
        interval_seconds=0,
        target_os_id="agent-1",
        seed_id="seed-1",
        persona="persona-a",
        dry_run=True,
        no_live_check=True,
    )

    code = formal.run_experiment(args)

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert len(output["events"]) == 18
    assert output["events"][0]["payload_summary"]


def test_catalog_rejects_legacy_event():
    with pytest.raises(ValueError):
        formal.validate_formal_event("linz.fake", "linz.fake.created")


def test_runtime_raw_export_groups_pipeline_without_optional_field_anomaly():
    event_id = "formal:formal-raw:P0-smoke:abc123"
    raw_rows = [
        {
            "trace_id": "wake-1",
            "session_id": "session-1",
            "timestamp": "2026-05-18T00:00:00Z",
            "route": "goal_event -> tension_operation -> tension_set -> action_potential",
            "step": "tension_operation",
            "data": {
                "event_ref": {"trace_id": event_id},
                "tension_interpretation": {"operations": [{"tension_id": "constraint:risk", "intensity_delta": 0.2}]},
            },
        },
        {
            "trace_id": "wake-1",
            "session_id": "session-1",
            "timestamp": "2026-05-18T00:00:01Z",
            "route": "goal_event -> tension_operation -> tension_set -> action_potential",
            "step": "tension_set",
            "data": {"tension_set": {"dynamic_tensions": [{"tension_id": "constraint:risk", "activation": 0.7}]}},
        },
        {
            "trace_id": "wake-1",
            "session_id": "session-1",
            "timestamp": "2026-05-18T00:00:02Z",
            "route": "goal_event -> tension_operation -> tension_set -> action_potential",
            "step": "action_potential",
            "data": {"action_potential": {"overall_score": 0.4, "risk_cost": 0.8}},
        },
    ]
    anomalies = []

    rows = formal._build_transitions_from_runtime_raw("formal-raw", raw_rows, anomalies)

    assert len(rows) == 1
    assert rows[0]["event_id"] == event_id
    assert rows[0]["trace_id"] == "wake-1"
    assert rows[0]["pipeline_scope"] == "formal_event"
    assert rows[0]["module_presence"]["tension_field"] is True
    assert rows[0]["module_presence"]["tension_set"] is True
    assert rows[0]["module_presence"]["action_potential"] is True
    assert rows[0]["module_presence"]["life_state"] is False
    assert rows[0]["missing_core_modules"] == []
    assert anomalies == []


def test_runtime_session_pipeline_missing_core_modules_is_not_anomaly():
    raw_rows = [
        {
            "session_id": "session-1",
            "timestamp": "2026-05-18T00:00:00Z",
            "route": "goal_event -> tension_operation -> open_intent",
            "step": "tension_operation",
            "data": {"tension_interpretation": {"operations": [{"tension_id": "constraint:risk"}]}},
        },
        {
            "session_id": "session-1",
            "timestamp": "2026-05-18T00:00:01Z",
            "route": "goal_event -> tension_operation -> open_intent",
            "step": "open_intent",
            "data": {"intent": {"intent_id": "intent-1"}},
        },
    ]
    anomalies = []

    rows = formal._build_transitions_from_runtime_raw("formal-raw", raw_rows, anomalies)

    assert len(rows) == 1
    assert rows[0]["pipeline_scope"] == "runtime_session"
    assert rows[0]["missing_core_modules"] == ["tension_set", "action_potential"]
    assert anomalies == []


def test_runtime_pipeline_does_not_attribute_historical_evidence_as_causal_event():
    event_id = "formal:formal-raw:P0-smoke:abc123"
    raw_rows = [
        {
            "session_id": "session-1",
            "timestamp": "2026-05-18T00:00:00Z",
            "route": "goal_event -> tension_operation",
            "step": "tension_operation",
            "data": {
                "event_ref": {"event_id": "osr-response-1"},
                "tension_interpretation": {
                    "event_id": "osr-response-1",
                    "operations": [{"tension_id": "constraint:risk", "evidence": [event_id]}],
                },
            },
        }
    ]
    anomalies = []

    rows = formal._build_transitions_from_runtime_raw("formal-raw", raw_rows, anomalies)

    assert len(rows) == 1
    assert rows[0]["event_id"] == "session-1"
    assert rows[0]["pipeline_scope"] == "runtime_session"
    assert rows[0]["source_event_ids"] == []
    assert anomalies == []


def test_export_event_row_includes_dashboard_style_transition_markdown():
    item = {
        "record": {
            "event_id": "evt-1",
            "subject": "sys.broadcast",
            "event_type": "sys.broadcast.notice_published",
            "raw_payload": {"event_id": "evt-1", "payload": {"phase": "P0", "scenario_id": "smoke"}},
            "consume_status": "handled",
            "projection_status": "projected",
        },
        "projection": {"message_event_id": "msg-1"},
        "transitions": [
            {"transition_id": 1, "to_status": "received", "reason": "message_event_recorded", "metadata": {"record_id": "evt-1"}},
            {"transition_id": 2, "to_status": "handled", "reason": "gateway_processing", "metadata": {"ok": True}},
        ],
    }

    row = formal._export_event_row("formal-md", item, [])

    assert "# Raw inbound payload" in row["gateway_transitions_markdown"]
    assert "## message_event_recorded" in row["gateway_transitions_markdown"]
    assert "## gateway_processing" in row["gateway_transitions_markdown"]
    assert "```json" in row["gateway_transitions_markdown"]
