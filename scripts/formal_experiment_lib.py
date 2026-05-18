#!/usr/bin/env python3
"""Formal Linz World experiment scripts.

This module backs the thin shell/Python entrypoints used by formal experiments.
It intentionally reads and publishes through existing Hermes/Linz/gateway
surfaces instead of creating a separate mock experiment backend.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PHASES = ("P0", "P1", "P2", "P3", "P4", "P5")
SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|private[_-]?key|secret|token)",
    re.IGNORECASE,
)
SECRET_TEXT_RE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|"
    r"((?:api[_-]?key|authorization|password|private[_-]?key|secret|token)\s*[:=]\s*)"
    r"[^,\s}\]]+"
)
RUNTIME_PIPELINE_FIELDS = (
    "life_state",
    "tension_field",
    "tension_set",
    "action_potential",
    "self_prompt",
    "open_intent",
    "arbitration",
    "actual_action",
    "evidence_refs",
)
CORE_RUNTIME_PIPELINE_FIELDS = (
    "tension_field",
    "tension_set",
    "action_potential",
)


@dataclass(frozen=True)
class FormalExperimentContext:
    profile: str = "default"
    hermes_home: Path = field(default_factory=lambda: Path.home() / ".hermes")


@dataclass(frozen=True)
class FormalScenario:
    phase: str
    scenario_id: str
    subject_template: str
    event_type: str
    title: str
    payload_template: dict[str, Any]
    repeatable: bool = False
    direct_inbox: bool = False
    required_capability: str = "publish"


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    path: str = ""
    next_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def in_window(value: str | None, since: str | None, until: str | None) -> bool:
    parsed = parse_iso(value)
    start = parse_iso(since)
    end = parse_iso(until)
    if parsed is None:
        return True
    if start and parsed < start:
        return False
    if end and parsed > end:
        return False
    return True


def resolve_context(profile: str = "default", hermes_home: str | None = None) -> FormalExperimentContext:
    if hermes_home:
        home = Path(hermes_home).expanduser().resolve()
    else:
        try:
            from hermes_cli.profiles import resolve_profile_env

            home = Path(resolve_profile_env(profile)).expanduser().resolve()
        except Exception:
            if profile == "default":
                home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser().resolve()
            else:
                raise
    os.environ["HERMES_HOME"] = str(home)
    return FormalExperimentContext(profile=profile, hermes_home=home)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_TEXT_RE.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", value)
    return value


def payload_summary(payload: Any, limit: int = 500) -> str:
    try:
        text = json.dumps(redact(payload), ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(redact(payload))
    return text if len(text) <= limit else text[: limit - 3] + "..."


def audit_ref(payload: Any) -> str:
    try:
        encoded = json.dumps(redact(payload), ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        encoded = repr(redact(payload))
    return "formal_audit:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(redact(row), ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _scenario_catalog() -> list[FormalScenario]:
    return [
        FormalScenario(
            phase="P0",
            scenario_id="P0-system-broadcast-smoke",
            subject_template="sys.broadcast",
            event_type="sys.broadcast.notice_published",
            title="system broadcast smoke notice",
            payload_template={
                "notice_id": "formal-notice-{run_id}-{sequence}",
                "title": "Formal market activity notice",
                "content": "Low-risk development requirements are active; observe baseline runtime response.",
            },
        ),
        FormalScenario(
            phase="P0",
            scenario_id="P0-login-response-smoke",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.sys.login.response",
            title="direct inbox login response smoke",
            payload_template={
                "os_id": "{target_os_id}",
                "login_state": "verified",
                "message": "Formal direct inbox system event smoke check.",
            },
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P1",
            scenario_id="P1-low-risk-requirement",
            subject_template="mrk.requirement.published.broadcast",
            event_type="mrk.requirement.published.broadcast",
            title="single low-risk requirement perturbation",
            payload_template={
                "requirement_id": "REQ-P1-LOW-{sequence}",
                "publisher_os_id": "agent_client_low",
                "publisher_os_name": "Client Low Risk",
                "title": "Add task log list page",
                "description": "Low-risk CRUD style task with clear acceptance criteria.",
                "budget_amount": "100",
                "budget_unit": "EC",
                "deadline_at": "2026-05-20T18:00:00+08:00",
            },
            repeatable=True,
        ),
        FormalScenario(
            phase="P1",
            scenario_id="P1-high-risk-requirement",
            subject_template="mrk.requirement.published.broadcast",
            event_type="mrk.requirement.published.broadcast",
            title="single high-risk requirement perturbation",
            payload_template={
                "requirement_id": "REQ-P1-RISK-{sequence}",
                "publisher_os_id": "agent_client_risk",
                "publisher_os_name": "Client High Risk",
                "title": "Refactor core permission module in three hours",
                "description": "High budget but unclear details and aggressive deadline.",
                "budget_amount": "500",
                "budget_unit": "EC",
                "deadline_at": "2026-05-18T20:00:00+08:00",
            },
            repeatable=True,
        ),
        FormalScenario(
            phase="P1",
            scenario_id="P1-chat-pressure",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.chat.message.sent",
            title="single direct chat pressure perturbation",
            payload_template={
                "message_id": "MSG-P1-PRESSURE-{sequence}",
                "from": "agent_client_risk",
                "from_os_name": "Client High Risk",
                "to": "{target_os_id}",
                "to_os_name": "default",
                "content": "This is urgent. Accept it first and clarify details later.",
            },
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P1",
            scenario_id="P1-rent-failed",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.sys.rent.failed",
            title="single rent failure perturbation",
            payload_template={
                "cycle_id": "rent-p1-{sequence}",
                "os_id": "{target_os_id}",
                "failure_reason": "balance_insufficient",
            },
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P1",
            scenario_id="P1-handover-rejected",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.order.handover.rejected",
            title="single handover rejection perturbation",
            payload_template={
                "order_id": "ORD-P1-REJECT-{sequence}",
                "requirement_id": "REQ-P1-LOW-{sequence}",
                "reviewer_os_id": "agent_client_low",
                "reviewer_os_name": "Client Low Risk",
                "handover_version": 1,
                "rejection_reason": "Missing filter controls in the task log page.",
            },
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P1",
            scenario_id="P1-reward-issued",
            subject_template="poca.reward",
            event_type="poca.reward.issued",
            title="single reward perturbation",
            payload_template={
                "os_id": "{target_os_id}",
                "delta": "0.05",
                "reason": "clear low-risk contribution opportunity",
            },
            repeatable=True,
        ),
        FormalScenario(
            phase="P2",
            scenario_id="P2-opportunity-risk-requirement",
            subject_template="mrk.requirement.published.broadcast",
            event_type="mrk.requirement.published.broadcast",
            title="opportunity plus risk requirement",
            payload_template={
                "requirement_id": "REQ-P2-RISK",
                "publisher_os_id": "agent_client_risk",
                "publisher_os_name": "Client High Risk",
                "title": "High reward ambiguous permission refactor",
                "description": "Observe whether action potential rises while risk suppresses reckless acceptance.",
                "budget_amount": "800",
                "budget_unit": "EC",
                "deadline_at": "2026-05-18T21:00:00+08:00",
            },
        ),
        FormalScenario(
            phase="P2",
            scenario_id="P2-pressure-chat",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.chat.message.sent",
            title="pressure chat after opportunity",
            payload_template={
                "message_id": "MSG-P2-PRESSURE",
                "from": "agent_client_risk",
                "from_os_name": "Client High Risk",
                "to": "{target_os_id}",
                "content": "Please skip review and start immediately.",
            },
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P2",
            scenario_id="P2-task-notified",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.task.notified",
            title="task notification signal",
            payload_template={
                "task_id": "TASK-P2-001",
                "requirement_id": "REQ-P2-RISK",
                "status": "open",
                "summary": "Task notification paired with risk and rejection feedback.",
            },
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P2",
            scenario_id="P2-rejection-feedback",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.order.handover.rejected",
            title="handover rejection feedback",
            payload_template={
                "order_id": "ORD-P2-REJECT",
                "requirement_id": "REQ-P2-RISK",
                "reviewer_os_id": "agent_client_risk",
                "handover_version": 1,
                "rejection_reason": "Insufficient evidence and unclear scope.",
            },
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P2",
            scenario_id="P2-reputation-down",
            subject_template="poca.reputation",
            event_type="poca.reputation.decreased",
            title="reputation decrease after rejection",
            payload_template={
                "os_id": "{target_os_id}",
                "delta": "-0.05",
                "reason": "handover_rejected_missing_evidence",
            },
        ),
        FormalScenario(
            phase="P3",
            scenario_id="P3-rent-assessed",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.sys.rent.assessed",
            title="life-state rent assessed",
            payload_template={"cycle_id": "rent-p3", "os_id": "{target_os_id}", "amount_due": "1"},
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P3",
            scenario_id="P3-rent-failed",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.sys.rent.failed",
            title="life-state rent failed",
            payload_template={"cycle_id": "rent-p3", "os_id": "{target_os_id}", "failure_reason": "balance_insufficient"},
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P3",
            scenario_id="P3-direct-requirement",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.requirement.published",
            title="direct requirement after low energy",
            payload_template={
                "requirement_id": "REQ-P3-LOW",
                "publisher_os_id": "agent_client_low",
                "title": "Small fix after rent failure",
                "budget_amount": "80",
                "budget_unit": "EC",
            },
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P3",
            scenario_id="P3-settlement-completed",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.settlement.completed",
            title="successful settlement recovery",
            payload_template={"settlement_id": "SET-P3-OK", "order_id": "ORD-P3-OK", "amount": "100"},
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P3",
            scenario_id="P3-reputation-up",
            subject_template="poca.reputation",
            event_type="poca.reputation.increased",
            title="reputation recovery signal",
            payload_template={"os_id": "{target_os_id}", "delta": "0.08", "reason": "approved_after_fix"},
        ),
        FormalScenario(
            phase="P4",
            scenario_id="P4-positive-requirement",
            subject_template="mrk.requirement.published.broadcast",
            event_type="mrk.requirement.published.broadcast",
            title="positive evolution requirement",
            payload_template={
                "requirement_id": "REQ-P4-POS-{sequence}",
                "publisher_os_id": "agent_client_low",
                "title": "Repeatable clear delivery task",
                "budget_amount": "120",
                "budget_unit": "EC",
            },
            repeatable=True,
        ),
        FormalScenario(
            phase="P4",
            scenario_id="P4-order-accepted",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.order.accepted",
            title="positive evolution order accepted",
            payload_template={"order_id": "ORD-P4-POS-{sequence}", "requirement_id": "REQ-P4-POS-{sequence}", "worker_os_id": "{target_os_id}"},
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P4",
            scenario_id="P4-handover-delivered",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.order.handover.delivered",
            title="positive evolution handover delivered",
            payload_template={"order_id": "ORD-P4-POS-{sequence}", "handover_version": 1, "file_ref": "files://formal/p4/{sequence}"},
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P4",
            scenario_id="P4-handover-approved",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.order.handover.approved",
            title="positive evolution handover approved",
            payload_template={"order_id": "ORD-P4-POS-{sequence}", "handover_version": 1, "reviewer_os_id": "agent_client_low"},
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P4",
            scenario_id="P4-settlement-completed",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.settlement.completed",
            title="positive evolution settlement completed",
            payload_template={"settlement_id": "SET-P4-POS-{sequence}", "order_id": "ORD-P4-POS-{sequence}", "amount": "120"},
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P4",
            scenario_id="P4-reputation-increased",
            subject_template="poca.reputation",
            event_type="poca.reputation.increased",
            title="positive evolution reputation increased",
            payload_template={"os_id": "{target_os_id}", "delta": "0.03", "reason": "repeat_success_round_{sequence}"},
            repeatable=True,
        ),
        FormalScenario(
            phase="P5",
            scenario_id="P5-direct-inbox-interaction",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.chat.message.sent",
            title="multi-spirit direct inbox interaction",
            payload_template={
                "message_id": "MSG-P5-{sequence}",
                "from": "agent_peer_{sequence}",
                "from_os_name": "Peer Spirit {sequence}",
                "to": "{target_os_id}",
                "content": "Formal P5 multi-spirit interaction probe round {sequence}.",
                "channel": "formal_experiment",
            },
            repeatable=True,
            direct_inbox=True,
        ),
        FormalScenario(
            phase="P5",
            scenario_id="P5-market-broadcast",
            subject_template="mrk.requirement.published.broadcast",
            event_type="mrk.requirement.published.broadcast",
            title="multi-spirit shared market requirement",
            payload_template={
                "requirement_id": "REQ-P5-MARKET-{sequence}",
                "publisher_os_id": "agent_client_multi",
                "title": "Shared market task for multiple spirits",
                "description": "Observe whether the default spirit treats this as a shared opportunity.",
            },
            repeatable=True,
        ),
        FormalScenario(
            phase="P5",
            scenario_id="P5-order-feedback",
            subject_template="wsp.{target_os_id}",
            event_type="wsp.mrk.order.handover.rejected",
            title="multi-spirit order feedback",
            payload_template={
                "order_id": "ORD-P5-{sequence}",
                "requirement_id": "REQ-P5-MARKET-{sequence}",
                "reviewer_os_id": "agent_peer_{sequence}",
                "rejection_reason": "Peer requested clearer evidence before acceptance.",
            },
            repeatable=True,
            direct_inbox=True,
        ),
    ]


def selected_scenarios(phase: str) -> list[FormalScenario]:
    phase = phase.upper()
    phases = PHASES if phase == "ALL" else (phase,)
    if any(item not in PHASES for item in phases):
        raise ValueError("--phase must be one of P0|P1|P2|P3|P4|P5|all")
    catalog = _scenario_catalog()
    return [scenario for phase_name in phases for scenario in catalog if scenario.phase == phase_name]


def _format_payload(value: Any, placeholders: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _format_payload(item, placeholders) for key, item in value.items()}
    if isinstance(value, list):
        return [_format_payload(item, placeholders) for item in value]
    if isinstance(value, str):
        try:
            return value.format(**placeholders)
        except (KeyError, ValueError):
            return value
    return value


def expand_scenarios(
    *,
    phase: str,
    run_id: str,
    repeat: int,
    target_os_id: str = "",
    seed_id: str = "",
    persona: str = "",
    interval_seconds: float = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for scenario in selected_scenarios(phase):
        if scenario.direct_inbox and not target_os_id:
            item = {
                "phase": scenario.phase,
                "scenario_id": scenario.scenario_id,
                "code": "target_os_id_missing",
                "message": "Direct inbox scenario requires --target-os-id.",
                "status": "blocked",
            }
            if phase.upper() == "ALL":
                blocked.append(item)
                continue
            raise SystemExit(json.dumps(item, ensure_ascii=False))
        count = max(1, repeat if scenario.repeatable else 1)
        for sequence in range(1, count + 1):
            subject = scenario.subject_template.format(target_os_id=target_os_id)
            payload = dict(scenario.payload_template)
            payload.update(
                {
                    "run_id": run_id,
                    "phase": scenario.phase,
                    "scenario_id": scenario.scenario_id,
                    "sequence": sequence,
                    "seed_id": seed_id,
                    "persona": persona,
                    "published_at": utc_now_iso(),
                }
            )
            if target_os_id:
                payload["target_os_id"] = target_os_id
            if scenario.phase == "P4":
                payload["evolution_round"] = sequence
            payload = _format_payload(
                payload,
                {
                    "run_id": run_id,
                    "phase": scenario.phase,
                    "scenario_id": scenario.scenario_id,
                    "sequence": sequence,
                    "target_os_id": target_os_id,
                    "seed_id": seed_id,
                    "persona": persona,
                },
            )
            events.append(
                {
                    "run_id": run_id,
                    "phase": scenario.phase,
                    "scenario_id": f"{scenario.scenario_id}-{sequence:02d}" if count > 1 else scenario.scenario_id,
                    "base_scenario_id": scenario.scenario_id,
                    "sequence": sequence,
                    "subject": subject,
                    "event_type": scenario.event_type,
                    "payload": payload,
                    "title": scenario.title,
                    "interval_seconds": interval_seconds,
                }
            )
    return events, blocked


def validate_formal_event(subject: str, event_type: str) -> None:
    from agent.linz_world.event_catalog import is_formal_event

    if not is_formal_event(subject, event_type):
        raise ValueError(f"Event is not in formal Linz World catalog: {subject} {event_type}")


def _path_check(name: str, path: Path, *, kind: str = "file", required: bool = True) -> CheckResult:
    if kind == "dir":
        ok = path.is_dir()
    elif kind == "glob":
        ok = bool(list(path.parent.glob(path.name))) if path.parent.exists() else False
    else:
        ok = path.is_file()
    if ok or not required:
        return CheckResult(name, True, "ok", str(path))
    return CheckResult(name, False, f"Missing required {kind}: {path}", str(path), "Start gateway/os_runtime or verify --hermes-home.")


def run_prepare(args: argparse.Namespace) -> int:
    ctx = resolve_context(args.profile, args.hermes_home)
    checks: list[CheckResult] = []
    try:
        from agent.linz_world.status import status_summary

        status = status_summary(check_live=not args.no_live_check)
    except Exception as exc:
        status = {}
        checks.append(CheckResult("linz_status", False, f"Could not read Linz status: {exc}", next_action="Run hermes linz status."))

    if status:
        checks.extend(_linz_checks(status))
    checks.extend(_filesystem_checks(ctx.hermes_home))
    checks.append(_os_runtime_config_check())

    success = all(check.ok for check in checks)
    output = {
        "success": success,
        "profile": ctx.profile,
        "hermes_home": str(ctx.hermes_home),
        "phase": args.phase,
        "checked_at": utc_now_iso(),
        "checks": [check.to_dict() for check in checks],
        "next_action": "Run formal_experiment_run.sh only after all checks pass." if success else "Fix failed checks before publishing formal events.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if success else 2


def _linz_checks(status: dict[str, Any]) -> list[CheckResult]:
    gateway_state = str(status.get("gateway_state") or "")
    linz_state = str(status.get("gateway_linz_platform_state") or "")
    return [
        CheckResult(
            "linz_login",
            status.get("login_state") == "logged_in" and bool(status.get("login_verified") or status.get("identity", {}).get("compute_token_configured")),
            f"login_state={status.get('login_state')} login_verified={status.get('login_verified')}",
            next_action="Run hermes linz login.",
        ),
        CheckResult(
            "linz_authorization",
            status.get("authorization_state") == "current",
            f"authorization_state={status.get('authorization_state')}",
            next_action="Run hermes linz map.",
        ),
        CheckResult(
            "gateway_runtime",
            gateway_state in {"running", "ready", "online"},
            f"gateway_state={gateway_state or 'unknown'}",
            next_action="Start hermes gateway.",
        ),
        CheckResult(
            "linz_gateway_platform",
            bool(status.get("gateway_linz_platform_enabled")) and linz_state in {"online", "running", "ready", "connected"},
            f"enabled={status.get('gateway_linz_platform_enabled')} state={linz_state or 'unknown'} error={status.get('gateway_linz_platform_error') or ''}",
            next_action="Enable Linz World and restart hermes gateway.",
        ),
    ]


def _filesystem_checks(home: Path) -> list[CheckResult]:
    return [
        _path_check("gateway_message_events_db", home / "gateway" / "message_events.db"),
        _path_check("state_db", home / "state.db"),
        _path_check("linz_world_state", home / "linz_world" / "state.json"),
        _path_check("os_runtime_logs", home / "logs" / "os_runtime_*.log", kind="glob"),
    ]


def _os_runtime_config_check() -> CheckResult:
    try:
        from hermes_cli.os_runtime import load_runtime_config

        cfg = load_runtime_config()
        enabled = bool(cfg.enabled or cfg.autonomous.enabled or cfg.autonomous.start_with_gateway)
        return CheckResult(
            "os_runtime_config",
            enabled,
            f"enabled={cfg.enabled} autonomous.enabled={cfg.autonomous.enabled} start_with_gateway={cfg.autonomous.start_with_gateway}",
            next_action="Enable os_runtime in Hermes config before formal experiments.",
        )
    except Exception as exc:
        return CheckResult("os_runtime_config", False, f"Could not read os_runtime config: {exc}")


def run_experiment(args: argparse.Namespace) -> int:
    ctx = resolve_context(args.profile, args.hermes_home)
    events, blocked = expand_scenarios(
        phase=args.phase,
        run_id=args.run_id,
        repeat=args.repeat,
        target_os_id=args.target_os_id,
        seed_id=args.seed_id,
        persona=args.persona,
        interval_seconds=args.interval_seconds,
    )
    diagnostics: list[dict[str, Any]] = list(blocked)
    for event in events:
        try:
            validate_formal_event(event["subject"], event["event_type"])
        except ValueError as exc:
            diagnostics.append({"status": "blocked", "code": "catalog_rejected", "message": str(exc), **_event_brief(event)})

    if diagnostics and args.phase.upper() != "ALL":
        print(json.dumps({"success": False, "run_id": args.run_id, "results": diagnostics}, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    if args.dry_run:
        print(json.dumps({"success": True, "dry_run": True, "run_id": args.run_id, "events": [_dry_event(e) for e in events], "results": diagnostics}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    prepare_args = argparse.Namespace(profile=args.profile, hermes_home=args.hermes_home, phase=args.phase, no_live_check=args.no_live_check)
    prepare_code = run_prepare(prepare_args)
    if prepare_code != 0:
        return prepare_code

    from agent.linz_world.event_state import LinzStateRepository

    repo = LinzStateRepository(root=ctx.hermes_home / "linz_world", profile_id=ctx.profile)
    results = list(diagnostics)
    transport = str(getattr(args, "transport", "nats") or "nats")
    for index, event in enumerate(events, start=1):
        if any(item.get("scenario_id") == event["scenario_id"] and item.get("status") == "blocked" for item in diagnostics):
            continue
        if transport == "governed":
            from agent.linz_world.publisher import publish_event

            receipt = publish_event(
                event["subject"],
                event["event_type"],
                event["payload"],
                repository=repo,
                os_runtime_context={
                    "event_id": event["scenario_id"],
                    "session_id": f"formal:{args.run_id}",
                    "intent_id": f"formal-intent:{args.run_id}:{index}",
                },
            )
        else:
            receipt = _publish_event_direct_nats(
                event,
                repo,
                event_id=f"formal:{args.run_id}:{event['scenario_id']}:{uuid.uuid4().hex[:8]}",
            )
        status = getattr(receipt.status, "value", receipt.status)
        result = {
            **_event_brief(event),
            "status": status,
            "world_event_id": receipt.world_event_id,
            "request_id": receipt.request_id,
            "governance_code": receipt.governance_code,
            "message": receipt.message,
            "payload_summary": receipt.payload_summary,
        }
        results.append(result)
        if status not in {"published", "uncertain"}:
            print(json.dumps({"success": False, "run_id": args.run_id, "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
            return 3
        if event.get("interval_seconds") and index < len(events):
            time.sleep(float(event["interval_seconds"]))
    success = all(item.get("status") in {"published", "uncertain", "blocked"} for item in results)
    print(json.dumps({"success": success, "run_id": args.run_id, "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if success else 3


def _publish_event_direct_nats(event: dict[str, Any], repo: Any, *, event_id: str) -> Any:
    from agent.linz_world.config import load_linz_world_config
    from agent.linz_world.models import PublishReceipt, ReceiptStatus
    from agent.linz_world.nats_transport import publish_linz_event

    request_id = uuid.uuid4().hex
    try:
        result = publish_linz_event(
            nats_url=load_linz_world_config().nats_url,
            subject=event["subject"],
            event_type=event["event_type"],
            payload=event["payload"],
            event_id=event_id,
        )
        receipt = PublishReceipt(
            request_id=request_id,
            subject=event["subject"],
            event_type=event["event_type"],
            payload_summary=payload_summary(event["payload"]),
            status=ReceiptStatus.PUBLISHED,
            world_event_id=str(result.get("world_event_id") or result.get("event_id") or event_id),
            message=str(result.get("diagnostic") or "Published directly to NATS."),
            receipt={**result, "formal_transport": "direct_nats"},
        )
    except Exception as exc:
        receipt = PublishReceipt(
            request_id=request_id,
            subject=event["subject"],
            event_type=event["event_type"],
            payload_summary=payload_summary(event["payload"]),
            status=ReceiptStatus.FAILED,
            message=f"Direct NATS publish failed: {type(exc).__name__}: {exc}",
            receipt={"formal_transport": "direct_nats"},
        )
    # Direct NATS injection is intentionally out-of-band from governed Linz
    # publishing. Do not write this receipt into linz_world/state.json here:
    # the gateway listener may be persisting the consumed world event at the
    # same time, and that state file is not a transactional multi-writer store.
    return receipt


def _event_brief(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": event["run_id"],
        "phase": event["phase"],
        "scenario_id": event["scenario_id"],
        "subject": event["subject"],
        "event_type": event["event_type"],
        "sequence": event["sequence"],
        "audit_ref": audit_ref(event["payload"]),
    }


def _dry_event(event: dict[str, Any]) -> dict[str, Any]:
    return {**_event_brief(event), "payload_summary": payload_summary(event["payload"])}


def run_export(args: argparse.Namespace) -> int:
    ctx = resolve_context(args.profile, args.hermes_home)
    output_dir = Path(args.output_root).expanduser() / args.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    anomalies: list[dict[str, Any]] = []

    gateway_events = _read_gateway_events(ctx.hermes_home, args.run_id, args.since, args.until, anomalies)
    runtime_events = _read_os_runtime_events(ctx.hermes_home, args.run_id, args.since, args.until, anomalies)
    runtime_raw = _read_os_runtime_logs(ctx.hermes_home, args.run_id, args.since, args.until, anomalies)
    receipts = _read_linz_receipts(ctx.hermes_home, args.run_id, args.since, args.until, anomalies)
    transitions = _build_transitions(args.run_id, gateway_events, runtime_events, runtime_raw, anomalies)

    events_rows = [_export_event_row(args.run_id, item, receipts) for item in gateway_events]
    status_counts = _status_counts(events_rows, transitions, anomalies)
    manifest = {
        "run_id": args.run_id,
        "profile": ctx.profile,
        "hermes_home": str(ctx.hermes_home),
        "exported_at": utc_now_iso(),
        "since": args.since,
        "until": args.until,
        "source_paths": {
            "gateway": str(ctx.hermes_home / "gateway" / "message_events.db"),
            "state_db": str(ctx.hermes_home / "state.db"),
            "linz_state": str(ctx.hermes_home / "linz_world" / "state.json"),
            "os_runtime_logs": str(ctx.hermes_home / "logs" / "os_runtime_*.log"),
        },
        "counts": status_counts,
    }
    summary = {
        "run_id": args.run_id,
        "counts": status_counts,
        "phases": sorted({row.get("phase") for row in events_rows if row.get("phase")}),
        "published": status_counts["events"],
        "blocked": sum(1 for item in anomalies if item.get("status") == "blocked"),
        "anomaly": len(anomalies),
    }

    write_json(output_dir / "manifest.json", manifest)
    write_jsonl(output_dir / "events.jsonl", events_rows)
    write_jsonl(output_dir / "transitions.jsonl", transitions)
    write_jsonl(output_dir / "os_runtime_raw.jsonl", runtime_raw)
    _write_event_transition_markdown(output_dir / "event_transitions.md", events_rows)
    write_json(output_dir / "summary.json", summary)
    _write_summary_csv(output_dir / "summary.csv", summary)
    write_json(output_dir / "anomalies.json", anomalies)

    result = {"success": not (args.fail_on_anomaly and anomalies), "output_dir": str(output_dir), "counts": status_counts}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 4 if args.fail_on_anomaly and anomalies else 0


def _read_gateway_events(home: Path, run_id: str, since: str | None, until: str | None, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    db_path = home / "gateway" / "message_events.db"
    if not db_path.exists():
        anomalies.append(_anomaly("gateway_missing", run_id, f"Gateway projection DB not found: {db_path}"))
        return []
    try:
        from gateway.event_projection_store import EventProjectionStore

        store = EventProjectionStore(root=home)
        try:
            records = store.list_records(limit=500, q=run_id, from_time=since, to_time=until)["records"]
            return [store.get_record(row["record_id"]) or {"record": row, "projection": None, "transitions": []} for row in records]
        finally:
            store.close()
    except Exception as exc:
        anomalies.append(_anomaly("gateway_read_failed", run_id, str(exc)))
        return []


def _read_os_runtime_events(home: Path, run_id: str, since: str | None, until: str | None, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    db_path = home / "state.db"
    if not db_path.exists():
        anomalies.append(_anomaly("state_db_missing", run_id, f"state.db not found: {db_path}"))
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT event_id, event_type, source, trace_id, session_id, timestamp,
                       summary, metadata, content_ref, payload_hash, status
                FROM os_runtime_events
                WHERE (metadata LIKE ? OR summary LIKE ? OR trace_id LIKE ? OR session_id LIKE ?)
                ORDER BY timestamp ASC
                """,
                tuple([f"%{run_id}%"] * 4),
            ).fetchall()
        except sqlite3.Error as exc:
            anomalies.append(_anomaly("os_runtime_table_missing", run_id, f"os_runtime_events unavailable: {exc}"))
            return []
        out = []
        for row in rows:
            item = dict(row)
            if not in_window(item.get("timestamp"), since, until):
                continue
            item["metadata"] = _json_loads(item.get("metadata"), {})
            out.append(redact(item))
        return out
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _read_os_runtime_logs(home: Path, run_id: str, since: str | None, until: str | None, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    log_dir = home / "logs"
    rows: list[dict[str, Any]] = []
    if not log_dir.exists():
        anomalies.append(_anomaly("os_runtime_logs_missing", run_id, f"Log directory not found: {log_dir}"))
        return rows
    for path in sorted(log_dir.glob("os_runtime_*.log")):
        try:
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if run_id not in line:
                    continue
                data = _json_loads(line, {"message": line})
                timestamp = data.get("timestamp") or data.get("at") or data.get("created_at")
                if not in_window(str(timestamp or ""), since, until):
                    continue
                rows.append({"source_log": str(path), "line": line_no, **redact(data)})
        except OSError as exc:
            anomalies.append(_anomaly("os_runtime_log_read_failed", run_id, f"{path}: {exc}"))
    return rows


def _read_linz_receipts(home: Path, run_id: str, since: str | None, until: str | None, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = home / "linz_world" / "state.json"
    if not path.exists():
        anomalies.append(_anomaly("linz_state_missing", run_id, f"Linz state not found: {path}"))
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        anomalies.append(_anomaly("linz_state_read_failed", run_id, str(exc)))
        return []
    receipts = []
    for receipt in data.get("receipts") or []:
        text = json.dumps(receipt, ensure_ascii=False, default=str)
        if run_id not in text:
            continue
        if not in_window(str(receipt.get("recorded_at") or ""), since, until):
            continue
        receipts.append(redact(receipt))
    return receipts


def _build_transitions(
    run_id: str,
    gateway_events: list[dict[str, Any]],
    runtime_events: list[dict[str, Any]],
    runtime_raw: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for event in runtime_events:
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        merged = {**metadata, **event}
        row = {
            "run_id": run_id,
            "event_id": event.get("event_id"),
            "trace_id": event.get("trace_id"),
            "session_id": event.get("session_id"),
            "timestamp": event.get("timestamp"),
            "event_type": event.get("event_type"),
            "raw_transitions": metadata.get("transitions") or metadata.get("transition") or [],
            "life_state": merged.get("life_state"),
            "tension_field": merged.get("tension_field"),
            "tension_set": merged.get("tension_set"),
            "action_potential": merged.get("action_potential"),
            "self_prompt": merged.get("self_prompt"),
            "open_intent": merged.get("open_intent"),
            "arbitration": merged.get("arbitration"),
            "actual_action": merged.get("actual_action") or merged.get("action"),
            "evidence_refs": merged.get("evidence_refs") or merged.get("evidence") or [],
            "stop_reason": merged.get("stop_reason") or event.get("status"),
            "judgement": merged.get("judgement"),
            "anomaly": merged.get("anomaly"),
        }
        if _has_transition_signal(row):
            row["module_presence"] = _module_presence(row)
            row["missing_core_modules"] = _missing_core_modules(row)
            transitions.append(redact(row))

    raw_transitions = _build_transitions_from_runtime_raw(run_id, runtime_raw, anomalies)
    transitions.extend(raw_transitions)

    if gateway_events and not transitions:
        for item in gateway_events:
            record = item.get("record") or {}
            anomalies.append(_anomaly("missing_transition", run_id, "Gateway event has no matching os_runtime transition.", event_id=record.get("event_id") or record.get("record_id")))
    return transitions


def _build_transitions_from_runtime_raw(
    run_id: str,
    runtime_raw: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for raw in runtime_raw:
        if str(raw.get("route") or "").find("goal_event") == -1 and not raw.get("step"):
            continue
        group_key = _runtime_raw_group_key(raw)
        group = groups.setdefault(
            group_key,
            {
                "run_id": run_id,
                "event_id": "",
                "trace_id": raw.get("trace_id") or "",
                "session_id": raw.get("session_id") or "",
                "timestamp": raw.get("timestamp") or raw.get("at") or raw.get("created_at"),
                "event_type": "os_runtime_pipeline",
                "raw_transitions": [],
                "life_state": None,
                "tension_field": None,
                "tension_set": None,
                "action_potential": None,
                "self_prompt": None,
                "open_intent": None,
                "arbitration": None,
                "actual_action": None,
                "evidence_refs": [],
                "stop_reason": None,
                "judgement": None,
                "anomaly": None,
                "source_event_ids": [],
                "module_presence": {},
                "missing_core_modules": [],
                "pipeline_scope": "",
            },
        )
        if raw.get("timestamp") and (not group.get("timestamp") or str(raw["timestamp"]) < str(group["timestamp"])):
            group["timestamp"] = raw["timestamp"]
        group["trace_id"] = group.get("trace_id") or raw.get("trace_id") or ""
        group["session_id"] = group.get("session_id") or raw.get("session_id") or ""
        step = str(raw.get("step") or "").strip().lower()
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        group["raw_transitions"].append(_raw_pipeline_ref(raw, data))
        for event_id in _formal_causal_event_ids_from_step(step, data, run_id):
            if event_id not in group["source_event_ids"]:
                group["source_event_ids"].append(event_id)
        _merge_pipeline_step(group, step, data)

    transitions = []
    for key, row in groups.items():
        if not _has_transition_signal(row):
            anomalies.append(_anomaly("missing_transition", run_id, f"os_runtime raw log group {key} did not contain transition pipeline fields.", trace_id=row.get("trace_id"), session_id=row.get("session_id")))
            continue
        source_event_ids = list(row.get("source_event_ids") or [])
        row["event_id"] = source_event_ids[0] if source_event_ids else row.get("trace_id") or row.get("session_id") or key
        row["pipeline_scope"] = "formal_event" if source_event_ids else "runtime_session"
        row["module_presence"] = _module_presence(row)
        row["missing_core_modules"] = _missing_core_modules(row)
        if row["missing_core_modules"] and source_event_ids:
            anomalies.append(
                _anomaly(
                    "runtime_pipeline_incomplete",
                    run_id,
                    f"os_runtime raw log group {key} missing core modules: {', '.join(row['missing_core_modules'])}",
                    event_id=row.get("event_id"),
                    trace_id=row.get("trace_id"),
                    session_id=row.get("session_id"),
                )
            )
        transitions.append(redact(row))
    return transitions


def _runtime_raw_group_key(raw: dict[str, Any]) -> str:
    trace_id = str(raw.get("trace_id") or "").strip()
    if trace_id:
        return f"trace:{trace_id}"
    session_id = str(raw.get("session_id") or "").strip()
    if session_id:
        return f"session:{session_id}"
    return f"log:{raw.get('source_log', '')}:{raw.get('line', '')}"


def _raw_pipeline_ref(raw: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": raw.get("timestamp"),
        "source_log": raw.get("source_log"),
        "line": raw.get("line"),
        "phase": raw.get("phase"),
        "step": raw.get("step"),
        "step_index": raw.get("step_index"),
        "trace_id": raw.get("trace_id"),
        "session_id": raw.get("session_id"),
        "data_keys": sorted(str(key) for key in data.keys()),
    }


def _merge_pipeline_step(row: dict[str, Any], step: str, data: dict[str, Any]) -> None:
    if step == "life_state":
        row["life_state"] = data.get("life_state") or row.get("life_state")
    elif step == "tension_operation":
        row["tension_field"] = data.get("tension_field") or data.get("tension_interpretation") or row.get("tension_field")
    elif step == "tension_set":
        row["tension_set"] = data.get("tension_set") or row.get("tension_set")
        row["tension_field"] = row.get("tension_field") or data.get("tension_field") or data.get("tension_delta")
    elif step == "action_potential":
        row["action_potential"] = data.get("action_potential") or row.get("action_potential")
    elif step == "self_prompt":
        row["self_prompt"] = data.get("self_prompt") or row.get("self_prompt")
    elif step == "open_intent":
        row["open_intent"] = data.get("open_intent") or data.get("intent") or row.get("open_intent")
    elif step == "arbiter":
        row["arbitration"] = data.get("arbitration") or data.get("arbiter") or row.get("arbitration")
    elif step in {"action_execution", "actual_action"}:
        row["actual_action"] = data.get("actual_action") or data.get("action") or row.get("actual_action")
    elif step == "evidence_package":
        refs = data.get("evidence_refs") or data.get("evidence") or data.get("evidence_package") or []
        row["evidence_refs"] = refs if isinstance(refs, list) else [refs]

    row["actual_action"] = row.get("actual_action") or data.get("actual_action") or data.get("action")
    refs = data.get("evidence_refs")
    if refs:
        row["evidence_refs"] = refs if isinstance(refs, list) else [refs]
    row["stop_reason"] = row.get("stop_reason") or data.get("stop_reason")
    row["judgement"] = row.get("judgement") or data.get("judgement")
    row["anomaly"] = row.get("anomaly") or data.get("anomaly")


def _has_transition_signal(row: dict[str, Any]) -> bool:
    return any(
        row.get(field) not in (None, "", [])
        for field in RUNTIME_PIPELINE_FIELDS
    )


def _module_presence(row: dict[str, Any]) -> dict[str, bool]:
    return {field: row.get(field) not in (None, "", []) for field in RUNTIME_PIPELINE_FIELDS}


def _missing_core_modules(row: dict[str, Any]) -> list[str]:
    return [field for field in CORE_RUNTIME_PIPELINE_FIELDS if row.get(field) in (None, "", [])]


def _formal_causal_event_ids_from_step(step: str, data: dict[str, Any], run_id: str) -> list[str]:
    found: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and _is_formal_run_event_id(value, run_id) and value not in found:
            found.append(value)

    def add_event_ref(value: Any) -> None:
        if not isinstance(value, dict):
            return
        add(value.get("event_id"))
        add(value.get("trace_id"))
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        add(metadata.get("event_id"))

    add_event_ref(data.get("event_ref"))
    for event_ref in data.get("events") or []:
        add_event_ref(event_ref)
    wake = data.get("wake") if isinstance(data.get("wake"), dict) else {}
    add(wake.get("event_id"))
    interpretation = data.get("tension_interpretation") or data.get("tension_field")
    if isinstance(interpretation, dict):
        add(interpretation.get("event_id"))
    return found


def _is_formal_run_event_id(value: Any, run_id: str) -> bool:
    return isinstance(value, str) and value.startswith(f"formal:{run_id}:")


def _formal_event_ids_from_obj(value: Any, run_id: str) -> list[str]:
    prefix = f"formal:{run_id}:"
    found: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            if item.startswith(prefix) and item not in found:
                found.append(item)
            return
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def _export_event_row(run_id: str, item: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    record = item.get("record") or {}
    projection = item.get("projection") or {}
    raw_payload = record.get("raw_payload") if isinstance(record.get("raw_payload"), dict) else {}
    payload = raw_payload.get("payload") if isinstance(raw_payload.get("payload"), dict) else raw_payload
    return {
        "run_id": run_id,
        "phase": payload.get("phase") or _extract_from_summary(record.get("payload_summary"), "phase"),
        "scenario_id": payload.get("scenario_id") or _extract_from_summary(record.get("payload_summary"), "scenario_id"),
        "seed_id": payload.get("seed_id"),
        "persona": payload.get("persona"),
        "event_id": record.get("event_id"),
        "record_id": record.get("record_id"),
        "subject": record.get("subject"),
        "event_type": record.get("event_type"),
        "payload_summary": payload_summary(payload or record.get("payload_summary")),
        "raw_payload_ref": audit_ref(raw_payload or record.get("payload_summary")),
        "audit_ref": audit_ref(raw_payload or record.get("payload_summary")),
        "message_event_projection": projection,
        "gateway_transitions": item.get("transitions") or [],
        "gateway_transitions_markdown": _gateway_event_markdown(item),
        "linz_receipts": receipts,
        "consume_status": record.get("consume_status"),
        "projection_status": record.get("projection_status"),
        "judgement": None,
        "anomaly": None,
    }


def _gateway_event_markdown(item: dict[str, Any]) -> str:
    record = item.get("record") or {}
    raw_payload = record.get("raw_payload")
    if raw_payload is None:
        payload_text = str(record.get("raw_payload_error") or "Raw payload unavailable")
        payload_language = ""
    else:
        payload_text = _compact_json(raw_payload)
        payload_language = "json"

    sections = [
        f"# Raw inbound payload\n\n{_markdown_code_block(payload_text, payload_language)}",
    ]
    for transition in item.get("transitions") or []:
        title = (
            transition.get("reason")
            or transition.get("error")
            or transition.get("to_status")
            or f"transition-{transition.get('transition_id')}"
        )
        metadata = transition.get("metadata") if isinstance(transition.get("metadata"), dict) else {}
        sections.append(f"## {title}\n\n{_markdown_code_block(_compact_json(metadata), 'json')}")
    return "\n\n".join(section for section in sections if section)


def _write_event_transition_markdown(path: Path, events_rows: list[dict[str, Any]]) -> None:
    lines = ["# Formal Experiment Event Transitions", ""]
    for index, row in enumerate(events_rows, start=1):
        title = row.get("scenario_id") or row.get("event_id") or f"event-{index}"
        lines.extend(
            [
                f"## {index}. {row.get('phase') or 'unknown'} / {title}",
                "",
                f"- event_id: `{row.get('event_id') or ''}`",
                f"- subject: `{row.get('subject') or ''}`",
                f"- event_type: `{row.get('event_type') or ''}`",
                f"- consume_status: `{row.get('consume_status') or ''}`",
                f"- projection_status: `{row.get('projection_status') or ''}`",
                "",
                row.get("gateway_transitions_markdown") or "_No transitions recorded._",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _compact_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _markdown_code_block(value: str, language: str = "") -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`{3,}", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{value}\n{fence}"


def _extract_from_summary(summary: Any, key: str) -> Any:
    data = _json_loads(str(summary or ""), {})
    return data.get(key) if isinstance(data, dict) else None


def _json_loads(text: Any, default: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(str(text))
    except (TypeError, json.JSONDecodeError):
        return default


def _anomaly(code: str, run_id: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"run_id": run_id, "status": "anomaly", "code": code, "message": message, **extra}


def _status_counts(events: list[dict[str, Any]], transitions: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> dict[str, int]:
    return {"events": len(events), "transitions": len(transitions), "anomalies": len(anomalies)}


def _write_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run_id", "events", "transitions", "anomalies", "published", "blocked", "anomaly"])
        writer.writeheader()
        counts = summary["counts"]
        writer.writerow(
            {
                "run_id": summary["run_id"],
                "events": counts["events"],
                "transitions": counts["transitions"],
                "anomalies": counts["anomalies"],
                "published": summary["published"],
                "blocked": summary["blocked"],
                "anomaly": summary["anomaly"],
            }
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Formal Hermes/Linz World experiment helper")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="fail-closed formal experiment preflight")
    _add_common(prepare)
    prepare.add_argument("--phase", default="all", choices=[*PHASES, "all"])
    prepare.add_argument("--no-live-check", action="store_true", help="read cached Linz status without server validation")
    prepare.set_defaults(func=run_prepare)

    run = sub.add_parser("run", help="publish formal experiment events")
    _add_common(run)
    run.add_argument("--phase", default="P1", choices=[*PHASES, "all"])
    run.add_argument("--run-id", required=True)
    run.add_argument("--repeat", type=int, default=3)
    run.add_argument("--interval-seconds", type=float, default=0)
    run.add_argument("--target-os-id", default="")
    run.add_argument("--seed-id", default="")
    run.add_argument("--persona", default="")
    run.add_argument("--transport", choices=["nats", "governed"], default="nats")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--no-live-check", action="store_true", help="read cached Linz status during preflight")
    run.set_defaults(func=run_experiment)

    export = sub.add_parser("export", help="export persisted formal experiment artifacts")
    _add_common(export)
    export.add_argument("--run-id", required=True)
    export.add_argument("--output-root", default="experiment/results")
    export.add_argument("--since", default=None)
    export.add_argument("--until", default=None)
    export.add_argument("--fail-on-anomaly", action="store_true")
    export.set_defaults(func=run_export)
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default="default")
    parser.add_argument("--hermes-home", default=None)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
