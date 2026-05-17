import json

from agent.os_runtime.adapters.tools import (
    build_final_response_receipt,
    build_tool_receipt,
    record_post_tool_call,
)
from agent.os_runtime.config import OSRuntimeConfig


def test_tool_receipt_records_trace_ids_summaries_and_duration():
    receipt = build_tool_receipt(
        tool_name="read_file",
        args={"path": "README.md"},
        result={"content": "hello"},
        task_id="task-1",
        session_id="session-1",
        tool_call_id="call-1",
        duration_ms=27,
        runtime_context={
            "event_id": "event-1",
            "intent_id": "intent-1",
            "arbitration_id": "arb-1",
            "permission_ticket_id": "ticket-1",
        },
    )

    assert receipt.receipt_type == "tool"
    assert receipt.status == "succeeded"
    assert receipt.task_id == "task-1"
    assert receipt.session_id == "session-1"
    assert receipt.tool_call_id == "call-1"
    assert receipt.event_id == "event-1"
    assert receipt.intent_id == "intent-1"
    assert receipt.arbitration_id == "arb-1"
    assert receipt.ticket_id == "ticket-1"
    assert receipt.duration_ms == 27
    assert "README.md" in receipt.input_summary
    assert "hello" in receipt.output_summary
    assert receipt.metadata["diagnostics"] == []


def test_tool_receipt_redacts_dict_json_string_and_authorization_header():
    receipt = build_tool_receipt(
        tool_name="http_post",
        args={
            "api_key": "alpha",
            "nested": {"password": "bravo"},
            "body": '{"token": "charlie", "value": "ok"}',
        },
        result="Authorization: Bearer sample\npassword=delta\nnormal output",
    )
    payload = json.dumps(receipt.to_dict(), ensure_ascii=False)

    assert "alpha" not in payload
    assert "bravo" not in payload
    assert "charlie" not in payload
    assert "sample" not in payload
    assert "delta" not in payload
    assert "[REDACTED]" in payload


def test_tool_failure_json_still_generates_receipt():
    receipt = build_tool_receipt(
        tool_name="run_command",
        args={"cmd": "false"},
        result=json.dumps({"exit_code": 2, "stderr": "boom", "status": "failed"}),
        runtime_context={
            "event_id": "event-1",
            "intent_id": "intent-1",
            "arbitration_id": "arb-1",
            "permission_ticket_id": "ticket-1",
        },
    )

    assert receipt.status == "failed"
    assert "boom" in receipt.error


def test_missing_ticket_is_diagnostic_not_authorized_fact():
    receipt = build_tool_receipt(
        tool_name="write_file",
        args={"path": "x"},
        result={"ok": True},
        runtime_context={
            "event_id": "event-1",
            "intent_id": "intent-1",
            "arbitration_id": "arb-1",
        },
    )

    assert receipt.ticket_id == ""
    assert "missing_permission_ticket_id" in receipt.metadata["diagnostics"]


def test_record_post_tool_call_uses_sink_and_does_not_change_result():
    seen = []
    result = {"ok": True, "value": "unchanged"}

    record = record_post_tool_call(
        tool_name="read_file",
        args={"path": "README.md"},
        result=result,
        sink=seen.append,
        config=OSRuntimeConfig(enabled=True),
    )

    assert record.status == "written"
    assert seen[0].receipt_type == "tool"
    assert result == {"ok": True, "value": "unchanged"}


def test_record_post_tool_call_skips_when_runtime_disabled():
    seen = []

    record = record_post_tool_call(
        tool_name="read_file",
        args={},
        result="ok",
        sink=seen.append,
        config=OSRuntimeConfig(enabled=False),
    )

    assert record.status == "skipped"
    assert seen == []


def test_final_response_receipt_summarizes_model_cost_and_exit_reason():
    receipt = build_final_response_receipt(
        assistant_response="final answer token=alpha",
        session_id="session-1",
        event_id="event-1",
        intent_id="intent-1",
        arbitration_id="arb-1",
        ticket_id="ticket-1",
        model="gpt-test",
        platform="openai",
        turn_exit_reason="text_response(finish_reason=stop)",
        token_usage={"input": 10, "output": 5},
        cost={"usd": 0.01},
    )
    payload = json.dumps(receipt.to_dict(), ensure_ascii=False)

    assert receipt.receipt_type == "final_response"
    assert receipt.status == "succeeded"
    assert receipt.metadata["model"] == "gpt-test"
    assert receipt.metadata["turn_exit_reason"] == "text_response(finish_reason=stop)"
    assert "alpha" not in payload
