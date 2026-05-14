"""Read-only aggregation for dashboard OS_RUNTIME log monitoring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from hermes_cli.logs import _read_last_n_lines


MAX_LINES = 500
DEFAULT_LINES = 100

PRIMARY_MODULES = ("life_state", "tension_field", "action_potential")

MODULE_TITLES = {
    "life_state": "Life State",
    "tension_field": "Tension Field",
    "action_potential": "Action Potential",
    "self_prompt": "SelfPrompt",
    "open_intent": "OpenIntent",
    "arbitration": "Arbitration",
    "runtime_driver": "Runtime Driver",
}

STEP_MODULES = {
    "life_state": "life_state",
    "tension_set": "tension_field",
    "tension_field": "tension_field",
    "action_potential": "action_potential",
    "self_prompt": "self_prompt",
    "open_intent": "open_intent",
    "intent": "open_intent",
    "arbiter": "arbitration",
    "arbitration": "arbitration",
    "runtime_driver": "runtime_driver",
    "driver": "runtime_driver",
    "autonomous_loop": "runtime_driver",
}

LIFE_STATE_FIELDS = (
    "energy",
    "fatigue",
    "health",
    "wakefulness",
    "curiosity",
    "boredom",
    "creative_pressure",
    "social_hunger",
    "silence_pressure",
    "restraint",
    "life_cycle",
    "recovery_cycle",
    "generated_intent_count",
)

ACTION_POTENTIAL_FIELDS = (
    "value_potential",
    "mutual_benefit_potential",
    "learning_potential",
    "risk_cost",
    "overall_score",
    "recommended_depth",
    "rationale",
)

SELF_PROMPT_FIELDS = (
    "prompt_id",
    "state_summary",
    "tension_summary",
    "potential_summary",
    "environment_scope",
)

OPEN_INTENT_FIELDS = (
    "intent_id",
    "description",
    "action_family",
    "risk_level",
    "success_condition",
)

ARBITRATION_FIELDS = (
    "decision",
    "verdict",
    "risk",
    "rationale",
    "requires_approval",
)

RUNTIME_DRIVER_FIELDS = (
    "status",
    "should_continue",
    "reason",
    "turns_used",
    "max_turns",
    "paused_reason",
)


def get_os_runtime_logs(lines: int = DEFAULT_LINES, include_raw: bool = True) -> dict[str, Any]:
    """Return module snapshots and raw OS_RUNTIME lines for the current profile."""

    requested_lines = _coerce_int(lines, DEFAULT_LINES)
    limit = _clamp_lines(requested_lines)
    files = _discover_log_files()
    if not files:
        return _empty_response(
            requested_lines=requested_lines,
            read_lines=0,
            include_raw=include_raw,
            empty_reason="No OS_RUNTIME log lines found for the current profile.",
        )

    source = files[0]
    raw_lines = [line.rstrip("\n") for line in _read_last_n_lines(source, limit)]
    if not raw_lines:
        return _empty_response(
            requested_lines=requested_lines,
            read_lines=0,
            include_raw=include_raw,
            source_files=[source.name],
            empty_reason="No OS_RUNTIME log lines found for the current profile.",
        )

    modules: dict[str, dict[str, Any]] = {}
    previous_by_module: dict[str, dict[str, Any]] = {}
    parse_error_count = 0
    latest_timestamp = ""

    for raw_index, raw_line in enumerate(raw_lines):
        parsed = _parse_json_line(raw_line)
        if parsed is None:
            parse_error_count += 1
            continue
        timestamp = str(parsed.get("timestamp") or "")
        if timestamp:
            latest_timestamp = timestamp
        step = str(parsed.get("step") or "").strip().lower()
        module_id = STEP_MODULES.get(step)
        if not module_id:
            continue
        snapshot = _snapshot_for_record(module_id, parsed, raw_index, previous_by_module.get(module_id))
        if snapshot is None:
            continue
        previous_by_module[module_id] = {
            p["key"]: p.get("value") for p in snapshot.get("parameters", [])
        }
        modules[module_id] = snapshot

    ordered_modules = [_ensure_module(modules, module_id) for module_id in PRIMARY_MODULES]
    for module_id in ("self_prompt", "open_intent", "arbitration", "runtime_driver"):
        if module_id in modules:
            ordered_modules.append(modules[module_id])

    has_data = any(module.get("status") != "empty" for module in ordered_modules)
    return {
        "mode": "os_runtime",
        "source_files": [source.name],
        "updated_at": latest_timestamp if has_data else "",
        "modules": ordered_modules,
        "raw_lines": raw_lines if include_raw else [],
        "raw_line_count": len(raw_lines) if include_raw else 0,
        "parse_error_count": parse_error_count,
        "empty_reason": "" if has_data or raw_lines else "No OS_RUNTIME log lines found for the current profile.",
        "limits": {
            "requested_lines": requested_lines,
            "max_lines": MAX_LINES,
            "read_lines": len(raw_lines),
        },
    }


def _discover_log_files() -> list[Path]:
    log_dir = get_hermes_home() / "logs"
    if not log_dir.exists():
        return []
    return sorted(
        (path for path in log_dir.glob("os_runtime_*.log") if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )


def _parse_json_line(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _snapshot_for_record(
    module_id: str,
    record: dict[str, Any],
    raw_index: int,
    previous: dict[str, Any] | None,
) -> dict[str, Any] | None:
    data = record.get("data")
    if not isinstance(data, dict):
        data = {}
    payload = _payload_for_module(module_id, data)
    if not isinstance(payload, dict):
        return None
    params = _parameters_for_module(module_id, payload, record, previous or {})
    metadata = _metadata_for_module(module_id, payload)
    status = "ok" if params else "partial"
    return {
        "module_id": module_id,
        "title": MODULE_TITLES.get(module_id, _label(module_id)),
        "summary": _summary_for_module(module_id, params, payload),
        "updated_at": str(record.get("timestamp") or ""),
        "status": status,
        "parameters": params,
        "raw_line_indexes": [raw_index],
        "metadata": metadata,
    }


def _payload_for_module(module_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    state = data.get("state")
    if not isinstance(state, dict):
        state = {}
    keys_by_module = {
        "life_state": ("life_state",),
        "tension_field": ("tension_set", "tension_field"),
        "action_potential": ("action_potential",),
        "self_prompt": ("self_prompt",),
        "open_intent": ("open_intent", "intent"),
        "arbitration": ("arbitration", "arbiter", "last_arbitration"),
        "runtime_driver": ("runtime_driver", "driver", "decision", "state"),
    }
    for key in keys_by_module.get(module_id, (module_id,)):
        value = data.get(key)
        if isinstance(value, dict):
            return value
        value = state.get(key)
        if isinstance(value, dict):
            return value
    if module_id == "life_state" and any(key in data for key in LIFE_STATE_FIELDS):
        return data
    if module_id == "action_potential" and any(key in data for key in ACTION_POTENTIAL_FIELDS):
        return data
    if module_id == "runtime_driver" and any(key in data for key in RUNTIME_DRIVER_FIELDS):
        return data
    return None


def _parameters_for_module(
    module_id: str,
    payload: dict[str, Any],
    record: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, Any]]:
    if module_id == "life_state":
        return _field_parameters(payload, LIFE_STATE_FIELDS, record, previous)
    if module_id == "action_potential":
        return _field_parameters(payload, ACTION_POTENTIAL_FIELDS, record, previous)
    if module_id == "self_prompt":
        return _field_parameters(payload, SELF_PROMPT_FIELDS, record, previous)
    if module_id == "open_intent":
        return _field_parameters(payload, OPEN_INTENT_FIELDS, record, previous)
    if module_id == "arbitration":
        return _field_parameters(payload, ARBITRATION_FIELDS, record, previous)
    if module_id == "runtime_driver":
        return _field_parameters(payload, RUNTIME_DRIVER_FIELDS, record, previous)
    if module_id == "tension_field":
        return _tension_parameters(payload, record, previous)
    return []


def _field_parameters(
    payload: dict[str, Any],
    fields: tuple[str, ...],
    record: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, Any]]:
    params = []
    for key in fields:
        if key not in payload or payload.get(key) is None:
            continue
        params.append(_parameter(key, payload.get(key), record, previous.get(key)))
    return params


def _tension_parameters(
    payload: dict[str, Any],
    record: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, Any]]:
    tensions = []
    for key in ("core_tensions", "dynamic_tensions", "tensions"):
        value = payload.get(key)
        if isinstance(value, list):
            tensions.extend(item for item in value if isinstance(item, dict))

    params: list[dict[str, Any]] = []
    params.append(_parameter("active_tensions", len(tensions), record, previous.get("active_tensions")))

    top = None
    if tensions:
        top = max(
            tensions,
            key=lambda item: _number(item.get("activation"), _number(item.get("intensity"), 0.0)),
        )
    if top:
        for source_key, param_key in (
            ("tension_id", "top_tension_id"),
            ("tension_type", "top_tension_type"),
            ("intensity", "intensity"),
            ("activation", "activation"),
            ("trend", "trend"),
            ("trend_slope", "trend_slope"),
            ("confidence", "confidence"),
            ("baseline", "baseline"),
        ):
            if source_key in top and top.get(source_key) is not None:
                params.append(_parameter(param_key, top.get(source_key), record, previous.get(param_key)))
    for key in ("intensity", "activation", "trend", "trend_slope", "confidence", "baseline"):
        if key in payload and payload.get(key) is not None and not any(p["key"] == key for p in params):
            params.append(_parameter(key, payload.get(key), record, previous.get(key)))

    edges = payload.get("propagation_edges")
    if isinstance(edges, list):
        params.append(_parameter("propagation_edges", len(edges), record, previous.get("propagation_edges")))
    return params


def _parameter(key: str, value: Any, record: dict[str, Any], previous: Any) -> dict[str, Any]:
    change, delta = _change(value, previous)
    return {
        "key": key,
        "label": _label(key),
        "value": value,
        "previous_value": previous,
        "change": change,
        "delta": delta,
        "unit": "",
        "evidence_step": str(record.get("step") or ""),
        "evidence_trace_id": str(record.get("trace_id") or ""),
    }


def _change(value: Any, previous: Any) -> tuple[str, float | None]:
    if previous is None:
        return "unknown", None
    if isinstance(value, bool) or isinstance(previous, bool):
        return ("unchanged" if value == previous else "changed"), None
    if isinstance(value, (int, float)) and isinstance(previous, (int, float)):
        delta = float(value) - float(previous)
        if abs(delta) < 1e-9:
            return "unchanged", 0.0
        return ("up" if delta > 0 else "down"), delta
    return ("unchanged" if value == previous else "changed"), None


def _summary_for_module(module_id: str, params: list[dict[str, Any]], payload: dict[str, Any]) -> str:
    if module_id == "self_prompt":
        return str(payload.get("state_summary") or payload.get("tension_summary") or "")[:180]
    if module_id == "open_intent":
        return str(payload.get("description") or payload.get("success_condition") or "")[:180]
    if module_id == "arbitration":
        return str(payload.get("rationale") or payload.get("decision") or payload.get("verdict") or "")[:180]
    if module_id == "runtime_driver":
        return str(payload.get("reason") or payload.get("paused_reason") or payload.get("status") or "")[:180]
    important = params[:3]
    return ", ".join(f"{param['label']} {param['value']}" for param in important)


def _metadata_for_module(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if module_id != "tension_field":
        return {}
    tensions = []
    for key in ("core_tensions", "dynamic_tensions", "tensions"):
        value = payload.get(key)
        if isinstance(value, list):
            tensions.extend(item for item in value if isinstance(item, dict))
    return {
        "core_count": len(payload.get("core_tensions") or []) if isinstance(payload.get("core_tensions"), list) else 0,
        "dynamic_count": len(payload.get("dynamic_tensions") or []) if isinstance(payload.get("dynamic_tensions"), list) else 0,
        "tension_count": len(tensions),
    }


def _ensure_module(modules: dict[str, dict[str, Any]], module_id: str) -> dict[str, Any]:
    if module_id in modules:
        return modules[module_id]
    return _empty_module(module_id)


def _empty_module(module_id: str) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "title": MODULE_TITLES[module_id],
        "summary": "",
        "updated_at": "",
        "status": "empty",
        "parameters": [],
        "raw_line_indexes": [],
        "metadata": {},
    }


def _empty_response(
    *,
    requested_lines: int,
    read_lines: int,
    include_raw: bool,
    source_files: list[str] | None = None,
    empty_reason: str,
) -> dict[str, Any]:
    return {
        "mode": "os_runtime",
        "source_files": source_files or [],
        "updated_at": "",
        "modules": [_empty_module(module_id) for module_id in PRIMARY_MODULES],
        "raw_lines": [] if include_raw else [],
        "raw_line_count": 0,
        "parse_error_count": 0,
        "empty_reason": empty_reason,
        "limits": {
            "requested_lines": requested_lines,
            "max_lines": MAX_LINES,
            "read_lines": read_lines,
        },
    }


def _label(key: str) -> str:
    return key.replace("_", " ").title()


def _number(value: Any, default: float) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_lines(value: int) -> int:
    return max(1, min(value, MAX_LINES))


__all__ = ["DEFAULT_LINES", "MAX_LINES", "get_os_runtime_logs"]
