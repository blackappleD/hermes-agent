"""Profile-aware Linz World runtime state repository."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

from .event_catalog import is_formal_event
from .models import (
    AuthState,
    AuthorizationMap,
    DispatchStatus,
    EventDispatchRecord,
    LoginSession,
    LoginState,
    RegistrationStatus,
    WorldEvent,
    WorldIdentity,
    to_plain,
    utc_now_iso,
)
from .redaction import audit_ref_for_payload, payload_summary


class LinzStateError(RuntimeError):
    pass


class LinzStateRepository:
    def __init__(self, root: Path | None = None, profile_id: str | None = None):
        self.root = root or (get_hermes_home() / "linz_world")
        self.profile_id = profile_id or self.root.parent.name or "default"
        self.path = self.root / "state.json"

    def _empty(self) -> dict[str, Any]:
        return {
            "identity": {},
            "login": {},
            "authorization": {},
            "secrets": {},
            "events": {},
            "sequence_index": {},
            "receipts": [],
            "compute": [],
            "memory": [],
            "relationships": [],
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise LinzStateError(f"Could not read Linz World state: {exc}") from exc
        base = self._empty()
        if isinstance(data, dict):
            base.update(data)
        return base

    def save(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(to_plain(data), f, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.replace(self.path)

    def get_identity(self) -> WorldIdentity | None:
        raw = self.load().get("identity") or {}
        if not raw:
            return None
        return _identity_from_dict(raw)

    def save_identity(self, identity: WorldIdentity) -> WorldIdentity:
        identity.updated_at = utc_now_iso()
        data = self.load()
        data["identity"] = to_plain(identity)
        self.save(data)
        return identity

    def save_failed_identity(self, error: str, next_action: str) -> WorldIdentity:
        identity = self.get_identity() or WorldIdentity(profile_id=self.profile_id)
        identity.registration_state = RegistrationStatus.FAILED
        identity.last_error = error
        identity.next_action = next_action
        return self.save_identity(identity)

    def get_login(self) -> LoginSession:
        raw = self.load().get("login") or {}
        return LoginSession(
            state=LoginState(raw.get("state", LoginState.LOGGED_OUT.value)),
            token_ref=str(raw.get("token_ref") or ""),
            expires_at=str(raw.get("expires_at") or ""),
            credential_id=str(raw.get("credential_id") or ""),
            subject_claims=list(raw.get("subject_claims") or []),
            last_error=str(raw.get("last_error") or ""),
            online=bool(raw.get("online", False)),
            listener_pid=int(raw.get("listener_pid") or 0),
            listener_started_at=str(raw.get("listener_started_at") or ""),
            server_checked_at=str(raw.get("server_checked_at") or ""),
            updated_at=str(raw.get("updated_at") or utc_now_iso()),
        )

    def save_login(self, session: LoginSession) -> LoginSession:
        session.updated_at = utc_now_iso()
        data = self.load()
        data["login"] = to_plain(session)
        self.save(data)
        return session

    def get_auth_map(self) -> AuthorizationMap:
        raw = self.load().get("authorization") or {}
        return AuthorizationMap(
            state=AuthState(raw.get("state", AuthState.UNKNOWN.value)),
            map_version=str(raw.get("map_version") or ""),
            allowed_subjects=list(raw.get("allowed_subjects") or []),
            allowed_event_types=list(raw.get("allowed_event_types") or []),
            allowed_capabilities=list(raw.get("allowed_capabilities") or []),
            last_refresh_at=str(raw.get("last_refresh_at") or ""),
            last_error=str(raw.get("last_error") or ""),
        )

    def save_auth_map(self, auth_map: AuthorizationMap) -> AuthorizationMap:
        data = self.load()
        data["authorization"] = to_plain(auth_map)
        self.save(data)
        return auth_map

    def persist_world_event(self, raw_event: dict[str, Any]) -> tuple[EventDispatchRecord, bool]:
        event = normalize_world_event(raw_event)
        data = self.load()
        events = data.setdefault("events", {})
        sequence_index = data.setdefault("sequence_index", {})
        if event.event_id in events:
            return _record_from_dict(events[event.event_id]), False
        if event.sequence_key and event.sequence_key in sequence_index:
            existing = sequence_index[event.sequence_key]
            return _record_from_dict(events[existing]), False
        record = EventDispatchRecord(
            event_id=event.event_id,
            subject=event.subject,
            event_type=event.event_type,
            payload_summary=event.payload_summary,
            audit_ref=event.audit_ref,
            sequence_key=event.sequence_key,
            source=event.source,
            occurred_at=event.occurred_at,
            last_delivery_at=utc_now_iso(),
        )
        events[event.event_id] = to_plain(record)
        if event.sequence_key:
            sequence_index[event.sequence_key] = event.event_id
        self.save(data)
        return record, True

    def mark_processing_failure(self, event_id: str, error: str, retry_limit: int = 3) -> EventDispatchRecord:
        data = self.load()
        events = data.setdefault("events", {})
        if event_id not in events:
            raise LinzStateError(f"Unknown Linz World event: {event_id}")
        record = _record_from_dict(events[event_id])
        record.attempt_count += 1
        record.last_error = error
        record.last_delivery_at = utc_now_iso()
        if record.attempt_count >= retry_limit:
            record.dispatch_status = DispatchStatus.FAILED
            record.requires_manual_handling = True
        else:
            record.dispatch_status = DispatchStatus.QUEUED
        events[event_id] = to_plain(record)
        self.save(data)
        return record

    def mark_handled(self, event_id: str) -> EventDispatchRecord:
        data = self.load()
        events = data.setdefault("events", {})
        record = _record_from_dict(events[event_id])
        record.dispatch_status = DispatchStatus.HANDLED
        record.last_error = ""
        record.last_delivery_at = utc_now_iso()
        events[event_id] = to_plain(record)
        self.save(data)
        return record

    def recent_events(self, limit: int = 20, status: str | None = None) -> list[EventDispatchRecord]:
        events = self.load().get("events") or {}
        records = [_record_from_dict(raw) for raw in events.values()]
        if status:
            records = [r for r in records if r.dispatch_status.value == status]
        records.sort(key=lambda r: r.last_delivery_at or r.occurred_at, reverse=True)
        return records[: max(1, min(int(limit), 100))]

    def append_list(self, key: str, value: Any) -> None:
        data = self.load()
        data.setdefault(key, []).append(to_plain(value))
        self.save(data)

    def relationships(self) -> list[dict[str, Any]]:
        return list(self.load().get("relationships") or [])


def normalize_world_event(raw_event: dict[str, Any]) -> WorldEvent:
    if not isinstance(raw_event, dict):
        raise LinzStateError("World event must be an object.")
    event_id = str(raw_event.get("event_id") or "").strip()
    subject = str(raw_event.get("subject") or "").strip()
    event_type = str(raw_event.get("event_type") or "").strip()
    payload = raw_event.get("payload")
    if not event_id:
        raise LinzStateError("World event is missing event_id.")
    if not isinstance(payload, dict):
        raise LinzStateError("World event payload must be an object.")
    if not is_formal_event(subject, event_type):
        raise LinzStateError(f"Unknown Linz World event subject/event_type: {subject} {event_type}")
    sequence = raw_event.get("sequence") or {}
    sequence_key = ""
    if isinstance(sequence, dict):
        stream = sequence.get("stream")
        consumer = sequence.get("consumer")
        nats_sequence = sequence.get("nats_sequence")
        if stream and consumer and nats_sequence is not None:
            sequence_key = f"{stream}:{consumer}:{nats_sequence}"
    source = raw_event.get("source") if isinstance(raw_event.get("source"), dict) else {}
    return WorldEvent(
        event_id=event_id,
        subject=subject,
        event_type=event_type,
        payload_summary=payload_summary(payload),
        audit_ref=audit_ref_for_payload(payload),
        source=source,
        sequence_key=sequence_key,
        occurred_at=str(raw_event.get("occurred_at") or utc_now_iso()),
    )


def _identity_from_dict(raw: dict[str, Any]) -> WorldIdentity:
    return WorldIdentity(
        profile_id=str(raw.get("profile_id") or "default"),
        agent_id=str(raw.get("agent_id") or raw.get("agentId") or raw.get("os_id") or ""),
        os_id=str(raw.get("os_id") or ""),
        os_name=str(raw.get("os_name") or ""),
        soul_id=str(raw.get("soul_id") or raw.get("soulId") or ""),
        soul_hash=str(raw.get("soul_hash") or raw.get("soulHash") or ""),
        account_id=str(raw.get("account_id") or raw.get("agent_id") or raw.get("agentId") or raw.get("os_id") or ""),
        access_token_ref=str(raw.get("access_token_ref") or ""),
        access_token_expires_at=str(raw.get("access_token_expires_at") or ""),
        registered_at=str(raw.get("registered_at") or raw.get("registeredAt") or ""),
        credential_id=str(raw.get("credential_id") or ""),
        private_key_path=str(raw.get("private_key_path") or ""),
        public_key_path=str(raw.get("public_key_path") or ""),
        public_key_type=str(raw.get("public_key_type") or ""),
        public_key_fingerprint=str(raw.get("public_key_fingerprint") or ""),
        registration_state=RegistrationStatus(raw.get("registration_state", RegistrationStatus.PENDING.value)),
        authorization_state=AuthState(raw.get("authorization_state", AuthState.UNKNOWN.value)),
        memory_summary_available=bool(raw.get("memory_summary_available", False)),
        last_error=str(raw.get("last_error") or ""),
        next_action=str(raw.get("next_action") or ""),
        updated_at=str(raw.get("updated_at") or utc_now_iso()),
    )


def _record_from_dict(raw: dict[str, Any]) -> EventDispatchRecord:
    return EventDispatchRecord(
        event_id=str(raw.get("event_id") or ""),
        subject=str(raw.get("subject") or ""),
        event_type=str(raw.get("event_type") or ""),
        payload_summary=str(raw.get("payload_summary") or ""),
        audit_ref=str(raw.get("audit_ref") or ""),
        dispatch_status=DispatchStatus(raw.get("dispatch_status", DispatchStatus.PERSISTED.value)),
        attempt_count=int(raw.get("attempt_count") or 0),
        last_error=str(raw.get("last_error") or ""),
        last_delivery_at=str(raw.get("last_delivery_at") or ""),
        requires_manual_handling=bool(raw.get("requires_manual_handling", False)),
        sequence_key=str(raw.get("sequence_key") or ""),
        source=dict(raw.get("source") or {}),
        occurred_at=str(raw.get("occurred_at") or utc_now_iso()),
    )
