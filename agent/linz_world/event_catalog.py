"""Formal Linz World subject/event catalog used for governance."""

from __future__ import annotations

FORMAL_EVENTS: dict[str, set[str]] = {
    "wsp.chat.message.sent": {"message.sent"},
    "wsp.mrk.requirement.published": {"requirement.published"},
    "wsp.task.created": {"task.created"},
    "wsp.task.updated": {"task.updated"},
    "wsp.task.completed": {"task.completed"},
    "wsp.mrk.order.created": {"order.created"},
    "wsp.mrk.order.updated": {"order.updated"},
    "wsp.mrk.delivery.submitted": {"delivery.submitted"},
    "wsp.mrk.settlement.requested": {"settlement.requested"},
    "wsp.mrk.settlement.completed": {"settlement.completed"},
    "wsp.governance.notice": {"governance.notice"},
}

LEGACY_EVENT_PREFIXES = ("linz.", "skill.", "legacy.")
FORBIDDEN_DIRECT_SUBJECTS = {
    "wsp.mrk.settlement.transfer",
    "wsp.mrk.settlement.completed",
    "rent.transfer",
}
FORBIDDEN_DIRECT_EVENT_TYPES = {"settlement.transfer", "transfer", "rent.transfer"}


def is_formal_event(subject: str, event_type: str) -> bool:
    if not subject or not event_type:
        return False
    if subject.startswith(LEGACY_EVENT_PREFIXES) or event_type.startswith(LEGACY_EVENT_PREFIXES):
        return False
    return event_type in FORMAL_EVENTS.get(subject, set())


def is_forbidden_direct_settlement_transfer(subject: str, event_type: str) -> bool:
    return subject in FORBIDDEN_DIRECT_SUBJECTS or event_type in FORBIDDEN_DIRECT_EVENT_TYPES


def event_category(subject: str, event_type: str) -> str:
    if subject == "wsp.chat.message.sent" and event_type == "message.sent":
        return "world_message"
    if subject.startswith("wsp.task."):
        return "task_signal"
    if subject.startswith("wsp.mrk.order.") or subject.startswith("wsp.mrk.delivery."):
        return "collaboration_signal"
    if subject.startswith("wsp.mrk.settlement.") or subject.startswith("rent."):
        return "governance_signal"
    if subject.startswith("wsp.mrk.requirement."):
        return "opportunity_signal"
    return "world_signal"
