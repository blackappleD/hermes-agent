"""Semantic Linz World chat actions."""

from __future__ import annotations

import uuid

from .event_state import LinzStateRepository
from .models import PublishReceipt, ReceiptStatus
from .publisher import publish_event

CHAT_MESSAGE_SENT_EVENT_TYPE = "wsp.chat.message.sent"


def send_chat_message(
    to_os_id: str,
    content: str,
    *,
    to_os_name: str = "",
    conversation_id: str = "",
    repository: LinzStateRepository | None = None,
    service=None,
) -> PublishReceipt:
    """Publish a Linz World chat message to the recipient inbox subject."""
    to_os_id = str(to_os_id or "").strip()
    content = str(content or "")
    repo = repository or LinzStateRepository()
    if not content.strip():
        receipt = PublishReceipt(
            request_id=uuid.uuid4().hex,
            subject=f"wsp.{to_os_id}" if to_os_id else "",
            event_type=CHAT_MESSAGE_SENT_EVENT_TYPE,
            payload_summary="",
            status=ReceiptStatus.REJECTED,
            governance_code="content_missing",
            message="content is required to send a Linz World chat message.",
        )
        repo.append_list("receipts", receipt)
        return receipt
    identity = repo.get_identity()
    from_os_id = str(getattr(identity, "os_id", "") or getattr(identity, "agent_id", "") or "")
    from_os_name = str(getattr(identity, "os_name", "") or "")
    payload = {
        "message_id": f"msg_{uuid.uuid4().hex}",
        "from": from_os_id,
        "from_os_name": from_os_name,
        "to": to_os_id,
        "to_os_name": str(to_os_name or ""),
        "content": content,
    }
    if conversation_id:
        payload["conversation_id"] = str(conversation_id)
    return publish_event(
        f"wsp.{to_os_id}",
        CHAT_MESSAGE_SENT_EVENT_TYPE,
        payload,
        repository=repo,
        service=service,
    )
