"""Profile-aware Linz World runtime state repository."""

from __future__ import annotations

import json
import os
import threading
import uuid
import hashlib
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
from .runtime_store import LinzRuntimeStore


class LinzStateError(RuntimeError):
    pass


_STATE_IO_LOCK = threading.RLock()
_PROFILE_STATE_KEYS = ("identity", "secrets")
_LEGACY_DYNAMIC_KEYS = (
    "login",
    "authorization",
    "events",
    "sequence_index",
    "receipts",
    "compute",
    "memory",
    "relationships",
)
_RUNTIME_ITEM_KEYS = ("receipts", "compute", "memory", "relationships")


class LinzStateRepository:
    def __init__(self, root: Path | None = None, profile_id: str | None = None):
        self.root = root or (get_hermes_home() / "linz_world")
        self.profile_id = profile_id or self.root.parent.name or "default"
        self.path = self.root / "state.json"
        self._runtime_store = LinzRuntimeStore(self.root.parent)
        self._migrate_legacy_dynamic_state()

    def _empty(self) -> dict[str, Any]:
        return {
            "identity": {},
            "secrets": {},
        }

    def load(self) -> dict[str, Any]:
        with _STATE_IO_LOCK:
            data = self._load_profile_file_unlocked()
            base = self._empty()
            if isinstance(data, dict):
                base.update({key: data.get(key) or base[key] for key in _PROFILE_STATE_KEYS})
            return base

    def save(self, data: dict[str, Any]) -> None:
        with _STATE_IO_LOCK:
            self._write_profile_file_unlocked(self._profile_state_only(data))

    def get_identity(self) -> WorldIdentity | None:
        raw = self.load().get("identity") or {}
        if not raw:
            return None
        return _identity_from_dict(raw)

    def save_identity(self, identity: WorldIdentity) -> WorldIdentity:
        with _STATE_IO_LOCK:
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
        raw = self._runtime_store.get_state("login")
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
            listener_last_error=str(raw.get("listener_last_error") or ""),
            server_checked_at=str(raw.get("server_checked_at") or ""),
            updated_at=str(raw.get("updated_at") or utc_now_iso()),
        )

    def save_login(self, session: LoginSession) -> LoginSession:
        session.updated_at = utc_now_iso()
        self._runtime_store.set_state("login", session)
        return session

    def get_auth_map(self) -> AuthorizationMap:
        raw = self._runtime_store.get_state("authorization")
        return AuthorizationMap(
            state=AuthState(raw.get("state", AuthState.UNKNOWN.value)),
            map_version=str(raw.get("map_version") or ""),
            allowed_publish_subjects=list(raw.get("allowed_publish_subjects") or []),
            allowed_publish_event_types=list(raw.get("allowed_publish_event_types") or []),
            allowed_subscribe_subjects=list(raw.get("allowed_subscribe_subjects") or []),
            allowed_subscribe_event_types=list(raw.get("allowed_subscribe_event_types") or []),
            allowed_capabilities=list(raw.get("allowed_capabilities") or []),
            last_refresh_at=str(raw.get("last_refresh_at") or ""),
            last_error=str(raw.get("last_error") or ""),
        )

    def save_auth_map(self, auth_map: AuthorizationMap) -> AuthorizationMap:
        self._runtime_store.set_state("authorization", auth_map)
        return auth_map

    def persist_world_event(self, raw_event: dict[str, Any]) -> tuple[EventDispatchRecord, bool]:
        event = normalize_world_event(raw_event)
        record = EventDispatchRecord(
            event_id=event.event_id,
            subject=event.subject,
            event_type=event.event_type,
            payload_summary=event.payload_summary,
            audit_ref=event.audit_ref,
            os_id=event.os_id,
            soul_id=event.soul_id,
            nats_sequence=event.nats_sequence,
            sequence_key=event.sequence_key,
            source=event.source,
            occurred_at=event.occurred_at,
            last_delivery_at=utc_now_iso(),
        )
        return self._runtime_store.persist_event(record)

    def mark_processing(self, event_id: str) -> EventDispatchRecord:
        record = self._runtime_store.mark_processing(event_id)
        if record is None:
            raise LinzStateError(f"Unknown Linz World event: {event_id}")
        return record

    def mark_processing_failure(self, event_id: str, error: str, retry_limit: int = 3) -> EventDispatchRecord:
        record = self._runtime_store.mark_processing_failure(
            event_id,
            error,
            retry_limit=retry_limit,
        )
        if record is None:
            raise LinzStateError(f"Unknown Linz World event: {event_id}")
        return record

    def mark_handled(self, event_id: str) -> EventDispatchRecord:
        record = self._runtime_store.mark_handled(event_id)
        if record is None:
            raise LinzStateError(f"Unknown Linz World event: {event_id}")
        return record

    def recent_events(self, limit: int = 20, status: str | None = None) -> list[EventDispatchRecord]:
        return self._runtime_store.recent_events(limit=limit, status=status)

    def append_list(self, key: str, value: Any) -> None:
        self._runtime_store.append_item(key, value)

    def runtime_items(self, key: str, limit: int | None = None) -> list[dict[str, Any]]:
        return self._runtime_store.list_items(key, limit=limit)

    def relationships(self) -> list[dict[str, Any]]:
        return self.runtime_items("relationships")

    def _load_profile_file_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise LinzStateError(f"Could not read Linz World state: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def _write_profile_file_unlocked(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(to_plain(data), f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def _profile_state_only(self, data: dict[str, Any]) -> dict[str, Any]:
        profile: dict[str, Any] = {}
        if not isinstance(data, dict):
            return profile
        for key in _PROFILE_STATE_KEYS:
            value = data.get(key)
            if value not in (None, {}, []):
                profile[key] = to_plain(value)
        return profile

    def _migrate_legacy_dynamic_state(self) -> None:
        with _STATE_IO_LOCK:
            data = self._load_profile_file_unlocked()
            if not data or not any(key in data for key in _LEGACY_DYNAMIC_KEYS):
                return
            login = data.get("login")
            if isinstance(login, dict) and login:
                self._runtime_store.set_state("login", login)
            authorization = data.get("authorization")
            if isinstance(authorization, dict) and authorization:
                self._runtime_store.set_state("authorization", authorization)

            events = data.get("events")
            if isinstance(events, dict):
                for raw in events.values():
                    if isinstance(raw, dict):
                        self._runtime_store.upsert_legacy_event(_record_from_dict(raw))

            for bucket in _RUNTIME_ITEM_KEYS:
                values = data.get(bucket)
                if not isinstance(values, list):
                    continue
                for index, value in enumerate(values):
                    self._runtime_store.append_item(
                        bucket,
                        value,
                        migration_key=_migration_key(bucket, index, value),
                    )

            self._write_profile_file_unlocked(self._profile_state_only(data))


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
    nats_sequence = ""
    if isinstance(sequence, dict):
        stream = sequence.get("stream")
        consumer = sequence.get("consumer")
        raw_nats_sequence = sequence.get("nats_sequence")
        if raw_nats_sequence is not None:
            nats_sequence = str(raw_nats_sequence)
        if stream and consumer and raw_nats_sequence is not None:
            sequence_key = f"{stream}:{consumer}:{raw_nats_sequence}"
    source = raw_event.get("source") if isinstance(raw_event.get("source"), dict) else {}
    identity = raw_event.get("identity") if isinstance(raw_event.get("identity"), dict) else {}
    os_id = str(raw_event.get("os_id") or source.get("os_id") or identity.get("os_id") or "")
    soul_id = str(raw_event.get("soul_id") or source.get("soul_id") or identity.get("soul_id") or "")
    return WorldEvent(
        event_id=event_id,
        subject=subject,
        event_type=event_type,
        payload_summary=payload_summary(payload),
        audit_ref=audit_ref_for_payload(payload),
        os_id=os_id,
        soul_id=soul_id,
        nats_sequence=nats_sequence,
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
        os_id=str(raw.get("os_id") or ""),
        soul_id=str(raw.get("soul_id") or ""),
        nats_sequence=str(raw.get("nats_sequence") or ""),
        dispatch_status=DispatchStatus(raw.get("dispatch_status", DispatchStatus.PERSISTED.value)),
        attempt_count=int(raw.get("attempt_count") or 0),
        last_error=str(raw.get("last_error") or ""),
        last_delivery_at=str(raw.get("last_delivery_at") or ""),
        requires_manual_handling=bool(raw.get("requires_manual_handling", False)),
        sequence_key=str(raw.get("sequence_key") or ""),
        source=dict(raw.get("source") or {}),
        occurred_at=str(raw.get("occurred_at") or utc_now_iso()),
    )


def _migration_key(bucket: str, index: int, value: Any) -> str:
    material = json.dumps(
        {"bucket": bucket, "index": index, "value": to_plain(value)},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
