import json

from agent.linz_world.models import PublishReceipt, ReceiptStatus
from agent.os_runtime.action_executor import AutonomousActionExecutor, is_world_publish_intent, publish_payload_from_intent
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.approval import OSRuntimeApprovalStore
from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.domain import (
    ArbitrationDecision,
    ArbitrationResult,
    OpenActionFamily,
    OpenIntent,
    RiskLevel,
)


def _config(**autonomous):
    defaults = {
        "enabled": True,
        "allow_tool_execution": False,
        "allow_world_publish": False,
    }
    defaults.update(autonomous)
    return OSRuntimeConfig.from_dict(
        {
            "enabled": True,
            "mode": "autonomous_low_risk",
            "autonomous": defaults,
        }
    )


def test_report_only_executes_internal_report_and_records_evidence(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path)
    executor = AutonomousActionExecutor(config=_config(), repository=repo)
    intent = OpenIntent(
        intent_id="intent-1",
        action_family=OpenActionFamily.COMMUNICATE,
        action_type="draft_message",
        why_now="relationship signal",
        success_condition="produce an auditable draft",
        stop_condition="no external side effects",
        risk_level=RiskLevel.LOW,
    )
    arbitration = ArbitrationResult(
        intent_id="intent-1",
        decision=ArbitrationDecision.REPORT_ONLY,
        rationale="low-risk intent has no tool side effects",
        metadata={"arbitration_id": "arb-1"},
    )

    try:
        result = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-1"],
            session_id="session-1",
        )

        assert result.status == "completed"
        assert result.executed is True
        assert result.ticket is not None
        assert result.receipts[0].receipt_type == "final_response"
        assert result.receipts[0].intent_id == "intent-1"
        assert result.receipts[0].arbitration_id == "arb-1"
        assert result.receipts[0].ticket_id == result.ticket.ticket_id
        assert result.evidence_package is not None
        assert result.evidence_package.complete is True
        assert result.feedback["status"] == "completed"
    finally:
        repo.close()


def test_report_only_chat_reply_records_draft_text_and_reply_metadata(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path)
    executor = AutonomousActionExecutor(config=_config(), repository=repo)
    intent = OpenIntent(
        intent_id="intent-chat",
        action_family=OpenActionFamily.COMMUNICATE,
        action_type="reply_chat_message",
        why_now="relationship signal",
        success_condition="produce an auditable draft",
        stop_condition="no external side effects",
        risk_level=RiskLevel.LOW,
        metadata={
            "reply": {
                "target_os_id": "peer-os",
                "conversation_id": "chat-1",
                "source_event_id": "event-chat",
                "draft_text": "你好，我在。",
                "send_requested": False,
            }
        },
    )
    arbitration = ArbitrationResult(
        intent_id="intent-chat",
        decision=ArbitrationDecision.REPORT_ONLY,
        rationale="chat reply draft only",
        metadata={"arbitration_id": "arb-chat"},
    )

    try:
        result = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-chat"],
            session_id="session-chat",
        )

        assert result.status == "completed"
        assert result.receipts[0].output_summary == "你好，我在。"
        assert result.receipts[0].metadata["reply"]["target_os_id"] == "peer-os"
        assert result.evidence_package.complete is True
    finally:
        repo.close()


def test_suppressed_chat_reply_records_no_reply_feedback(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path)
    executor = AutonomousActionExecutor(config=_config(), repository=repo)
    intent = OpenIntent(
        intent_id="intent-chat-close",
        action_family=OpenActionFamily.COMMUNICATE,
        action_type="close_chat_no_reply",
        why_now="politeness loop is closing",
        success_condition="avoid redundant reply",
        stop_condition="no external side effects",
        risk_level=RiskLevel.LOW,
        metadata={
            "reply": {
                "target_os_id": "peer-os",
                "conversation_id": "chat-1",
                "source_event_id": "event-chat",
                "should_reply": False,
                "suppress_reply": True,
                "suppress_reason": "conversation_closing_context",
                "detected_cues": ["gratitude_ack"],
                "send_requested": True,
            }
        },
    )
    arbitration = ArbitrationResult(
        intent_id="intent-chat-close",
        decision=ArbitrationDecision.REPORT_ONLY,
        rationale="chat reply suppressed because the conversation appears to be closing",
        metadata={"arbitration_id": "arb-chat-close"},
    )

    try:
        result = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-chat"],
            session_id="session-chat",
        )

        assert result.status == "completed"
        assert result.action_summary == "chat_reply_suppressed"
        assert result.feedback["should_reply"] is False
        assert result.feedback["reply_control"]["suppress_reply"] is True
        assert result.receipts[0].output_summary == "No reply sent: conversation closing context detected."
        assert result.receipts[0].metadata["should_reply"] is False
    finally:
        repo.close()


def test_untrusted_linz_candidate_does_not_make_draft_a_world_publish():
    intent = OpenIntent(
        intent_id="intent-chat-draft",
        action_family=OpenActionFamily.COMMUNICATE,
        action_type="draft_message",
        why_now="relationship signal",
        success_condition="draft only",
        stop_condition="no external side effects",
        risk_level=RiskLevel.LOW,
        metadata={
            "catalog_validation_required": True,
            "untrusted_linz_world_candidate": {
                "source": "linz_world",
                "subject": "wsp.agent_b",
                "event_type": "wsp.chat.message.sent",
            },
            "llm_response": {
                "raw": "constraints: no world publish without policy, catalog, authorization, and approval"
            },
        },
    )

    assert is_world_publish_intent(intent) is False
    assert publish_payload_from_intent(intent) == {"subject": "", "event_type": "", "payload": {}}


def test_approved_chat_reply_uses_semantic_chat_sender_and_records_world_receipt(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path)
    calls = []

    def chat_sender(**kwargs):
        calls.append(kwargs)
        return PublishReceipt(
            request_id="req-chat",
            subject=f"wsp.{kwargs['to_os_id']}",
            event_type="wsp.chat.message.sent",
            payload_summary='{"content":"你好，我在。"}',
            status=ReceiptStatus.PUBLISHED,
            world_event_id="world-chat",
            receipt={"authorization_map_version": "map-chat"},
        )

    executor = AutonomousActionExecutor(
        config=_config(allow_chat_reply_auto_send=True),
        repository=repo,
        chat_sender=chat_sender,
    )
    intent = OpenIntent(
        intent_id="intent-chat-send",
        action_family=OpenActionFamily.COMMUNICATE,
        action_type="reply_chat_message",
        metadata={
            "reply": {
                "target_os_id": "peer-os",
                "target_os_name": "Peer",
                "conversation_id": "chat-1",
                "draft_text": "你好，我在。",
                "send_requested": True,
            }
        },
    )
    arbitration = ArbitrationResult(
        intent_id="intent-chat-send",
        decision=ArbitrationDecision.REQUIRE_APPROVAL,
        rationale="Linz World chat reply requires approval before execution",
        required_approvals=["linz_world_chat_reply_approval"],
        metadata={"arbitration_id": "arb-chat-send"},
    )

    try:
        pending = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-chat-send"],
            session_id="session-chat-send",
        )
        approved = executor.approve_and_execute(
            pending.metadata["approval_id"],
            session_id="session-chat-send",
            resolver="test",
        )

        assert calls[0]["to_os_id"] == "peer-os"
        assert calls[0]["content"] == "你好，我在。"
        assert calls[0]["os_runtime_context"]["semantic_action"] == "linz_chat_send"
        assert approved.status == "completed"
        assert approved.receipts[0].receipt_type == "world_publish"
        assert approved.receipts[0].metadata["semantic_action"] == "linz_chat_send"
        assert approved.receipts[0].metadata["world_event_id"] == "world-chat"
    finally:
        repo.close()


def test_auto_execute_uses_existing_tool_dispatcher_and_binds_receipt_context(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path)
    calls = []

    def dispatcher(**kwargs):
        calls.append(kwargs)
        return json.dumps({"ok": True, "value": "ran"})

    executor = AutonomousActionExecutor(
        config=_config(allow_tool_execution=True),
        repository=repo,
        tool_dispatcher=dispatcher,
    )
    intent = OpenIntent(
        intent_id="intent-tool",
        action_family=OpenActionFamily.USE_TOOL,
        action_type="inspect",
        tools_needed=["fake_tool"],
        risk_level=RiskLevel.LOW,
        metadata={"tool_args": {"fake_tool": {"x": 1}}},
    )
    arbitration = ArbitrationResult(
        intent_id="intent-tool",
        decision=ArbitrationDecision.AUTO_EXECUTE,
        rationale="allowed",
        metadata={"arbitration_id": "arb-tool"},
    )

    try:
        result = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-tool"],
            session_id="session-tool",
            task_id="task-tool",
        )

        assert calls[0]["tool_name"] == "fake_tool"
        assert calls[0]["args"] == {"x": 1}
        assert calls[0]["runtime_context"]["intent_id"] == "intent-tool"
        assert calls[0]["runtime_context"]["arbitration_id"] == "arb-tool"
        assert result.status == "completed"
        assert result.receipts[0].receipt_type == "tool"
        assert result.receipts[0].event_id == "event-tool"
        assert result.receipts[0].arbitration_id == "arb-tool"
        assert result.evidence_package is not None
        assert result.evidence_package.complete is True
    finally:
        repo.close()


def test_executable_tool_decision_blocks_when_config_disallows_tool_execution(tmp_path):
    dispatched = []
    executor = AutonomousActionExecutor(
        config=_config(allow_tool_execution=False),
        tool_dispatcher=lambda **kwargs: dispatched.append(kwargs),
    )
    intent = OpenIntent(
        intent_id="intent-tool",
        action_family=OpenActionFamily.USE_TOOL,
        tools_needed=["fake_tool"],
        metadata={"tool_args": {"fake_tool": {"x": 1}}},
    )
    arbitration = ArbitrationResult(
        intent_id="intent-tool",
        decision=ArbitrationDecision.SANDBOX_EXECUTE,
        metadata={"arbitration_id": "arb-tool"},
    )

    result = executor.execute(
        intent=intent,
        arbitration=arbitration,
        event_ids=["event-tool"],
        session_id="session-tool",
    )

    assert dispatched == []
    assert result.status == "blocked"
    assert result.executed is False
    assert "allow_tool_execution=false" in result.evidence_package.known_risks


def test_require_approval_creates_pending_request_and_approved_request_executes_tool(tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path)
    calls = []

    def dispatcher(**kwargs):
        calls.append(kwargs)
        return json.dumps({"ok": True})

    executor = AutonomousActionExecutor(
        config=_config(allow_tool_execution=True),
        repository=repo,
        tool_dispatcher=dispatcher,
    )
    intent = OpenIntent(
        intent_id="intent-approval",
        action_family=OpenActionFamily.USE_TOOL,
        action_type="inspect",
        tools_needed=["fake_tool"],
        metadata={"tool_args": {"fake_tool": {"x": 2}}},
    )
    arbitration = ArbitrationResult(
        intent_id="intent-approval",
        decision=ArbitrationDecision.REQUIRE_APPROVAL,
        rationale="high risk requires approval",
        required_approvals=["human_approval"],
        metadata={"arbitration_id": "arb-approval"},
    )

    try:
        pending = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-approval"],
            session_id="session-approval",
            task_id="task-approval",
        )
        approval_id = pending.metadata["approval_id"]
        store = OSRuntimeApprovalStore(repo)

        assert pending.status == "approval_required"
        assert calls == []
        assert store.get(approval_id, session_id="session-approval").status == "pending"

        approved = executor.approve_and_execute(
            approval_id,
            session_id="session-approval",
            resolver="test",
        )

        assert store.get(approval_id, session_id="session-approval").status == "approved"
        assert calls[0]["tool_name"] == "fake_tool"
        assert approved.status == "completed"
        assert approved.receipts[0].arbitration_id == "arb-approval"
    finally:
        repo.close()


def test_world_publish_uses_default_governed_publisher_when_enabled(tmp_path, monkeypatch):
    repo = OSRuntimeEventRepository(root=tmp_path)
    seen = []

    def fake_publish_event(**kwargs):
        seen.append(kwargs)
        return PublishReceipt(
            request_id="req-1",
            subject=kwargs["subject"],
            event_type=kwargs["event_type"],
            payload_summary="{}",
            status=ReceiptStatus.PUBLISHED,
            world_event_id="world-1",
            receipt={"authorization_map_version": "map-v1"},
        )

    monkeypatch.setattr("agent.linz_world.publisher.publish_event", fake_publish_event)
    executor = AutonomousActionExecutor(
        config=_config(allow_world_publish=True),
        repository=repo,
    )
    intent = OpenIntent(
        intent_id="intent-world",
        action_family=OpenActionFamily.USE_TOOL,
        action_type="linz_world.publish",
        risk_level=RiskLevel.LOW,
        metadata={
            "linz_world_publish": {
                "subject": "wsp.agent_b",
                "event_type": "wsp.chat.message.sent",
                "payload": {"content": "hi"},
            }
        },
    )
    arbitration = ArbitrationResult(
        intent_id="intent-world",
        decision=ArbitrationDecision.AUTO_EXECUTE,
        metadata={"arbitration_id": "arb-world"},
    )

    try:
        result = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-world"],
            session_id="session-world",
        )

        assert seen[0]["subject"] == "wsp.agent_b"
        assert seen[0]["os_runtime_context"]["intent_id"] == "intent-world"
        assert result.status == "completed"
        assert result.receipts[0].receipt_type == "world_publish"
        assert result.receipts[0].metadata["world_event_id"] == "world-1"
    finally:
        repo.close()


def test_autonomous_command_lists_and_approves_pending_request(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    repo = OSRuntimeEventRepository(root=home)
    executor = AutonomousActionExecutor(config=_config(), repository=repo)
    intent = OpenIntent(
        intent_id="intent-command-approval",
        action_family=OpenActionFamily.COMMUNICATE,
        action_type="draft_message",
    )
    arbitration = ArbitrationResult(
        intent_id="intent-command-approval",
        decision=ArbitrationDecision.REQUIRE_APPROVAL,
        metadata={"arbitration_id": "arb-command-approval"},
    )

    try:
        pending = executor.execute(
            intent=intent,
            arbitration=arbitration,
            event_ids=["event-command-approval"],
            session_id="session-command",
        )
        approval_id = pending.metadata["approval_id"]
    finally:
        repo.close()

    from hermes_cli.os_runtime_autonomous import handle_autonomous_command

    approvals = handle_autonomous_command(
        "approvals",
        session_id="session-command",
        config=_config(),
    )
    approved = handle_autonomous_command(
        f"approve {approval_id}",
        session_id="session-command",
        config=_config(),
    )

    assert approval_id in approvals.output
    assert "Autonomous approval completed" in approved.output
    assert approved.decision["status"] == "completed"
