from agent.linz_world.bubble_receipts import BubbleReceipt
from agent.linz_world.models import ReceiptStatus
from agent.os_runtime.adapters.bubble import build_bubble_receipt


def test_bubble_receipt_projects_to_execution_receipt():
    receipt = BubbleReceipt(
        request_id="req_1",
        action="bubble.create_task",
        status=ReceiptStatus.PUBLISHED,
        bubble_id="bub_task_1",
        lifecycle_state="produced",
        result_summary="bubble bub_task_1 is produced",
    )

    projected = build_bubble_receipt(
        receipt,
        event_id="evt_1",
        intent_id="intent_1",
        arbitration_id="arb_1",
        ticket_id="ticket_1",
        session_id="session_1",
    )

    assert projected.receipt_type == "linz_bubble"
    assert projected.status == "succeeded"
    assert projected.metadata["action"] == "bubble.create_task"
    assert projected.metadata["bubble_id"] == "bub_task_1"
