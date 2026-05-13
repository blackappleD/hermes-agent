"""Data models for the native Linz World integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RegistrationStatus(str, Enum):
    PENDING = "pending"
    REGISTERED = "registered"
    FAILED = "failed"


class LoginState(str, Enum):
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    EXPIRED = "expired"


class AuthState(str, Enum):
    UNKNOWN = "unknown"
    CURRENT = "current"
    STALE = "stale"
    FAILED = "failed"


class DispatchStatus(str, Enum):
    PERSISTED = "persisted"
    QUEUED = "queued"
    PROCESSING = "processing"
    HANDLED = "handled"
    SKIPPED = "skipped"
    FAILED = "failed"


class GovernanceStatus(str, Enum):
    ALLOWED = "allowed"
    REJECTED = "rejected"
    FAILED = "failed"


class ReceiptStatus(str, Enum):
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass
class WorldIdentity:
    profile_id: str
    agent_id: str = ""
    os_id: str = ""
    os_name: str = ""
    soul_id: str = ""
    soul_hash: str = ""
    account_id: str = ""
    access_token_ref: str = ""
    access_token_expires_at: str = ""
    registered_at: str = ""
    credential_id: str = ""
    compute_api_key_ref: str = ""
    registration_state: RegistrationStatus = RegistrationStatus.PENDING
    authorization_state: AuthState = AuthState.UNKNOWN
    memory_summary_available: bool = False
    last_error: str = ""
    next_action: str = ""
    updated_at: str = field(default_factory=utc_now_iso)

    def is_complete(self) -> bool:
        return (
            self.registration_state == RegistrationStatus.REGISTERED
            and bool(self.agent_id)
            and bool(self.os_id)
            and bool(self.os_name)
            and bool(self.soul_id)
            and bool(self.soul_hash)
            and bool(self.account_id)
        )


@dataclass
class LoginSession:
    state: LoginState = LoginState.LOGGED_OUT
    token_ref: str = ""
    expires_at: str = ""
    credential_id: str = ""
    subject_claims: list[str] = field(default_factory=list)
    last_error: str = ""
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class AuthorizationMap:
    state: AuthState = AuthState.UNKNOWN
    map_version: str = ""
    allowed_subjects: list[str] = field(default_factory=list)
    allowed_event_types: list[str] = field(default_factory=list)
    allowed_capabilities: list[str] = field(default_factory=list)
    last_refresh_at: str = ""
    last_error: str = ""

    def allows_event(self, subject: str, event_type: str) -> bool:
        return subject in self.allowed_subjects and event_type in self.allowed_event_types

    def allows_capability(self, capability: str) -> bool:
        return capability in self.allowed_capabilities


@dataclass
class GovernanceResult:
    status: GovernanceStatus
    code: str
    message: str
    next_action: str = ""

    @property
    def allowed(self) -> bool:
        return self.status == GovernanceStatus.ALLOWED


@dataclass
class WorldEvent:
    event_id: str
    subject: str
    event_type: str
    payload_summary: str
    audit_ref: str
    source: dict[str, Any] = field(default_factory=dict)
    sequence_key: str = ""
    occurred_at: str = field(default_factory=utc_now_iso)


@dataclass
class EventDispatchRecord:
    event_id: str
    subject: str
    event_type: str
    payload_summary: str
    audit_ref: str
    dispatch_status: DispatchStatus = DispatchStatus.PERSISTED
    attempt_count: int = 0
    last_error: str = ""
    last_delivery_at: str = ""
    requires_manual_handling: bool = False
    sequence_key: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=utc_now_iso)


@dataclass
class PublishReceipt:
    request_id: str
    subject: str
    event_type: str
    payload_summary: str
    status: ReceiptStatus
    world_event_id: str = ""
    governance_code: str = ""
    message: str = ""
    receipt: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=utc_now_iso)


@dataclass
class ComputeReceipt:
    request_id: str
    status: ReceiptStatus
    provider: str = ""
    model: str = ""
    provider_summary: str = ""
    result_summary: str = ""
    receipt: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    reservation: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    recorded_at: str = field(default_factory=utc_now_iso)


@dataclass
class SoulMemoryEntry:
    artifact_ref: str
    sink_reason: str
    summary: str
    status: ReceiptStatus
    receipt: str = ""
    message: str = ""
    recorded_at: str = field(default_factory=utc_now_iso)


@dataclass
class RelationshipRecord:
    relationship_id: str
    counterparty_id: str
    state: str
    summary: str = ""
    recorded_at: str = field(default_factory=utc_now_iso)


def to_plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    return value
