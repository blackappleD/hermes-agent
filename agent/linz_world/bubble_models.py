"""BPS bubble data transfer objects for Linz World."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _pick(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


@dataclass
class BubbleRecord:
    bubble_id: str = ""
    bubble_type: str = ""
    name: str = ""
    goal: str = ""
    parent_bubble_id: str = ""
    source_bubble_ids: list[str] = field(default_factory=list)
    owner_os_id: str = ""
    created_by_os_id: str = ""
    lifecycle_state: str = ""
    spec: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_api(cls, data: Any) -> "BubbleRecord":
        if not isinstance(data, dict):
            return cls()
        return cls(
            bubble_id=str(_pick(data, "bubble_id", "BubbleID")),
            bubble_type=str(_pick(data, "bubble_type", "BubbleType")),
            name=str(_pick(data, "name", "Name")),
            goal=str(_pick(data, "goal", "Goal")),
            parent_bubble_id=str(_pick(data, "parent_bubble_id", "ParentBubbleID")),
            source_bubble_ids=_string_list(_pick(data, "source_bubble_ids", "SourceBubbleIDs", default=[])),
            owner_os_id=str(_pick(data, "owner_os_id", "OwnerOsID", "OwnerOSID")),
            created_by_os_id=str(_pick(data, "created_by_os_id", "CreatedByOsID", "CreatedByOSID")),
            lifecycle_state=str(_pick(data, "lifecycle_state", "LifecycleState")),
            spec=_dict_value(_pick(data, "spec", "Spec", default={})),
            created_at=str(_pick(data, "created_at", "CreatedAt")),
            updated_at=str(_pick(data, "updated_at", "UpdatedAt")),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "bubble_id": self.bubble_id,
            "bubble_type": self.bubble_type,
            "name": self.name,
            "goal": self.goal,
            "parent_bubble_id": self.parent_bubble_id,
            "owner_os_id": self.owner_os_id,
            "lifecycle_state": self.lifecycle_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class BubbleMountRecord:
    mount_id: str = ""
    task_bubble_id: str = ""
    mounted_bubble_id: str = ""
    slot_id: str = ""
    relation_role: str = ""
    mount_state: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    credit_settlement_ref: str = ""
    requested_by_os_id: str = ""
    reviewed_by_os_id: str = ""
    reject_reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_api(cls, data: Any) -> "BubbleMountRecord":
        if not isinstance(data, dict):
            return cls()
        return cls(
            mount_id=str(_pick(data, "mount_id", "MountID")),
            task_bubble_id=str(_pick(data, "task_bubble_id", "TaskBubbleID")),
            mounted_bubble_id=str(_pick(data, "mounted_bubble_id", "MountedBubbleID")),
            slot_id=str(_pick(data, "slot_id", "SlotID")),
            relation_role=str(_pick(data, "relation_role", "RelationRole")),
            mount_state=str(_pick(data, "mount_state", "MountState")),
            allowed_actions=_string_list(_pick(data, "allowed_actions", "AllowedActions", default=[])),
            credit_settlement_ref=str(_pick(data, "credit_settlement_ref", "CreditSettlementRef")),
            requested_by_os_id=str(_pick(data, "requested_by_os_id", "RequestedByOsID", "RequestedByOSID")),
            reviewed_by_os_id=str(_pick(data, "reviewed_by_os_id", "ReviewedByOsID", "ReviewedByOSID")),
            reject_reason=str(_pick(data, "reject_reason", "RejectReason")),
            payload=_dict_value(_pick(data, "payload", "Payload", default={})),
            created_at=str(_pick(data, "created_at", "CreatedAt")),
            updated_at=str(_pick(data, "updated_at", "UpdatedAt")),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "mount_id": self.mount_id,
            "task_bubble_id": self.task_bubble_id,
            "mounted_bubble_id": self.mounted_bubble_id,
            "slot_id": self.slot_id,
            "relation_role": self.relation_role,
            "mount_state": self.mount_state,
            "allowed_actions": self.allowed_actions,
            "requested_by_os_id": self.requested_by_os_id,
            "reviewed_by_os_id": self.reviewed_by_os_id,
            "reject_reason": self.reject_reason,
        }


@dataclass
class BubbleBehaviorEvent:
    event_id: str = ""
    behavior_event_type: str = ""
    bubble_id: str = ""
    actor_id: str = ""
    before_state: str = ""
    after_state: str = ""
    reason: str = ""
    occurred_at: str = ""

    @classmethod
    def from_api(cls, data: Any) -> "BubbleBehaviorEvent":
        if not isinstance(data, dict):
            return cls()
        return cls(
            event_id=str(_pick(data, "event_id", "EventID")),
            behavior_event_type=str(_pick(data, "behavior_event_type", "BehaviorEventType")),
            bubble_id=str(_pick(data, "bubble_id", "BubbleID")),
            actor_id=str(_pick(data, "actor_id", "ActorID")),
            before_state=str(_pick(data, "before_state", "BeforeState")),
            after_state=str(_pick(data, "after_state", "AfterState")),
            reason=str(_pick(data, "reason", "Reason")),
            occurred_at=str(_pick(data, "occurred_at", "OccurredAt")),
        )


@dataclass
class BubbleRelationEvent:
    relation_id: str = ""
    relation_event_type: str = ""
    behavior_event_id: str = ""
    from_bubble: str = ""
    to_bubble: str = ""
    slot_id: str = ""
    relation_role: str = ""
    mount_state: str = ""
    occurred_at: str = ""

    @classmethod
    def from_api(cls, data: Any) -> "BubbleRelationEvent":
        if not isinstance(data, dict):
            return cls()
        return cls(
            relation_id=str(_pick(data, "relation_id", "RelationID")),
            relation_event_type=str(_pick(data, "relation_event_type", "RelationEventType")),
            behavior_event_id=str(_pick(data, "behavior_event_id", "BehaviorEventID")),
            from_bubble=str(_pick(data, "from_bubble", "FromBubble")),
            to_bubble=str(_pick(data, "to_bubble", "ToBubble")),
            slot_id=str(_pick(data, "slot_id", "SlotID")),
            relation_role=str(_pick(data, "relation_role", "RelationRole")),
            mount_state=str(_pick(data, "mount_state", "MountState")),
            occurred_at=str(_pick(data, "occurred_at", "OccurredAt")),
        )


@dataclass
class BubbleResidue:
    residue_id: str = ""
    residue_type: str = ""
    source_bubble_id: str = ""
    contributor_bubble_id: str = ""
    contribution_role: str = ""
    content_ref: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    acceptance_result: str = ""
    credit_settlement_ref: str = ""
    reusable: bool = False
    created_at: str = ""

    @classmethod
    def from_api(cls, data: Any) -> "BubbleResidue":
        if not isinstance(data, dict):
            return cls()
        return cls(
            residue_id=str(_pick(data, "residue_id", "ResidueID")),
            residue_type=str(_pick(data, "residue_type", "ResidueType")),
            source_bubble_id=str(_pick(data, "source_bubble_id", "SourceBubbleID")),
            contributor_bubble_id=str(_pick(data, "contributor_bubble_id", "ContributorBubbleID")),
            contribution_role=str(_pick(data, "contribution_role", "ContributionRole")),
            content_ref=str(_pick(data, "content_ref", "ContentRef")),
            evidence_refs=_string_list(_pick(data, "evidence_refs", "EvidenceRefs", default=[])),
            acceptance_result=str(_pick(data, "acceptance_result", "AcceptanceResult")),
            credit_settlement_ref=str(_pick(data, "credit_settlement_ref", "CreditSettlementRef")),
            reusable=bool(_pick(data, "reusable", "Reusable", default=False)),
            created_at=str(_pick(data, "created_at", "CreatedAt")),
        )


@dataclass
class BubbleMemoryRecordReference:
    memory_record_id: str = ""
    memory_bubble_id: str = ""
    source_bubble_id: str = ""
    memory_scope: str = ""

    @classmethod
    def from_api(cls, data: Any) -> "BubbleMemoryRecordReference":
        if not isinstance(data, dict):
            return cls()
        return cls(
            memory_record_id=str(_pick(data, "memory_record_id", "MemoryRecordID")),
            memory_bubble_id=str(_pick(data, "memory_bubble_id", "MemoryBubbleID")),
            source_bubble_id=str(_pick(data, "source_bubble_id", "SourceBubbleID")),
            memory_scope=str(_pick(data, "memory_scope", "MemoryScope")),
        )


@dataclass
class BubbleSnapshot:
    bubble: BubbleRecord = field(default_factory=BubbleRecord)
    children: list[BubbleRecord] = field(default_factory=list)
    mounts: list[BubbleMountRecord] = field(default_factory=list)
    mounted_bubbles: list[BubbleRecord] = field(default_factory=list)
    behavior_events: list[BubbleBehaviorEvent] = field(default_factory=list)
    relation_events: list[BubbleRelationEvent] = field(default_factory=list)
    residues: list[BubbleResidue] = field(default_factory=list)
    memory_bubbles: list[BubbleRecord] = field(default_factory=list)
    memory_records: list[BubbleMemoryRecordReference] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: Any) -> "BubbleSnapshot":
        if not isinstance(data, dict):
            return cls()
        return cls(
            bubble=BubbleRecord.from_api(_pick(data, "bubble", "Bubble", default={})),
            children=[BubbleRecord.from_api(item) for item in _list_value(_pick(data, "children", "Children", default=[]))],
            mounts=[BubbleMountRecord.from_api(item) for item in _list_value(_pick(data, "mounts", "Mounts", default=[]))],
            mounted_bubbles=[
                BubbleRecord.from_api(item)
                for item in _list_value(_pick(data, "mounted_bubbles", "MountedBubbles", default=[]))
            ],
            behavior_events=[
                BubbleBehaviorEvent.from_api(item)
                for item in _list_value(_pick(data, "behavior_events", "BehaviorEvents", default=[]))
            ],
            relation_events=[
                BubbleRelationEvent.from_api(item)
                for item in _list_value(_pick(data, "relation_events", "RelationEvents", default=[]))
            ],
            residues=[BubbleResidue.from_api(item) for item in _list_value(_pick(data, "residues", "Residues", default=[]))],
            memory_bubbles=[
                BubbleRecord.from_api(item)
                for item in _list_value(_pick(data, "memory_bubbles", "MemoryBubbles", default=[]))
            ],
            memory_records=[
                BubbleMemoryRecordReference.from_api(item)
                for item in _list_value(_pick(data, "memory_records", "MemoryRecords", default=[]))
            ],
        )

    def summary(self, *, max_events: int = 20, max_residues: int = 20) -> dict[str, Any]:
        return {
            "bubble": self.bubble.summary(),
            "children": [item.summary() for item in self.children],
            "mounts": [item.summary() for item in self.mounts],
            "mounted_bubbles": [item.summary() for item in self.mounted_bubbles],
            "behavior_events": [
                {
                    "event_id": item.event_id,
                    "behavior_event_type": item.behavior_event_type,
                    "bubble_id": item.bubble_id,
                    "actor_id": item.actor_id,
                    "before_state": item.before_state,
                    "after_state": item.after_state,
                    "reason": item.reason,
                    "occurred_at": item.occurred_at,
                }
                for item in self.behavior_events[:max_events]
            ],
            "relation_events": [
                {
                    "relation_id": item.relation_id,
                    "relation_event_type": item.relation_event_type,
                    "from_bubble": item.from_bubble,
                    "to_bubble": item.to_bubble,
                    "slot_id": item.slot_id,
                    "mount_state": item.mount_state,
                    "occurred_at": item.occurred_at,
                }
                for item in self.relation_events[:max_events]
            ],
            "residues": [
                {
                    "residue_id": item.residue_id,
                    "residue_type": item.residue_type,
                    "source_bubble_id": item.source_bubble_id,
                    "contributor_bubble_id": item.contributor_bubble_id,
                    "content_ref": item.content_ref,
                    "acceptance_result": item.acceptance_result,
                    "reusable": item.reusable,
                    "created_at": item.created_at,
                }
                for item in self.residues[:max_residues]
            ],
            "memory_bubbles": [item.summary() for item in self.memory_bubbles],
            "memory_records": [
                {
                    "memory_record_id": item.memory_record_id,
                    "memory_bubble_id": item.memory_bubble_id,
                    "source_bubble_id": item.source_bubble_id,
                    "memory_scope": item.memory_scope,
                }
                for item in self.memory_records
            ],
            "truncated": {
                "behavior_events": max(0, len(self.behavior_events) - max_events),
                "relation_events": max(0, len(self.relation_events) - max_events),
                "residues": max(0, len(self.residues) - max_residues),
            },
        }
