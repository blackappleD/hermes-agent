from __future__ import annotations

import json
from pathlib import Path

from scripts import linz_bubble_mrk_flow_test as flow


def test_redact_removes_secret_values():
    payload = {
        "token": "raw-secret",
        "nested": {"authorization": "Bearer abc123", "text": "password=hidden"},
    }

    redacted = json.dumps(flow.redact(payload), sort_keys=True)

    assert "raw-secret" not in redacted
    assert "abc123" not in redacted
    assert "hidden" not in redacted
    assert "[REDACTED]" in redacted


def test_mounted_agent_bubble_id_uses_linz_world_agent_prefix():
    actor = flow.ActorContext(
        role="receiver",
        profile="receiver",
        profile_dir=Path("/tmp/receiver"),
        os_id="78867306-5f5d-4cd5-b7de-d085c562b2d9",
    )

    assert flow.mounted_agent_bubble_id(actor) == "agent_78867306-5f5d-4cd5-b7de-d085c562b2d9"


def test_dry_run_exports_two_profile_report_without_creating_linz_state(tmp_path, monkeypatch):
    default_home = tmp_path / ".hermes"
    default_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(default_home))

    code = flow.main(
        [
            "run",
            "--dry-run",
            "--publisher-profile",
            "default",
            "--receiver-profile",
            "bubble-mrk-worker",
            "--run-id",
            "unit-dry",
            "--output-root",
            str(tmp_path / "results"),
            "--confirm-mutations",
            "--skip-settlement",
        ]
    )

    assert code == 0
    run_dir = tmp_path / "results" / "unit-dry"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["result"] == "DRY_RUN"
    assert summary["publisher_profile"] == "default"
    assert summary["receiver_profile"] == "bubble-mrk-worker"
    assert summary["publisher_os_id"] != summary["receiver_os_id"]
    assert summary["ids"]["demand_bubble_id"].startswith("dry_demand_")
    assert summary["ids"]["task_bubble_id"].startswith("dry_task_")
    assert (run_dir / "REPORT.md").exists()
    assert not (default_home / "linz_world").exists()


def test_dry_run_steps_record_expected_actors(tmp_path, monkeypatch):
    default_home = tmp_path / ".hermes"
    default_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(default_home))

    code = flow.main(
        [
            "run",
            "--dry-run",
            "--publisher-profile",
            "default",
            "--receiver-profile",
            "receiver",
            "--run-id",
            "actor-dry",
            "--output-root",
            str(tmp_path / "results"),
            "--confirm-mutations",
            "--skip-settlement",
        ]
    )

    assert code == 0
    rows = [
        json.loads(line)
        for line in (tmp_path / "results" / "actor-dry" / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_step = {row["step"]: row for row in rows}
    assert by_step["publish requirement"]["actor_profile"] == "default"
    assert by_step["publish order accepted"]["actor_profile"] == "receiver"
    assert by_step["submit task artifact"]["actor_profile"] == "receiver"
    assert by_step["review TaskBubble acceptance"]["actor_profile"] == "default"
