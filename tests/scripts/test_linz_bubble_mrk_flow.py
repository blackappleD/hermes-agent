from __future__ import annotations

import json
from pathlib import Path

from tests._linz_world_script_loader import load_linz_world_script


flow = load_linz_world_script("linz_bubble_mrk_flow_test")


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


def test_expected_mrk_task_bubble_id_matches_linz_world_backend_rule():
    assert (
        flow.expected_mrk_task_bubble_id(
            "REQ-directed-mrk-20260521-120250",
            "78867306-5f5d-4cd5-b7de-d085c562b2d9",
        )
        == "task_REQ-directed-mrk-20260521-120250_78867306-5f5d-4cd5-b7de-d085c562b2d9"
    )


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


def test_directed_dry_run_exports_formal_mrk_checks(tmp_path, monkeypatch):
    default_home = tmp_path / ".hermes"
    default_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(default_home))

    code = flow.main(
        [
            "directed",
            "--dry-run",
            "--publisher-profile",
            "default",
            "--receiver-profile",
            "receiver",
            "--run-id",
            "directed-dry",
            "--output-root",
            str(tmp_path / "results"),
            "--confirm-mutations",
        ]
    )

    assert code == 0
    run_dir = tmp_path / "results" / "directed-dry"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "directed"
    assert summary["result"] == "DRY_RUN"
    assert summary["ids"]["task_bubble_id"].startswith("task_REQ-directed-dry_")
    steps = (run_dir / "steps.jsonl").read_text(encoding="utf-8")
    assert "publish directed MRK requirement" in steps
    assert "verify directed MRK order path" in steps
    observations = (run_dir / "observations.jsonl").read_text(encoding="utf-8")
    assert "mrk.order.accepted is the formal receiver action" in observations


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


def test_real_publisher_prompt_declares_script_mutation_boundary():
    state = flow.FlowState(requirement_id="REQ-real-unit")
    publisher = flow.ActorContext(
        role="publisher",
        profile="default",
        profile_dir=Path("/tmp/default"),
        os_id="publisher-os",
        os_name="publisher",
    )
    receiver = flow.ActorContext(
        role="receiver",
        profile="receiver",
        profile_dir=Path("/tmp/receiver"),
        os_id="receiver-os",
        os_name="receiver",
    )

    prompt = flow.build_real_publisher_prompt(state, publisher, receiver, "real-unit")

    assert "run_id: `real-unit`" in prompt
    assert "REQ-real-unit" in prompt
    assert "开发 JSONL 事件统计脚本 real-unit" in prompt
    assert "linz_event_summary.py" in prompt
    assert "`--input <path>`" in prompt
    assert "`by_event_type`" in prompt
    assert "publisher_os_id: `publisher-os`" in prompt
    assert "target_os_id: `receiver-os`" in prompt
    assert "测试脚本不会替你调用任何 mutating Bubble 工具" in prompt
    assert "confirm_mutation: true" in prompt
    assert "subject=`mrk.requirement.published`, event_type=`mrk.requirement.published`" in prompt
    assert "不要手动发布 `mrk.requirement.published.broadcast`" in prompt


def test_collect_session_evidence_extracts_real_linz_tool_calls(tmp_path):
    profile = tmp_path / "profile"
    sessions = profile / "sessions"
    sessions.mkdir(parents=True)
    session_path = sessions / "20260521_real.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "REQ-real-unit"}),
                json.dumps(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "linz_bubble_create_demand",
                                    "arguments": "{\"name\":\"REQ-real-unit\"}",
                                },
                            }
                        ],
                    }
                ),
                json.dumps(
                    {
                        "role": "tool",
                        "name": "linz_bubble_create_demand",
                        "content": "{\"success\":true,\"bubble_id\":\"bub_demand_real-unit\"}",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    rows = flow.collect_session_evidence(profile, "real-unit")

    assert any("linz_bubble_create_demand" in row["tool_names"] for row in rows)
    assert any("bub_demand_real-unit" in row["bubble_ids"] for row in rows)


def test_collect_session_evidence_reads_json_session_files(tmp_path):
    profile = tmp_path / "profile"
    sessions = profile / "sessions"
    sessions.mkdir(parents=True)
    session_path = sessions / "session_20260521_real.json"
    session_path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "REQ-real-json"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "linz_bubble_accept_demand",
                                    "arguments": "{\"demand_bubble_id\":\"REQ-real-json\"}",
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "name": "linz_bubble_accept_demand",
                        "content": "{\"success\":true,\"bubble_id\":\"REQ-real-json\"}",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = flow.collect_session_evidence(profile, "real-json")

    assert any("linz_bubble_accept_demand" in row["tool_names"] for row in rows)
    assert any("REQ-real-json" in row["bubble_ids"] for row in rows)


def test_gateway_online_requires_live_listener():
    assert flow.is_linz_gateway_online(
        {
            "gateway_state": "running",
            "gateway_linz_platform_state": "connected",
            "listener_state": "online",
        }
    )


def test_fill_missing_config_preserves_linz_identity_section():
    target = {"linz_world": {"os_name": "receiver"}}
    source = {"linz_world": {"os_name": "default"}, "model": {"provider": "minimax-cn"}, "toolsets": ["hermes-cli"]}

    added = flow.fill_missing_config(target, source)

    assert added == ["model", "toolsets"]
    assert target["linz_world"]["os_name"] == "receiver"
    assert target["model"]["provider"] == "minimax-cn"
    assert not flow.is_linz_gateway_online(
        {
            "gateway_state": "running",
            "gateway_linz_platform_state": "connected",
            "listener_state": "offline",
        }
    )
