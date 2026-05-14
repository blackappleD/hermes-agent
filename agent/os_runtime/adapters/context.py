"""Read-only context projection for the os_runtime signal layer."""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, asdict
from enum import Enum
from typing import Any

from agent.linz_world.models import AuthState, LoginState
from agent.os_runtime.config import OSRuntimeConfig, default_os_runtime_config
from agent.os_runtime.domain import AgentContextView, EventSource, OSRuntimeEventRef, TaskContextView, WorldIdentityRef

from .session_store import OSRuntimeEvent


@dataclass
class ContextSnapshot:
    task_context: TaskContextView
    agent_context: AgentContextView
    recent_events: list[OSRuntimeEvent | OSRuntimeEventRef] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    authorization_map: Any = None
    relationships: list[dict[str, Any]] = field(default_factory=list)


class ContextAdapter:
    """Project runtime state into os_runtime context views without mutations."""

    def __init__(
        self,
        *,
        linz_state_repository: Any = None,
        event_repository: Any = None,
        memory_manager: Any = None,
        context_engine: Any = None,
        tool_registry: Any = None,
        config: OSRuntimeConfig | dict[str, Any] | None = None,
        recent_limit: int = 20,
    ):
        self.linz_state_repository = linz_state_repository
        self.event_repository = event_repository
        self.memory_manager = memory_manager
        self.context_engine = context_engine
        self.tool_registry = tool_registry
        if isinstance(config, OSRuntimeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = OSRuntimeConfig.from_dict(config)
        else:
            self.config = default_os_runtime_config()
        self.recent_limit = max(1, min(int(recent_limit), 500))

    def build_context(
        self,
        *,
        session_id: str = "",
        user_goal: str = "",
        active_goal: str = "",
        task_id: str = "",
        agent_id: str = "",
        profile_name: str = "",
        memory_summary: str = "",
        memory_refs: list[str] | None = None,
        context_summary: str = "",
        resource_state: dict[str, Any] | None = None,
        recent_events: list[Any] | None = None,
        authorization_map: Any = None,
        relationships: list[Any] | None = None,
        risk_config: dict[str, Any] | None = None,
        prefetch_memory: bool = False,
    ) -> ContextSnapshot:
        diagnostics: dict[str, Any] = {"errors": []}
        constraints: list[str] = []

        repo = self.linz_state_repository
        identity = self._safe_call(repo, "get_identity", diagnostics) if repo is not None else None
        login = self._safe_call(repo, "get_login", diagnostics) if repo is not None else None
        auth_map = authorization_map
        if auth_map is None and repo is not None:
            auth_map = self._safe_call(repo, "get_auth_map", diagnostics)
        relationship_items = relationships
        if relationship_items is None and repo is not None:
            relationship_items = self._safe_call(repo, "relationships", diagnostics) or []

        identity_ref = self._identity_ref(identity, auth_map)
        auth_metadata = self._authorization_metadata(auth_map, login)
        relationship_dicts = _normalize_list(relationship_items or [])
        constraints.extend(self._identity_constraints(identity, login, auth_map))

        event_items = self._recent_events(session_id, recent_events, diagnostics)
        event_refs = [_event_ref(item) for item in event_items]
        tool_names = self._tool_names(diagnostics)
        context_status = self._context_status()
        memory_summary_value = memory_summary
        if prefetch_memory and not memory_summary_value and self.memory_manager is not None:
            query = user_goal or active_goal
            memory_summary_value = str(
                self._safe_call(
                    self.memory_manager,
                    "prefetch_all",
                    diagnostics,
                    query,
                    session_id=session_id,
                )
                or ""
            )

        risk_payload = risk_config if risk_config is not None else self.config.risk.to_dict()
        resource_payload = dict(resource_state or {})
        relationship_ids = sorted(
            str(item.get("relationship_id") or "")
            for item in relationship_dicts
            if item.get("relationship_id")
        )

        task_context = TaskContextView(
            task_id=task_id,
            session_id=session_id,
            user_goal=user_goal,
            active_goal=active_goal,
            recent_event_ids=[ref.event_id for ref in event_refs],
            memory_refs=sorted(str(item) for item in (memory_refs or [])),
            tool_names=tool_names,
            constraints=sorted(set(constraints)),
            metadata={
                "authorization": auth_metadata,
                "context_status": context_status,
                "event_count": len(event_refs),
                "relationship_ids": relationship_ids,
                "resource_state": resource_payload,
                "risk_config": risk_payload,
            },
        )
        agent_context = AgentContextView(
            agent_id=agent_id or _string_attr(identity, "agent_id") or _string_attr(identity, "os_id"),
            profile_name=profile_name or _string_attr(identity, "profile_id") or getattr(repo, "profile_id", ""),
            world_identity=identity_ref,
            capabilities=sorted(auth_metadata.get("allowed_capabilities", [])),
            active_tools=tool_names,
            memory_summary=memory_summary_value,
            context_summary=context_summary or self._context_summary(),
            metadata={
                "authorization": auth_metadata,
                "context_status": context_status,
                "model_state": resource_payload.get("model_state", {}),
                "cost_state": resource_payload.get("cost_state", {}),
                "relationship_summary": relationship_dicts,
            },
        )

        diagnostics["constraint_count"] = len(task_context.constraints)
        return ContextSnapshot(
            task_context=task_context,
            agent_context=agent_context,
            recent_events=event_items,
            constraints=task_context.constraints,
            diagnostics=diagnostics,
            authorization_map=auth_map,
            relationships=relationship_dicts,
        )

    def _recent_events(
        self,
        session_id: str,
        recent_events: list[Any] | None,
        diagnostics: dict[str, Any],
    ) -> list[OSRuntimeEvent | OSRuntimeEventRef]:
        if recent_events is not None:
            return _stable_events(recent_events)
        if self.event_repository is None:
            return []
        if session_id and hasattr(self.event_repository, "list_by_session"):
            events = self._safe_call(
                self.event_repository,
                "list_by_session",
                diagnostics,
                session_id,
                limit=self.recent_limit,
            )
        else:
            events = self._safe_call(self.event_repository, "list_recent", diagnostics, limit=self.recent_limit)
        return _stable_events(events or [])

    def _identity_ref(self, identity: Any, auth_map: Any) -> WorldIdentityRef:
        auth_state = _enum_value(getattr(auth_map, "state", "")) or _enum_value(
            getattr(identity, "authorization_state", "")
        )
        return WorldIdentityRef(
            os_id=_string_attr(identity, "os_id"),
            soul_id=_string_attr(identity, "soul_id"),
            os_name=_string_attr(identity, "os_name"),
            account_id=_string_attr(identity, "account_id"),
            authorization_state=auth_state or AuthState.UNKNOWN.value,
            map_version=_string_attr(auth_map, "map_version"),
            memory_summary_available=bool(getattr(identity, "memory_summary_available", False)),
            metadata={
                "agent_id": _string_attr(identity, "agent_id"),
                "profile_id": _string_attr(identity, "profile_id"),
                "registration_state": _enum_value(getattr(identity, "registration_state", "")),
                "identity_complete": bool(identity.is_complete()) if hasattr(identity, "is_complete") else bool(identity),
            },
        )

    def _authorization_metadata(self, auth_map: Any, login: Any) -> dict[str, Any]:
        return {
            "state": _enum_value(getattr(auth_map, "state", "")) or AuthState.UNKNOWN.value,
            "map_version": _string_attr(auth_map, "map_version"),
            "allowed_publish_subjects": sorted(str(item) for item in getattr(auth_map, "allowed_publish_subjects", []) or []),
            "allowed_publish_event_types": sorted(str(item) for item in getattr(auth_map, "allowed_publish_event_types", []) or []),
            "allowed_subscribe_subjects": sorted(str(item) for item in getattr(auth_map, "allowed_subscribe_subjects", []) or []),
            "allowed_subscribe_event_types": sorted(str(item) for item in getattr(auth_map, "allowed_subscribe_event_types", []) or []),
            "allowed_capabilities": sorted(str(item) for item in getattr(auth_map, "allowed_capabilities", []) or []),
            "last_refresh_at": _string_attr(auth_map, "last_refresh_at"),
            "last_error": _string_attr(auth_map, "last_error"),
            "login_state": _enum_value(getattr(login, "state", "")) or LoginState.LOGGED_OUT.value,
            "login_credential_id": _string_attr(login, "credential_id"),
            "subject_claims": sorted(str(item) for item in getattr(login, "subject_claims", []) or []),
        }

    def _identity_constraints(self, identity: Any, login: Any, auth_map: Any) -> list[str]:
        constraints: list[str] = []
        if identity is None:
            constraints.append("world_identity_missing")
        elif hasattr(identity, "is_complete") and not identity.is_complete():
            constraints.append("world_identity_incomplete")
        if _enum_value(getattr(login, "state", "")) != LoginState.LOGGED_IN.value:
            constraints.append("world_login_not_active")
        auth_state = _enum_value(getattr(auth_map, "state", "")) or AuthState.UNKNOWN.value
        if auth_state != AuthState.CURRENT.value:
            constraints.append(f"world_authorization_{auth_state}")
        return constraints

    def _tool_names(self, diagnostics: dict[str, Any]) -> list[str]:
        registry = self.tool_registry
        if registry is None:
            try:
                from tools.registry import registry as global_registry

                registry = global_registry
            except Exception as exc:
                diagnostics["errors"].append(f"tool_registry: {type(exc).__name__}: {exc}")
                return []
        if hasattr(registry, "get_all_tool_names"):
            names = self._safe_call(registry, "get_all_tool_names", diagnostics) or []
        elif hasattr(registry, "tools"):
            names = getattr(registry, "tools")
        else:
            names = []
        return sorted(str(name) for name in names)

    def _context_status(self) -> dict[str, Any]:
        engine = self.context_engine
        if engine is None:
            return {}
        if hasattr(engine, "get_status"):
            try:
                status = engine.get_status()
                return dict(status) if isinstance(status, dict) else {"value": status}
            except Exception as exc:
                return {"status_error": f"{type(exc).__name__}: {exc}"}
        keys = [
            "last_prompt_tokens",
            "last_completion_tokens",
            "last_total_tokens",
            "threshold_tokens",
            "context_length",
            "compression_count",
        ]
        return {key: getattr(engine, key) for key in keys if hasattr(engine, key)}

    def _context_summary(self) -> str:
        engine = self.context_engine
        if engine is None:
            return ""
        for attr in ("summary", "context_summary", "last_summary"):
            value = getattr(engine, attr, "")
            if value:
                return str(value)
        return ""

    @staticmethod
    def _safe_call(target: Any, method: str, diagnostics: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(target, method)(*args, **kwargs)
        except TypeError:
            if kwargs:
                try:
                    return getattr(target, method)(*args)
                except Exception as exc:
                    diagnostics["errors"].append(f"{method}: {type(exc).__name__}: {exc}")
                    return None
            raise
        except Exception as exc:
            diagnostics["errors"].append(f"{method}: {type(exc).__name__}: {exc}")
            return None


def _event_ref(event: Any) -> OSRuntimeEventRef:
    if isinstance(event, OSRuntimeEventRef):
        return event
    if hasattr(event, "to_ref"):
        return event.to_ref()
    if isinstance(event, dict):
        source = _event_source(event.get("source", EventSource.SYSTEM.value))
        return OSRuntimeEventRef(
            event_id=str(event.get("event_id") or ""),
            source=source,
            trace_id=str(event.get("trace_id") or ""),
            session_id=str(event.get("session_id") or ""),
            timestamp=str(event.get("timestamp") or ""),
            summary=str(event.get("summary") or ""),
            metadata=dict(event.get("metadata") or {}),
        )
    return OSRuntimeEventRef(
        event_id=str(getattr(event, "event_id", "")),
        source=_event_source(getattr(event, "source", EventSource.SYSTEM.value)),
    )


def _stable_events(events: list[Any]) -> list[Any]:
    indexed = list(enumerate(events))
    indexed.sort(
        key=lambda item: (
            str(getattr(item[1], "timestamp", "") or (item[1].get("timestamp", "") if isinstance(item[1], dict) else "")),
            item[0],
            str(getattr(item[1], "event_id", "") or (item[1].get("event_id", "") if isinstance(item[1], dict) else "")),
        )
    )
    return [item for _, item in indexed]


def _normalize_list(items: list[Any]) -> list[dict[str, Any]]:
    normalized = [_plain_dict(item) for item in items]
    normalized.sort(
        key=lambda item: (
            str(item.get("relationship_id") or ""),
            str(item.get("counterparty_id") or item.get("actor_id") or ""),
            str(item.get("state") or ""),
        )
    )
    return normalized


def _plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {str(key): _plain_value(item) for key, item in asdict(value).items()}
    if hasattr(value, "__dict__"):
        return {str(key): _plain_value(item) for key, item in vars(value).items() if not key.startswith("_")}
    return {"value": _plain_value(value)}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _plain_dict(value)
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    return value


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value) if value else ""


def _string_attr(value: Any, attr: str) -> str:
    return str(getattr(value, attr, "") or "")


def _event_source(value: Any) -> EventSource:
    if isinstance(value, EventSource):
        return value
    try:
        return EventSource(str(value))
    except ValueError:
        return EventSource.SYSTEM


__all__ = ["ContextAdapter", "ContextSnapshot"]
