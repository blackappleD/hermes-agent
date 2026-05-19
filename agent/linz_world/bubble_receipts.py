"""Receipts for governed Linz World Bubble Protocol actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ReceiptStatus, utc_now_iso


@dataclass
class BubbleReceipt:
    request_id: str
    action: str
    status: ReceiptStatus
    bubble_id: str = ""
    target_bubble_id: str = ""
    mount_id: str = ""
    lifecycle_state: str = ""
    governance_code: str = ""
    message: str = ""
    result_summary: str = ""
    receipt: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=utc_now_iso)
