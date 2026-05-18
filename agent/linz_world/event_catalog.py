"""Formal Linz World subject/event catalog used for governance."""

from __future__ import annotations

DIRECT_INBOX_EVENT_TYPES = {
    "wsp.sys.login.response",
    "wsp.sys.subject.changed",
    "wsp.sys.credential.issued",
    "wsp.sys.credential.expiring",
    "wsp.sys.rent.assessed",
    "wsp.sys.rent.deducted",
    "wsp.sys.rent.failed",
    "wsp.chat.message.sent",
    "wsp.chat.message.read",
    "wsp.task.notified",
    "wsp.task.reminded",
    "wsp.task.acknowledged",
    "wsp.task.status.synced",
    "wsp.mrk.requirement.published",
    "wsp.mrk.order.accepted",
    "wsp.mrk.order.handover.delivered",
    "wsp.mrk.order.handover.approved",
    "wsp.mrk.order.handover.rejected",
    "wsp.mrk.settlement.completed",
    "wsp.mrk.settlement.failed",
}
RESERVED_WSP_INBOX_NAMES = {"chat", "sys", "task", "mrk"}

LEGACY_CHAT_EVENTS: dict[str, set[str]] = {
    # Kept as receive-side compatibility for early Hermes native events.
    # New chat publishes should target the recipient inbox subject
    # (wsp.<recipient_os_id>) with event_type=wsp.chat.message.sent.
    "wsp.chat.message.sent": {"message.sent"},
}

FORMAL_EVENTS: dict[str, set[str]] = {
    "sys.heartbeat": {"sys.heartbeat.report"},
    "sys.broadcast": {"sys.broadcast.notice_published"},
    "auth.login.request": {"auth.login.request"},
    "mrk.requirement.published": {"mrk.requirement.published"},
    "mrk.requirement.published.broadcast": {"mrk.requirement.published.broadcast"},
    "mrk.requirement": {
        "mrk.requirement.updated",
        "mrk.requirement.withdrawn",
        "mrk.requirement.closed",
    },
    "mrk.order": {
        "mrk.order.created",
        "mrk.order.accepted",
        "mrk.order.cancelled",
        "mrk.order.completed",
    },
    "mrk.order.handover": {
        "mrk.order.handover.submitted",
        "mrk.order.handover.delivered",
        "mrk.order.handover.approved",
        "mrk.order.handover.rejected",
    },
    "mrk.settlement": {
        "mrk.settlement.requested",
        "mrk.settlement.completed",
        "mrk.settlement.failed",
        "mrk.settlement.reversed",
    },
    "ec.transfer": {
        "ec.transfer.requested",
        "ec.transfer.completed",
        "ec.transfer.failed",
    },
    "event.memory.sink": {"event.memory.sink.requested"},
    "apl.case": {"apl.case.created", "apl.case.accepted", "apl.case.withdrawn"},
    "apl.review": {"apl.review.started", "apl.review.completed", "apl.review.reopened"},
    "apl.decision": {
        "apl.decision.drafted",
        "apl.decision.published",
        "apl.decision.executed",
    },
    "rent.cycle": {"rent.cycle.started"},
    "rent.accrual": {"rent.accrual.calculated"},
    "rent.settlement": {
        "rent.settlement.created",
        "rent.settlement.completed",
        "rent.settlement.failed",
    },
    "rent.distribution": {
        "rent.distribution.allocated",
        "rent.distribution.reversed",
    },
    "poca.assessment": {
        "poca.assessment.submitted",
        "poca.assessment.accepted",
        "poca.assessment.rejected",
    },
    "poca.review": {"poca.review.started", "poca.review.completed", "poca.review.reopened"},
    "poca.reputation": {
        "poca.reputation.increased",
        "poca.reputation.decreased",
        "poca.reputation.corrected",
    },
    "poca.reward": {"poca.reward.issued", "poca.reward.reversed"},
    # Compatibility aliases used by earlier formal experiment scripts.
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
    if is_direct_inbox_event(subject, event_type):
        return True
    if event_type in LEGACY_CHAT_EVENTS.get(subject, set()):
        return True
    return event_type in FORMAL_EVENTS.get(subject, set())


def is_direct_inbox_subject(subject: str) -> bool:
    if not subject.startswith("wsp."):
        return False
    # Direct inbox subjects are exactly "wsp.<os_id>". Namespaced subjects like
    # "wsp.chat.message.sent" are event families, not recipient inboxes.
    inbox_name = subject.removeprefix("wsp.")
    return subject.count(".") == 1 and bool(inbox_name) and inbox_name not in RESERVED_WSP_INBOX_NAMES


def is_direct_inbox_event(subject: str, event_type: str) -> bool:
    return is_direct_inbox_subject(subject) and event_type in DIRECT_INBOX_EVENT_TYPES


def is_forbidden_direct_settlement_transfer(subject: str, event_type: str) -> bool:
    return subject in FORBIDDEN_DIRECT_SUBJECTS or event_type in FORBIDDEN_DIRECT_EVENT_TYPES


def event_category(subject: str, event_type: str) -> str:
    if event_type.startswith("wsp.chat.") or event_type in LEGACY_CHAT_EVENTS.get(subject, set()):
        return "world_message"
    if is_direct_inbox_event(subject, event_type):
        if event_type.startswith("wsp.task."):
            return "task_signal"
        if event_type.startswith("wsp.mrk.requirement."):
            return "opportunity_signal"
        if event_type.startswith("wsp.mrk.order."):
            return "collaboration_signal"
        if event_type.startswith("wsp.mrk.settlement.") or event_type.startswith("wsp.sys.rent."):
            return "governance_signal"
        if event_type.startswith("wsp.sys."):
            return "system_signal"
    if subject.startswith("wsp.task."):
        return "task_signal"
    if subject.startswith("mrk.order") or subject.startswith("wsp.mrk.order.") or subject.startswith("wsp.mrk.delivery."):
        return "collaboration_signal"
    if subject.startswith("mrk.settlement") or subject.startswith("ec.transfer") or subject.startswith("wsp.mrk.settlement.") or subject.startswith("rent."):
        return "governance_signal"
    if subject.startswith("mrk.requirement") or subject.startswith("wsp.mrk.requirement."):
        return "opportunity_signal"
    if subject.startswith("poca."):
        return "reputation_signal"
    if subject.startswith("sys.") or subject.startswith("auth."):
        return "system_signal"
    return "world_signal"
