"""Execution bridge for autonomous os_runtime arbitration results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agent.linz_world.models import utc_now_iso
from agent.os_runtime.adapters.events import stable_hash
from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.adapters.tools import (
    build_final_response_receipt,
    build_tool_receipt,
    record_final_response,
    record_post_tool_call,
)
from agent.os_runtime.approval import ApprovalRequest, OSRuntimeApprovalStore
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import (
    ArbitrationDecision,
    ArbitrationResult,
    EvidencePackage,
    ExecutionReceipt,
    OpenIntent,
    PermissionTicket,
    SelfPrompt,
)
from agent.os_runtime.evidence import build_evidence_package, record_evidence_package
from agent.os_runtime.engine.arbiter import EXECUTABLE_DECISIONS


ToolDispatcher = Callable[..., Any]
WorldPublisher = Callable[..., Any]
ChatSender = Callable[..., Any]


@dataclass
class AutonomousExecutionResult:
    status: str
    action_summary: str
    executed: bool = False
    ticket: PermissionTicket | None = None
    receipts: list[ExecutionReceipt] = field(default_factory=list)
    evidence_package: EvidencePackage | None = None
    feedback: dict[str, Any] = field(default_factory=dict)
    output_summary: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action_summary": self.action_summary,
            "executed": self.executed,
            "ticket": self.ticket.to_dict() if self.ticket else {},
            "receipts": [item.to_dict() for item in self.receipts],
            "evidence_package": self.evidence_package.to_dict() if self.evidence_package else {},
            "feedback": dict(self.feedback),
            "output_summary": self.output_summary,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


class AutonomousActionExecutor:
    """Execute the side-effect permitted by an arbitration result.

    The executor is deliberately thin. It does not create a second tool
    gateway: tool calls go through ``model_tools.handle_function_call`` unless
    a test dispatcher is injected. World publishing is opt-in and goes through
    the governed Linz World publisher when enabled.
    """

    def __init__(
        self,
        *,
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        repository: OSRuntimeEventRepository | None = None,
        tool_dispatcher: ToolDispatcher | None = None,
        world_publisher: WorldPublisher | None = None,
        chat_sender: ChatSender | None = None,
        approval_store: OSRuntimeApprovalStore | None = None,
    ) -> None:
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.repository = repository
        self.tool_dispatcher = tool_dispatcher
        self.world_publisher = world_publisher or _default_world_publisher
        self.chat_sender = chat_sender or _default_chat_sender
        self.approval_store = approval_store or (OSRuntimeApprovalStore(repository) if repository is not None else None)

    def execute(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        self_prompt: SelfPrompt | None = None,
        event_ids: list[str] | None = None,
        session_id: str = "",
        task_id: str = "",
        profile_id: str = "",
    ) -> AutonomousExecutionResult:
        event_ids = [item for item in event_ids or [] if item]
        event_id = event_ids[0] if event_ids else ""
        arbitration_id = _arbitration_id(arbitration)
        ticket = self._issue_ticket(
            intent=intent,
            arbitration=arbitration,
            arbitration_id=arbitration_id,
            profile_id=profile_id,
        )
        decision = arbitration.decision

        if decision == ArbitrationDecision.REJECT:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=None,
                event_ids=event_ids,
                session_id=session_id,
                status="rejected",
                action_summary="reject",
                executed=False,
                receipts=[],
                known_risks=["arbitration_rejected"],
                output_summary=arbitration.rationale,
            )

        if decision == ArbitrationDecision.REQUIRE_APPROVAL:
            approval_request = self._request_approval(
                intent=intent,
                arbitration=arbitration,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                task_id=task_id,
                profile_id=profile_id,
                self_prompt=self_prompt,
            )
            receipt = self._record_report_receipt(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_id=event_id,
                session_id=session_id,
                output_text=_approval_text(intent, arbitration),
                status_metadata={
                    "execution_status": "approval_required",
                    "approval_id": approval_request.approval_id if approval_request else "",
                    **_reply_status_metadata(intent),
                },
            )
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="approval_required",
                action_summary="require_approval",
                executed=False,
                receipts=[receipt],
                known_risks=["approval_required_before_external_execution"],
                output_summary=receipt.output_summary,
                approval_request=approval_request,
            )

        if decision == ArbitrationDecision.REPORT_ONLY:
            receipt = self._record_report_receipt(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_id=event_id,
                session_id=session_id,
                output_text=_report_text(intent, arbitration, self_prompt),
                status_metadata={"execution_status": "reported", **_reply_status_metadata(intent)},
            )
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="completed",
                action_summary="report_only",
                executed=True,
                receipts=[receipt],
                output_summary=receipt.output_summary,
            )

        if _is_chat_reply_send_intent(intent):
            return self._execute_chat_reply(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
            )

        if _is_world_publish_intent(intent):
            return self._execute_world_publish(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
            )

        if decision in EXECUTABLE_DECISIONS:
            return self._execute_tools(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                task_id=task_id,
            )

        return self._package_result(
            intent=intent,
            arbitration=arbitration,
            arbitration_id=arbitration_id,
            ticket=ticket,
            event_ids=event_ids,
            session_id=session_id,
            status="skipped",
            action_summary=f"unsupported_decision:{decision.value}",
            executed=False,
            receipts=[],
            known_risks=[f"unsupported_arbitration_decision:{decision.value}"],
            output_summary=arbitration.rationale,
        )

    def approve_and_execute(
        self,
        approval_id: str,
        *,
        session_id: str = "",
        resolver: str = "os_runtime",
        reason: str = "",
    ) -> AutonomousExecutionResult:
        if self.approval_store is None:
            return AutonomousExecutionResult(
                status="blocked",
                action_summary="approval_store_unavailable",
                executed=False,
                error="approval store is not configured",
            )
        request = self.approval_store.get(approval_id, session_id=session_id)
        if request is None:
            return AutonomousExecutionResult(
                status="not_found",
                action_summary="approval_not_found",
                executed=False,
                error=f"approval not found: {approval_id}",
            )
        if request.status == "denied":
            return AutonomousExecutionResult(
                status="denied",
                action_summary="approval_denied",
                executed=False,
                error=f"approval was denied: {approval_id}",
            )
        if request.status != "approved":
            request = self.approval_store.resolve(
                approval_id,
                approved=True,
                session_id=session_id or request.session_id,
                resolver=resolver,
                reason=reason,
            ) or request
        intent = OpenIntent.from_dict(request.payload.get("intent") or {})
        arbitration = ArbitrationResult.from_dict(request.payload.get("arbitration") or {})
        self_prompt_payload = request.payload.get("self_prompt") or {}
        self_prompt = SelfPrompt.from_dict(self_prompt_payload) if self_prompt_payload else None
        approved_arbitration = _approved_arbitration(arbitration, intent, approval_id)
        return self.execute(
            intent=intent,
            arbitration=approved_arbitration,
            self_prompt=self_prompt,
            event_ids=request.event_ids,
            session_id=request.session_id,
            task_id=request.task_id,
            profile_id=request.profile_id,
        )

    def deny_approval(
        self,
        approval_id: str,
        *,
        session_id: str = "",
        resolver: str = "os_runtime",
        reason: str = "",
    ) -> ApprovalRequest | None:
        if self.approval_store is None:
            return None
        return self.approval_store.resolve(
            approval_id,
            approved=False,
            session_id=session_id,
            resolver=resolver,
            reason=reason,
        )

    def _request_approval(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        ticket: PermissionTicket,
        event_ids: list[str],
        session_id: str,
        task_id: str,
        profile_id: str,
        self_prompt: SelfPrompt | None,
    ) -> ApprovalRequest | None:
        if self.approval_store is None:
            return None
        return self.approval_store.request(
            intent=intent,
            arbitration=arbitration,
            ticket=ticket,
            event_ids=event_ids,
            session_id=session_id,
            task_id=task_id,
            profile_id=profile_id,
            self_prompt=self_prompt,
            summary=_approval_text(intent, arbitration),
        )

    def _execute_tools(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        arbitration_id: str,
        ticket: PermissionTicket,
        event_ids: list[str],
        session_id: str,
        task_id: str,
    ) -> AutonomousExecutionResult:
        if not self.config.autonomous.allow_tool_execution:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="blocked",
                action_summary="tool_execution_blocked",
                executed=False,
                receipts=[],
                known_risks=["allow_tool_execution=false"],
                output_summary="Tool execution blocked by os_runtime.autonomous.allow_tool_execution=false.",
            )

        event_id = event_ids[0] if event_ids else ""
        receipts: list[ExecutionReceipt] = []
        errors: list[str] = []
        for index, call in enumerate(_tool_calls(intent)):
            tool_name = call["tool_name"]
            args = call["args"]
            tool_call_id = call.get("tool_call_id") or f"autonomous-{stable_hash([intent.intent_id, index, tool_name])[:16]}"
            runtime_context = {
                "event_id": event_id,
                "intent_id": intent.intent_id,
                "arbitration_id": arbitration_id,
                "permission_ticket_id": ticket.ticket_id,
                "os_runtime_autonomous": True,
            }
            result = self._dispatch_tool(
                tool_name=tool_name,
                args=args,
                task_id=task_id,
                session_id=session_id,
                tool_call_id=tool_call_id,
                runtime_context=runtime_context,
            )
            record = record_post_tool_call(
                tool_name=tool_name,
                args=args,
                result=result,
                task_id=task_id,
                session_id=session_id,
                tool_call_id=tool_call_id,
                runtime_context=runtime_context,
                repository=self.repository,
                config=self.config,
            )
            receipt = record.receipt or build_tool_receipt(
                tool_name=tool_name,
                args=args,
                result=result,
                task_id=task_id,
                session_id=session_id,
                tool_call_id=tool_call_id,
                runtime_context=runtime_context,
            )
            receipts.append(receipt)
            if receipt.status not in {"succeeded", "completed"}:
                errors.append(receipt.error or receipt.output_summary or receipt.status)

        status = "failed" if errors else "completed"
        return self._package_result(
            intent=intent,
            arbitration=arbitration,
            arbitration_id=arbitration_id,
            ticket=ticket,
            event_ids=event_ids,
            session_id=session_id,
            status=status,
            action_summary=f"{arbitration.decision.value}:tool",
            executed=True,
            receipts=receipts,
            known_risks=[] if receipts else ["no_tool_calls_to_execute"],
            output_summary="; ".join(item.output_summary for item in receipts if item.output_summary)[:1024],
            error="; ".join(errors),
        )

    def _execute_chat_reply(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        arbitration_id: str,
        ticket: PermissionTicket,
        event_ids: list[str],
        session_id: str,
    ) -> AutonomousExecutionResult:
        reply = _reply_payload(intent)
        target_os_id = str(reply.get("target_os_id") or "")
        draft_text = str(reply.get("draft_text") or "")
        if not target_os_id or not draft_text:
            missing = []
            if not target_os_id:
                missing.append("reply_target_os_id_missing")
            if not draft_text:
                missing.append("reply_draft_text_missing")
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="blocked",
                action_summary="chat_reply_blocked",
                executed=False,
                receipts=[],
                known_risks=missing,
                output_summary="Linz World chat reply requires target_os_id and draft_text.",
            )
        approval_granted = bool(arbitration.metadata.get("approval_granted")) if isinstance(arbitration.metadata, dict) else False
        if not self.config.autonomous.allow_chat_reply_auto_send and not approval_granted:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="blocked",
                action_summary="chat_reply_auto_send_blocked",
                executed=False,
                receipts=[],
                known_risks=["allow_chat_reply_auto_send=false"],
                output_summary="Linz World chat reply send blocked by os_runtime.autonomous.allow_chat_reply_auto_send=false.",
            )

        try:
            receipt_data = self.chat_sender(
                to_os_id=target_os_id,
                content=draft_text,
                to_os_name=str(reply.get("target_os_name") or ""),
                conversation_id=str(reply.get("conversation_id") or ""),
                os_runtime_context={
                    "event_id": event_ids[0] if event_ids else "",
                    "intent_id": intent.intent_id,
                    "arbitration_id": arbitration_id,
                    "permission_ticket_id": ticket.ticket_id,
                    "session_id": session_id,
                    "semantic_action": "linz_chat_send",
                },
            )
            from agent.os_runtime.adapters.linz_world import record_world_publish

            record = record_world_publish(
                receipt_data,
                event_id=event_ids[0] if event_ids else "",
                intent_id=intent.intent_id,
                arbitration_id=arbitration_id,
                ticket_id=ticket.ticket_id,
                session_id=session_id,
                metadata={"semantic_action": "linz_chat_send", "reply": reply},
                repository=self.repository,
                config=self.config,
            )
            receipts = [record.receipt] if record.receipt else []
            status = "completed" if receipts and receipts[0].status == "succeeded" else "failed"
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status=status,
                action_summary="chat_reply_sent",
                executed=True,
                receipts=[item for item in receipts if item is not None],
                known_risks=[] if receipts else ["chat_reply_receipt_missing"],
                output_summary=receipts[0].output_summary if receipts else "",
                error=receipts[0].error if receipts else "",
            )
        except Exception as exc:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="failed",
                action_summary="chat_reply_failed",
                executed=True,
                receipts=[],
                known_risks=["chat_reply_exception"],
                output_summary="",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _execute_world_publish(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        arbitration_id: str,
        ticket: PermissionTicket,
        event_ids: list[str],
        session_id: str,
    ) -> AutonomousExecutionResult:
        if not self.config.autonomous.allow_world_publish:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="blocked",
                action_summary="world_publish_blocked",
                executed=False,
                receipts=[],
                known_risks=["allow_world_publish=false"],
                output_summary="World publish blocked by os_runtime.autonomous.allow_world_publish=false.",
            )
        if self.world_publisher is None:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="blocked",
                action_summary="world_publish_unavailable",
                executed=False,
                receipts=[],
                known_risks=["world_publisher_not_configured"],
                output_summary="World publish requires an injected publisher dependency.",
            )

        publish_payload = _publish_payload(intent)
        try:
            receipt_data = self.world_publisher(
                **publish_payload,
                os_runtime_context={
                    "event_id": event_ids[0] if event_ids else "",
                    "intent_id": intent.intent_id,
                    "arbitration_id": arbitration_id,
                    "permission_ticket_id": ticket.ticket_id,
                    "session_id": session_id,
                },
            )
            from agent.os_runtime.adapters.linz_world import record_world_publish

            record = record_world_publish(
                receipt_data,
                event_id=event_ids[0] if event_ids else "",
                intent_id=intent.intent_id,
                arbitration_id=arbitration_id,
                ticket_id=ticket.ticket_id,
                session_id=session_id,
                repository=self.repository,
                config=self.config,
            )
            receipts = [record.receipt] if record.receipt else []
            status = "completed" if receipts and receipts[0].status == "succeeded" else "failed"
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status=status,
                action_summary="world_publish",
                executed=True,
                receipts=[item for item in receipts if item is not None],
                known_risks=[] if receipts else ["world_publish_receipt_missing"],
                output_summary=receipts[0].output_summary if receipts else "",
                error=receipts[0].error if receipts else "",
            )
        except Exception as exc:
            return self._package_result(
                intent=intent,
                arbitration=arbitration,
                arbitration_id=arbitration_id,
                ticket=ticket,
                event_ids=event_ids,
                session_id=session_id,
                status="failed",
                action_summary="world_publish_failed",
                executed=True,
                receipts=[],
                known_risks=["world_publish_exception"],
                output_summary="",
                error=f"{type(exc).__name__}: {exc}",
            )

    def _record_report_receipt(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        arbitration_id: str,
        ticket: PermissionTicket,
        event_id: str,
        session_id: str,
        output_text: str,
        status_metadata: dict[str, Any],
    ) -> ExecutionReceipt:
        record = record_final_response(
            assistant_response=output_text,
            session_id=session_id,
            event_id=event_id,
            intent_id=intent.intent_id,
            arbitration_id=arbitration_id,
            ticket_id=ticket.ticket_id,
            model="os_runtime",
            platform="autonomous",
            turn_exit_reason=f"autonomous:{arbitration.decision.value}",
            metadata={
                "action_family": intent.action_family.value,
                "action_type": intent.action_type,
                "decision": arbitration.decision.value,
                **status_metadata,
            },
            repository=self.repository,
            config=self.config,
        )
        if record.receipt:
            return record.receipt
        return build_final_response_receipt(
            assistant_response=output_text,
            session_id=session_id,
            event_id=event_id,
            intent_id=intent.intent_id,
            arbitration_id=arbitration_id,
            ticket_id=ticket.ticket_id,
            model="os_runtime",
            platform="autonomous",
            turn_exit_reason=f"autonomous:{arbitration.decision.value}",
            metadata=status_metadata,
        )

    def _dispatch_tool(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        task_id: str,
        session_id: str,
        tool_call_id: str,
        runtime_context: dict[str, Any],
    ) -> Any:
        if self.tool_dispatcher is not None:
            return self.tool_dispatcher(
                tool_name=tool_name,
                args=args,
                task_id=task_id,
                session_id=session_id,
                tool_call_id=tool_call_id,
                runtime_context=runtime_context,
            )
        from model_tools import handle_function_call

        return handle_function_call(
            tool_name,
            args,
            task_id=task_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            runtime_context=runtime_context,
        )

    def _issue_ticket(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        arbitration_id: str,
        profile_id: str,
    ) -> PermissionTicket:
        return PermissionTicket(
            ticket_id=f"ticket_{stable_hash([intent.intent_id, arbitration_id, arbitration.decision.value])[:24]}",
            intent_id=intent.intent_id,
            arbitration_id=arbitration_id,
            decision=arbitration.decision,
            issued_at=utc_now_iso(),
            allowed_tools=list(intent.tools_needed),
            constraints=[
                f"decision={arbitration.decision.value}",
                f"risk={arbitration.risk_level.value}",
                *(intent.open_space.constraints if intent.open_space else []),
            ],
            issuer="bo-yue-arbiter",
            metadata={
                "profile_id": profile_id,
                "required_approvals": list(arbitration.required_approvals),
            },
        )

    def _package_result(
        self,
        *,
        intent: OpenIntent,
        arbitration: ArbitrationResult,
        arbitration_id: str,
        ticket: PermissionTicket | None,
        event_ids: list[str],
        session_id: str,
        status: str,
        action_summary: str,
        executed: bool,
        receipts: list[ExecutionReceipt],
        known_risks: list[str] | None = None,
        output_summary: str = "",
        error: str = "",
        approval_request: ApprovalRequest | None = None,
    ) -> AutonomousExecutionResult:
        arbitration_data = arbitration.to_dict()
        arbitration_data.setdefault("metadata", {})
        arbitration_data["metadata"]["arbitration_id"] = arbitration_id
        if ticket is not None:
            arbitration_data["metadata"]["permission_ticket_id"] = ticket.ticket_id

        package = build_evidence_package(
            trace_id=event_ids[0] if event_ids else intent.intent_id,
            session_id=session_id,
            event_ids=event_ids,
            intent=intent,
            arbitration=arbitration_data,
            receipts=receipts,
            known_risks=known_risks or [],
            metadata={
                "action_summary": action_summary,
                "execution_status": status,
                "executed": executed,
                "permission_ticket": ticket.to_dict() if ticket else {},
                "approval_request": approval_request.to_dict() if approval_request else {},
            },
        )
        if self.repository is not None:
            record_evidence_package(package, repository=self.repository, config=self.config)
        feedback_status = "failed" if status in {"failed", "rejected", "blocked"} else status
        return AutonomousExecutionResult(
            status=status,
            action_summary=action_summary,
            executed=executed,
            ticket=ticket,
            receipts=receipts,
            evidence_package=package,
            feedback={
                "status": feedback_status,
                "action_summary": action_summary,
                "receipt_count": len(receipts),
                "evidence_id": package.evidence_id,
                "error": error,
            },
            output_summary=output_summary,
            error=error,
            metadata={
                "arbitration_id": arbitration_id,
                "intent_id": intent.intent_id,
                "approval_id": approval_request.approval_id if approval_request else "",
            },
        )


def _arbitration_id(arbitration: ArbitrationResult) -> str:
    metadata = arbitration.metadata if isinstance(arbitration.metadata, dict) else {}
    existing = metadata.get("arbitration_id")
    if existing:
        return str(existing)
    return f"arb_{stable_hash(arbitration.to_dict())[:24]}"


def _approved_arbitration(
    arbitration: ArbitrationResult,
    intent: OpenIntent,
    approval_id: str,
) -> ArbitrationResult:
    data = arbitration.to_dict()
    metadata = dict(data.get("metadata") or {})
    metadata["approval_id"] = approval_id
    metadata["approval_granted"] = True
    metadata["original_decision"] = arbitration.decision.value
    data["metadata"] = metadata
    if _is_chat_reply_send_intent(intent):
        data["decision"] = ArbitrationDecision.AUTO_EXECUTE.value
        data["rationale"] = f"{arbitration.rationale}; approval granted for chat reply".strip("; ")
    elif _is_world_publish_intent(intent):
        data["decision"] = ArbitrationDecision.AUTO_EXECUTE.value
        data["rationale"] = f"{arbitration.rationale}; approval granted for world publish".strip("; ")
    elif intent.tools_needed:
        data["decision"] = ArbitrationDecision.SANDBOX_EXECUTE.value
        data["rationale"] = f"{arbitration.rationale}; approval granted for sandbox execution".strip("; ")
    else:
        data["decision"] = ArbitrationDecision.REPORT_ONLY.value
        data["rationale"] = f"{arbitration.rationale}; approval granted for report-only execution".strip("; ")
    data["required_approvals"] = []
    return ArbitrationResult.from_dict(data)


def _tool_calls(intent: OpenIntent) -> list[dict[str, Any]]:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    explicit = metadata.get("tool_calls")
    calls: list[dict[str, Any]] = []
    if isinstance(explicit, list):
        for index, item in enumerate(explicit):
            if not isinstance(item, dict):
                continue
            name = str(item.get("tool_name") or item.get("tool") or item.get("name") or "")
            if not name:
                continue
            args = item.get("args", item.get("arguments", {}))
            calls.append(
                {
                    "tool_name": name,
                    "args": args if isinstance(args, dict) else {"value": args},
                    "tool_call_id": str(item.get("tool_call_id") or item.get("id") or f"call-{index}"),
                }
            )
    if calls:
        return calls

    arg_map = metadata.get("tool_args") or metadata.get("tool_arguments") or {}
    if not isinstance(arg_map, dict):
        arg_map = {}
    for name in intent.tools_needed:
        args = arg_map.get(name, {})
        calls.append(
            {
                "tool_name": name,
                "args": args if isinstance(args, dict) else {"value": args},
            }
        )
    return calls


def _report_text(intent: OpenIntent, arbitration: ArbitrationResult, self_prompt: SelfPrompt | None) -> str:
    reply = _reply_payload(intent)
    if reply.get("draft_text"):
        return str(reply["draft_text"])
    lines = [
        "Autonomous report-only action completed.",
        f"Intent: {intent.intent_id}",
        f"Action: {intent.action_family.value}/{intent.action_type or 'unspecified'}",
        f"Decision: {arbitration.decision.value}",
    ]
    if intent.why_now:
        lines.append(f"Why now: {intent.why_now}")
    if intent.success_condition:
        lines.append(f"Success condition: {intent.success_condition}")
    if intent.stop_condition:
        lines.append(f"Stop condition: {intent.stop_condition}")
    if arbitration.rationale:
        lines.append(f"Rationale: {arbitration.rationale}")
    if self_prompt and self_prompt.target_direction:
        lines.append(f"Target: {self_prompt.target_direction.description}")
    return "\n".join(lines)


def _approval_text(intent: OpenIntent, arbitration: ArbitrationResult) -> str:
    lines = [
        "Autonomous action requires approval before execution.",
        f"Intent: {intent.intent_id}",
        f"Action: {intent.action_family.value}/{intent.action_type or 'unspecified'}",
        f"Required approvals: {', '.join(arbitration.required_approvals) or 'unspecified'}",
        f"Rationale: {arbitration.rationale or 'not provided'}",
    ]
    reply = _reply_payload(intent)
    if reply:
        lines.append(f"Reply target: {reply.get('target_os_id') or 'missing'}")
        lines.append(f"Draft: {reply.get('draft_text') or 'missing'}")
    return "\n".join(lines)


def _is_world_publish_intent(intent: OpenIntent) -> bool:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    if isinstance(metadata.get("linz_world_publish"), dict) or isinstance(metadata.get("world_publish"), dict):
        return True
    haystack = " ".join(
        [
            intent.action_type,
            *intent.tools_needed,
            str(metadata.get("operation") or ""),
            str(metadata.get("tool_name") or ""),
        ]
    ).lower()
    return ("linz_world.publish" in haystack or "linz_publish" in haystack) and "publish" in haystack


def is_world_publish_intent(intent: OpenIntent) -> bool:
    return _is_world_publish_intent(intent)


def _is_chat_reply_intent(intent: OpenIntent) -> bool:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    return intent.action_type == "reply_chat_message" or isinstance(metadata.get("reply"), dict)


def _is_chat_reply_send_intent(intent: OpenIntent) -> bool:
    if not _is_chat_reply_intent(intent):
        return False
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    reply = metadata.get("reply") if isinstance(metadata.get("reply"), dict) else {}
    return bool(metadata.get("chat_reply_send_requested") or reply.get("send_requested"))


def is_chat_reply_intent(intent: OpenIntent) -> bool:
    return _is_chat_reply_intent(intent)


def is_chat_reply_send_intent(intent: OpenIntent) -> bool:
    return _is_chat_reply_send_intent(intent)


def _publish_payload(intent: OpenIntent) -> dict[str, Any]:
    if _is_chat_reply_send_intent(intent):
        return _chat_reply_publish_payload(intent)
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    payload = metadata.get("linz_world_publish") or metadata.get("world_publish") or {}
    if not isinstance(payload, dict):
        payload = {}
    raw_payload = payload.get("payload")
    if not isinstance(raw_payload, dict):
        raw_payload = {}
    return {
        "subject": str(payload.get("subject") or metadata.get("subject") or ""),
        "event_type": str(payload.get("event_type") or metadata.get("event_type") or ""),
        "payload": raw_payload,
    }


def publish_payload_from_intent(intent: OpenIntent) -> dict[str, Any]:
    return _publish_payload(intent)


def _chat_reply_publish_payload(intent: OpenIntent) -> dict[str, Any]:
    reply = _reply_payload(intent)
    target_os_id = str(reply.get("target_os_id") or "")
    return {
        "subject": f"wsp.{target_os_id}" if target_os_id else "",
        "event_type": "wsp.chat.message.sent",
        "payload": {"content": str(reply.get("draft_text") or "")},
    }


def _reply_status_metadata(intent: OpenIntent) -> dict[str, Any]:
    reply = _reply_payload(intent)
    return {"reply": reply} if reply else {}


def _reply_payload(intent: OpenIntent) -> dict[str, Any]:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    reply = metadata.get("reply") if isinstance(metadata.get("reply"), dict) else {}
    if not reply:
        return {}
    allowed = {
        "target_os_id",
        "target_os_name",
        "conversation_id",
        "source_event_id",
        "source_subject",
        "source_event_type",
        "incoming_summary",
        "draft_text",
        "send_requested",
    }
    return {key: value for key, value in reply.items() if key in allowed}


def _default_world_publisher(**kwargs: Any) -> Any:
    from agent.linz_world.publisher import publish_event

    return publish_event(**kwargs)


def _default_chat_sender(**kwargs: Any) -> Any:
    from agent.linz_world.chat import send_chat_message

    return send_chat_message(
        str(kwargs.get("to_os_id") or ""),
        str(kwargs.get("content") or ""),
        to_os_name=str(kwargs.get("to_os_name") or ""),
        conversation_id=str(kwargs.get("conversation_id") or ""),
    )


__all__ = [
    "AutonomousActionExecutor",
    "AutonomousExecutionResult",
    "is_chat_reply_intent",
    "is_chat_reply_send_intent",
    "is_world_publish_intent",
    "publish_payload_from_intent",
]
