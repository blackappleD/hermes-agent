import json

from agent.linz_world.models import PublishReceipt, ReceiptStatus
from agent.os_runtime.adapters.linz_world import build_world_publish_receipt
from agent.os_runtime.adapters.tools import build_final_response_receipt, build_tool_receipt
from agent.os_runtime.domain import (
    ArbitrationDecision,
    ArbitrationResult,
    OpenActionFamily,
    OpenIntent,
    RiskLevel,
)
from agent.os_runtime.evidence import build_evidence_package, command_evidence


def _intent():
    return OpenIntent(
        intent_id="intent-1",
        action_family=OpenActionFamily.USE_TOOL,
        action_type="inspect",
        risk_level=RiskLevel.LOW,
    )


def _arbitration():
    return ArbitrationResult(
        intent_id="intent-1",
        decision=ArbitrationDecision.AUTO_EXECUTE,
        metadata={"arbitration_id": "arb-1"},
    )


def test_world_publish_receipt_maps_published_receipt():
    publish_receipt = PublishReceipt(
        request_id="req-1",
        subject="wsp.agent_b",
        event_type="wsp.chat.message.sent",
        payload_summary='{"content": "hi"}',
        status=ReceiptStatus.PUBLISHED,
        world_event_id="world-1",
        receipt={"authorization_map_version": "map-v1"},
    )

    receipt = build_world_publish_receipt(
        publish_receipt,
        event_id="event-1",
        intent_id="intent-1",
        arbitration_id="arb-1",
        ticket_id="ticket-1",
    )

    assert receipt.receipt_type == "world_publish"
    assert receipt.status == "succeeded"
    assert receipt.metadata["subject"] == "wsp.agent_b"
    assert receipt.metadata["event_type"] == "wsp.chat.message.sent"
    assert receipt.metadata["world_event_id"] == "world-1"
    assert receipt.metadata["authorization_map_version"] == "map-v1"
    assert receipt.arbitration_id == "arb-1"


def test_world_publish_receipt_records_rejected_and_failed_statuses():
    rejected = PublishReceipt(
        request_id="req-2",
        subject="forbidden",
        event_type="blocked",
        payload_summary="{}",
        status=ReceiptStatus.REJECTED,
        governance_code="policy_denied",
        message="not allowed",
    )
    failed = PublishReceipt(
        request_id="req-3",
        subject="wsp.agent_b",
        event_type="wsp.chat.message.sent",
        payload_summary="{}",
        status=ReceiptStatus.FAILED,
        message="transport failed",
    )

    rejected_receipt = build_world_publish_receipt(rejected)
    failed_receipt = build_world_publish_receipt(failed)

    assert rejected_receipt.status == "rejected"
    assert "not allowed" in rejected_receipt.error
    assert failed_receipt.status == "failed"
    assert "transport failed" in failed_receipt.error


def test_evidence_package_aggregates_intent_arbitration_receipts_and_commands():
    tool = build_tool_receipt(
        tool_name="read_file",
        args={"path": "README.md"},
        result={"ok": True},
        session_id="session-1",
        runtime_context={
            "event_id": "event-1",
            "intent_id": "intent-1",
            "arbitration_id": "arb-1",
            "permission_ticket_id": "ticket-1",
        },
    )
    world = build_world_publish_receipt(
        PublishReceipt(
            request_id="req-1",
            subject="wsp.agent_b",
            event_type="wsp.chat.message.sent",
            payload_summary="{}",
            status=ReceiptStatus.PUBLISHED,
            world_event_id="world-1",
            receipt={"authorization_map_version": "map-v1"},
        ),
        event_id="event-1",
        intent_id="intent-1",
        arbitration_id="arb-1",
        ticket_id="ticket-1",
    )
    final = build_final_response_receipt(
        assistant_response="done",
        session_id="session-1",
        event_id="event-1",
        intent_id="intent-1",
        arbitration_id="arb-1",
        ticket_id="ticket-1",
        model="gpt-test",
        platform="openai",
        turn_exit_reason="stop",
    )
    command = command_evidence(command="pytest tests/os_runtime", exit_status=0, output="passed")

    package = build_evidence_package(
        trace_id="trace-1",
        session_id="session-1",
        intent=_intent(),
        arbitration=_arbitration(),
        receipts=[tool, world, final],
        commands=[command],
    )

    payload = package.to_dict()
    restored = type(package).from_dict(json.loads(json.dumps(payload, ensure_ascii=False)))

    assert package.complete is True
    assert package.intent_id == "intent-1"
    assert package.arbitration_id == "arb-1"
    assert "event-1" in package.event_ids
    assert set(package.receipt_ids) == {tool.receipt_id, world.receipt_id, final.receipt_id}
    assert restored.receipts[0].receipt_id == tool.receipt_id
    assert restored.commands[0]["status"] == "succeeded"


def test_command_evidence_redacts_failed_output_and_records_risk():
    command = command_evidence(
        command="pytest",
        exit_status=1,
        output="Authorization: Bearer sample\npassword=delta\nfailed",
    )
    package = build_evidence_package(
        trace_id="trace-1",
        intent=_intent(),
        arbitration=_arbitration(),
        receipts=[],
        commands=[command],
    )
    payload = json.dumps(package.to_dict(), ensure_ascii=False)

    assert command["status"] == "failed"
    assert "sample" not in payload
    assert "delta" not in payload
    assert "command_failed:pytest" in package.known_risks
    assert "missing_receipts" in package.diagnostics


def test_evidence_package_marks_missing_arbitration_ticket_and_orphan_receipt():
    receipt = build_tool_receipt(
        tool_name="write_file",
        args={"path": "x"},
        result={"ok": True},
        runtime_context={"intent_id": "intent-1"},
    )

    package = build_evidence_package(
        trace_id="trace-1",
        intent=_intent(),
        receipts=[receipt],
    )

    assert package.complete is False
    assert "missing_arbitration" in package.diagnostics
    assert f"missing_ticket:{receipt.receipt_id}" in package.diagnostics
    assert f"orphan_receipt:{receipt.receipt_id}" in package.diagnostics
