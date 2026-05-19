#!/usr/bin/env python3
"""Run a two-spirit Linz World Bubble/MRK flow test and export a report."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|private[_-]?key|secret|token)",
    re.IGNORECASE,
)
SECRET_TEXT_RE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|"
    r"((?:api[_-]?key|authorization|password|private[_-]?key|secret|token)\s*[:=]\s*)"
    r"[^,\s}\]]+"
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_BLOCKED = "BLOCKED"
STATUS_SKIPPED = "SKIPPED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                output[str(key)] = "[REDACTED]"
            else:
                output[str(key)] = redact(item)
        return output
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_TEXT_RE.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", value)
    return value


def to_plain(value: Any) -> Any:
    try:
        from agent.linz_world.models import to_plain as linz_to_plain

        return linz_to_plain(value)
    except Exception:
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return value


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(data), ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(redact(row), ensure_ascii=False, sort_keys=True, default=str) + "\n")


def markdown_cell(value: Any, *, limit: int = 160) -> str:
    text = str(value if value is not None else "")
    text = SECRET_TEXT_RE.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", text)
    text = text.replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def bubble_id_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return text or uuid.uuid4().hex


def mounted_agent_bubble_id(actor: "ActorContext") -> str:
    source = actor.os_id or actor.profile
    if source.startswith(("agent_", "bub_agent_")):
        return source
    return f"agent_{bubble_id_part(source)}"


@contextmanager
def temporary_hermes_home(profile_dir: Path):
    old_home = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(profile_dir)
    try:
        yield
    finally:
        if old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = old_home


@dataclass
class ActorContext:
    role: str
    profile: str
    profile_dir: Path
    os_id: str = ""
    os_name: str = ""
    soul_id: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    linz_config: Any = None
    repo: Any = None
    identity: Any = None
    session: Any = None
    auth_map: Any = None
    dry_run: bool = False

    @property
    def label(self) -> str:
        return f"{self.role}:{self.profile}"


@dataclass
class FlowState:
    requirement_id: str = ""
    order_id: str = ""
    handover_id: str = ""
    settlement_id: str = ""
    demand_bubble_id: str = ""
    task_bubble_id: str = ""
    mount_id: str = ""
    artifact_ref: str = ""
    summary_ref: str = ""


class FlowReport:
    def __init__(self, output_dir: Path, *, run_id: str, command: list[str], dry_run: bool):
        self.output_dir = output_dir
        self.run_id = run_id
        self.command = command
        self.dry_run = dry_run
        self.started_at = utc_now_iso()
        self.finished_at = ""
        self.manifest: dict[str, Any] = {}
        self.steps: list[dict[str, Any]] = []
        self.receipts: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.anomalies: list[dict[str, Any]] = []

    def step(
        self,
        index: int,
        name: str,
        actor: ActorContext | None,
        fn: Callable[[], tuple[str, str, dict[str, Any], str]],
    ) -> tuple[str, dict[str, Any]]:
        started = time.perf_counter()
        started_at = utc_now_iso()
        status = STATUS_FAIL
        key_result = ""
        details: dict[str, Any] = {}
        error = ""
        try:
            status, key_result, details, error = fn()
        except Exception as exc:
            status = STATUS_FAIL
            error = f"{type(exc).__name__}: {exc}"
            details = {"exception_type": type(exc).__name__}
        duration_ms = int((time.perf_counter() - started) * 1000)
        row = {
            "index": index,
            "step": name,
            "actor_profile": actor.profile if actor else "",
            "actor_role": actor.role if actor else "",
            "actor_os_id": actor.os_id if actor else "",
            "status": status,
            "key_result": key_result,
            "error": error,
            "details": details,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "duration_ms": duration_ms,
        }
        self.steps.append(redact(row))
        if status in {STATUS_FAIL, STATUS_BLOCKED}:
            self.anomalies.append(
                redact(
                    {
                        "step": name,
                        "index": index,
                        "status": status,
                        "actor_profile": row["actor_profile"],
                        "actor_os_id": row["actor_os_id"],
                        "message": error or key_result,
                        "details": details,
                    }
                )
            )
        return status, details

    def add_receipt(self, actor: ActorContext, action: str, receipt: Any, *, source: str = "") -> None:
        self.receipts.append(
            redact(
                {
                    "run_id": self.run_id,
                    "actor_role": actor.role,
                    "actor_profile": actor.profile,
                    "actor_os_id": actor.os_id,
                    "action": action,
                    "source": source,
                    "receipt": to_plain(receipt),
                    "recorded_at": utc_now_iso(),
                }
            )
        )

    def add_snapshot(self, actor: ActorContext, bubble_id: str, snapshot: dict[str, Any], *, source: str = "") -> None:
        self.snapshots.append(
            redact(
                {
                    "run_id": self.run_id,
                    "actor_role": actor.role,
                    "actor_profile": actor.profile,
                    "actor_os_id": actor.os_id,
                    "bubble_id": bubble_id,
                    "source": source,
                    "snapshot": snapshot,
                    "recorded_at": utc_now_iso(),
                }
            )
        )

    def add_event_rows(self, actor: ActorContext, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.events.append(
                redact(
                    {
                        "run_id": self.run_id,
                        "actor_role": actor.role,
                        "actor_profile": actor.profile,
                        "actor_os_id": actor.os_id,
                        **row,
                    }
                )
            )

    def write(self, state: FlowState, publisher: ActorContext, receiver: ActorContext, *, args: argparse.Namespace) -> None:
        self.finished_at = utc_now_iso()
        counts = {
            STATUS_PASS: sum(1 for row in self.steps if row["status"] == STATUS_PASS),
            STATUS_FAIL: sum(1 for row in self.steps if row["status"] == STATUS_FAIL),
            STATUS_BLOCKED: sum(1 for row in self.steps if row["status"] == STATUS_BLOCKED),
            STATUS_SKIPPED: sum(1 for row in self.steps if row["status"] == STATUS_SKIPPED),
        }
        if self.dry_run:
            result = "DRY_RUN"
        elif counts[STATUS_FAIL]:
            result = STATUS_FAIL
        elif counts[STATUS_BLOCKED]:
            result = STATUS_BLOCKED
        else:
            result = STATUS_PASS

        summary = {
            "run_id": self.run_id,
            "result": result,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "counts": counts,
            "publisher_profile": publisher.profile,
            "publisher_os_id": publisher.os_id,
            "publisher_soul_id": publisher.soul_id,
            "receiver_profile": receiver.profile,
            "receiver_os_id": receiver.os_id,
            "receiver_soul_id": receiver.soul_id,
            "ids": state.__dict__,
            "report_path": str(self.output_dir / "REPORT.md"),
        }
        self.manifest = {
            "script": "scripts/linz_bubble_mrk_flow_test.py",
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "command": self.command,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "publisher": {
                "profile": publisher.profile,
                "profile_dir": str(publisher.profile_dir),
                "os_id": publisher.os_id,
                "os_name": publisher.os_name,
                "soul_id": publisher.soul_id,
            },
            "receiver": {
                "profile": receiver.profile,
                "profile_dir": str(receiver.profile_dir),
                "os_id": receiver.os_id,
                "os_name": receiver.os_name,
                "soul_id": receiver.soul_id,
            },
            "args": vars(args),
        }

        write_json(self.output_dir / "manifest.json", self.manifest)
        write_jsonl(self.output_dir / "steps.jsonl", self.steps)
        write_jsonl(self.output_dir / "receipts.jsonl", self.receipts)
        write_jsonl(self.output_dir / "snapshots.jsonl", self.snapshots)
        write_jsonl(self.output_dir / "events.jsonl", self.events)
        write_json(self.output_dir / "summary.json", summary)
        write_json(self.output_dir / "anomalies.json", self.anomalies)
        self._write_markdown_report(summary)

    def _write_markdown_report(self, summary: dict[str, Any]) -> None:
        lines: list[str] = []
        lines.append("# Bubble MRK Flow Test Report")
        lines.append("")
        lines.append(f"- Run ID: `{summary['run_id']}`")
        lines.append(f"- Publisher profile: `{summary['publisher_profile']}`")
        lines.append(f"- Receiver profile: `{summary['receiver_profile']}`")
        lines.append(f"- Publisher OS: `{summary['publisher_os_id']}`")
        lines.append(f"- Receiver OS: `{summary['receiver_os_id']}`")
        lines.append(f"- Started: `{summary['started_at']}`")
        lines.append(f"- Finished: `{summary['finished_at']}`")
        lines.append(f"- Result: `{summary['result']}`")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        for key, value in [
            ("Steps passed", summary["counts"][STATUS_PASS]),
            ("Steps failed", summary["counts"][STATUS_FAIL]),
            ("Steps blocked", summary["counts"][STATUS_BLOCKED]),
            ("Steps skipped", summary["counts"][STATUS_SKIPPED]),
            ("Demand bubble", summary["ids"].get("demand_bubble_id", "")),
            ("Task bubble", summary["ids"].get("task_bubble_id", "")),
            ("Mount", summary["ids"].get("mount_id", "")),
            ("Publisher profile", summary["publisher_profile"]),
            ("Receiver profile", summary["receiver_profile"]),
        ]:
            lines.append(f"| {markdown_cell(key)} | {markdown_cell(value)} |")
        lines.append("")
        lines.append("## Step Results")
        lines.append("")
        lines.append("| # | Step | Actor | Status | Duration | Key Result | Error |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for row in self.steps:
            actor = row.get("actor_profile") or "-"
            duration = f"{row.get('duration_ms', 0)} ms"
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(row.get("index")),
                        markdown_cell(row.get("step")),
                        markdown_cell(actor),
                        markdown_cell(row.get("status")),
                        markdown_cell(duration),
                        markdown_cell(row.get("key_result")),
                        markdown_cell(row.get("error")),
                    ]
                )
                + " |"
            )
        lines.append("")
        lines.append("## Receipts")
        lines.append("")
        lines.append(f"- Receipt rows: `{len(self.receipts)}`")
        lines.append("")
        lines.append("## Snapshots")
        lines.append("")
        lines.append(f"- Snapshot rows: `{len(self.snapshots)}`")
        lines.append("")
        lines.append("## Anomalies")
        lines.append("")
        if self.anomalies:
            for item in self.anomalies:
                lines.append(f"- `{markdown_cell(item.get('status'))}` step `{markdown_cell(item.get('step'))}`: {markdown_cell(item.get('message'))}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Reproduction Command")
        lines.append("")
        lines.append("```bash")
        lines.append(" ".join(self.command))
        lines.append("```")
        lines.append("")
        (self.output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def load_yaml_config(profile_dir: Path) -> dict[str, Any]:
    path = profile_dir / "config.yaml"
    if not path.exists():
        return {}
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def save_yaml_config(profile_dir: Path, config: dict[str, Any]) -> None:
    from utils import atomic_yaml_write

    atomic_yaml_write(profile_dir / "config.yaml", config, sort_keys=False)


def profile_identity_summary(profile_dir: Path, profile_name: str) -> dict[str, Any]:
    from agent.linz_world.event_state import LinzStateRepository

    repo = LinzStateRepository(root=profile_dir / "linz_world", profile_id=profile_name)
    identity = repo.get_identity()
    if not identity:
        return {}
    return {
        "profile": profile_name,
        "os_id": identity.os_id,
        "os_name": identity.os_name,
        "soul_id": identity.soul_id,
        "complete": identity.is_complete(),
    }


def resolve_profile_dir(profile_name: str) -> Path:
    from hermes_cli.profiles import get_profile_dir, normalize_profile_name, validate_profile_name

    canon = normalize_profile_name(profile_name)
    validate_profile_name(canon)
    return get_profile_dir(canon)


def profile_exists(profile_name: str) -> bool:
    try:
        from hermes_cli.profiles import profile_exists as exists

        return bool(exists(profile_name))
    except Exception:
        return resolve_profile_dir(profile_name).is_dir()


def list_profile_names() -> list[str]:
    from hermes_cli.profiles import list_profiles

    names = [str(profile.name) for profile in list_profiles()]
    return sorted(set(names), key=lambda item: (item != "default", item))


def safe_profile_name(raw: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "-", str(raw or "").strip().lower()).strip("-_")
    if not value or not re.match(r"^[a-z0-9]", value):
        value = f"profile-{value}" if value else "profile"
    return value[:64]


def configure_linz_profile(profile_dir: Path, *, agent_name: str, persona_seed: str) -> dict[str, Any]:
    from agent.linz_world.config import DEFAULT_LINZ_WORLD_NATS_URL, DEFAULT_LINZ_WORLD_SERVICE_URL

    config = load_yaml_config(profile_dir)
    linz = config.get("linz_world")
    if not isinstance(linz, dict):
        linz = {}
        config["linz_world"] = linz
    linz["enabled"] = True
    linz["identity_required_on_agent_load"] = True
    linz["service_url"] = str(linz.get("service_url") or DEFAULT_LINZ_WORLD_SERVICE_URL).strip()
    linz["nats_url"] = str(linz.get("nats_url") or DEFAULT_LINZ_WORLD_NATS_URL).strip()
    linz["os_name"] = agent_name
    linz["os_type"] = str(linz.get("os_type") or "USER").strip().upper() or "USER"
    if linz["os_type"] not in {"USER", "SEV", "GOV"}:
        linz["os_type"] = "USER"
    linz["runtime_type"] = str(linz.get("runtime_type") or "Hermes").strip() or "Hermes"
    linz["persona_seed"] = persona_seed
    linz.pop("server_url", None)
    linz.pop("compute_api_key_ref", None)
    linz.pop("type", None)

    try:
        from hermes_cli import setup as setup_mod

        setup_mod._apply_os_runtime_install_defaults(config)
        setup_mod._write_linz_persona_seed_to_soul(profile_dir, persona_seed)
    except Exception:
        pass

    save_yaml_config(profile_dir, config)
    return config


def create_receiver_profile(args: argparse.Namespace, report: FlowReport, receiver_profile: str) -> dict[str, Any]:
    from agent.linz_world import auth, identity
    from agent.linz_world.event_state import LinzStateRepository
    from agent.linz_world.models import LoginState
    from hermes_cli import profiles as profiles_mod

    if not args.clone_config_from_default:
        raise RuntimeError("Receiver profile creation requires clone_config_from_default=true.")

    if profile_exists(receiver_profile):
        path = profiles_mod.get_profile_dir(receiver_profile)
    else:
        path = profiles_mod.create_profile(
            receiver_profile,
            clone_from="default",
            clone_config=True,
            no_alias=True,
        )

    agent_name = args.receiver_agent_name or receiver_profile
    persona_seed = args.receiver_persona_seed or f"bubble MRK receiver {args.run_id} {uuid.uuid4().hex[:8]}"
    config = configure_linz_profile(path, agent_name=agent_name, persona_seed=persona_seed)
    repo = LinzStateRepository(root=path / "linz_world", profile_id=receiver_profile)

    with temporary_hermes_home(path):
        world_identity = identity.ensure_original_spirit_identity(repo, config=config)
        if not world_identity.is_complete():
            raise RuntimeError(world_identity.last_error or "Linz World identity registration failed.")
        session = auth.login(repo, config=config)
        if session.state != LoginState.LOGGED_IN:
            raise RuntimeError(session.last_error or "Linz World login failed after receiver registration.")

    report.add_receipt(
        ActorContext(
            role="receiver",
            profile=receiver_profile,
            profile_dir=path,
            os_id=world_identity.os_id,
            os_name=world_identity.os_name,
            soul_id=world_identity.soul_id,
        ),
        "profile.create_linz_world_spirit",
        {
            "profile": receiver_profile,
            "profile_dir": str(path),
            "identity": {
                "os_id": world_identity.os_id,
                "os_name": world_identity.os_name,
                "soul_id": world_identity.soul_id,
            },
            "login_state": session.state.value,
        },
        source="script",
    )
    return {"profile": receiver_profile, "path": str(path), "os_id": world_identity.os_id, "soul_id": world_identity.soul_id}


def build_actor(profile_name: str, role: str, *, dry_run: bool) -> ActorContext:
    if dry_run:
        profile_dir = Path(f"<dry-run:{profile_name}>")
        os_id = ""
        os_name = profile_name
        soul_id = ""
        config: dict[str, Any] = {}
        if profile_exists(profile_name):
            profile_dir = resolve_profile_dir(profile_name)
            config = load_yaml_config(profile_dir)
            summary = profile_identity_summary(profile_dir, profile_name)
            os_id = str(summary.get("os_id") or "")
            os_name = str(summary.get("os_name") or profile_name)
            soul_id = str(summary.get("soul_id") or "")
        digest = uuid.uuid5(uuid.NAMESPACE_DNS, profile_name).hex[:12]
        if not os_id:
            os_id = f"agent_{digest}"
        if not soul_id:
            soul_id = f"soul_{digest}"
        try:
            from agent.linz_world.config import load_linz_world_config

            linz_config = load_linz_world_config(config)
        except Exception:
            linz_config = None
        return ActorContext(
            role=role,
            profile=profile_name,
            profile_dir=profile_dir,
            os_id=os_id,
            os_name=os_name,
            soul_id=soul_id,
            config=config,
            linz_config=linz_config,
            dry_run=True,
        )

    from agent.linz_world import auth, identity
    from agent.linz_world.config import load_linz_world_config
    from agent.linz_world.event_state import LinzStateRepository

    profile_dir = resolve_profile_dir(profile_name)
    config = load_yaml_config(profile_dir)
    repo = LinzStateRepository(root=profile_dir / "linz_world", profile_id=profile_name)
    with temporary_hermes_home(profile_dir):
        world_identity = identity.ensure_original_spirit_identity(repo, config=config)
        session = auth.ensure_login_session(repo, config=config)
        auth_map = repo.get_auth_map()
    linz_config = load_linz_world_config(config)
    return ActorContext(
        role=role,
        profile=profile_name,
        profile_dir=profile_dir,
        os_id=world_identity.os_id,
        os_name=world_identity.os_name,
        soul_id=world_identity.soul_id,
        config=config,
        linz_config=linz_config,
        repo=repo,
        identity=world_identity,
        session=session,
        auth_map=auth_map,
        dry_run=dry_run,
    )


def select_profiles(args: argparse.Namespace, report: FlowReport) -> tuple[str, str]:
    publisher = args.publisher_profile or "default"
    receiver = args.receiver_profile

    if args.dry_run:
        if not receiver:
            receiver = "bubble-mrk-worker"
        return publisher, receiver

    names = list_profile_names()
    if publisher not in names:
        raise RuntimeError(f"Publisher profile '{publisher}' does not exist.")

    if receiver:
        if receiver == publisher:
            raise RuntimeError("Receiver profile must be different from publisher profile.")
        if not profile_exists(receiver):
            if not args.auto_create_receiver:
                raise RuntimeError(f"Receiver profile '{receiver}' does not exist and auto-create is disabled.")
            create_receiver_profile(args, report, receiver)
        return publisher, receiver

    candidates = [name for name in names if name != publisher]
    if candidates:
        return publisher, candidates[0]

    if not args.auto_create_receiver:
        raise RuntimeError("A second profile is required and auto-create is disabled.")
    receiver = safe_profile_name(f"bubble-mrk-receiver-{args.run_id}")
    create_receiver_profile(args, report, receiver)
    return publisher, receiver


def actor_ready_details(actor: ActorContext) -> tuple[bool, list[str], dict[str, Any]]:
    from agent.linz_world.models import AuthState, LoginState

    errors: list[str] = []
    if actor.dry_run:
        return True, [], {"dry_run": True}
    identity = actor.identity
    session = actor.session
    auth_map = actor.auth_map
    cfg = actor.linz_config
    if not identity or not identity.is_complete():
        errors.append(getattr(identity, "last_error", "") or "Linz World identity is incomplete.")
    if not session or session.state != LoginState.LOGGED_IN or not session.token_ref:
        errors.append(getattr(session, "last_error", "") or "Linz World login session is missing.")
    if not auth_map or auth_map.state != AuthState.CURRENT:
        errors.append(getattr(auth_map, "last_error", "") or "Linz World authorization map is not current.")
    if not cfg.enabled:
        errors.append("linz_world.enabled is false.")
    if not cfg.bubble.enabled:
        errors.append("linz_world.bubble.enabled is false.")
    if cfg.bubble.read_only or not cfg.bubble.allow_mutations:
        errors.append("Bubble mutations are disabled; set linz_world.bubble.read_only=false and allow_mutations=true.")
    details = {
        "profile": actor.profile,
        "profile_dir": str(actor.profile_dir),
        "os_id": actor.os_id,
        "os_name": actor.os_name,
        "soul_id": actor.soul_id,
        "login_state": session.state.value if session else "",
        "auth_state": auth_map.state.value if auth_map else "",
        "allowed_publish_subjects": list(getattr(auth_map, "allowed_publish_subjects", []) or []),
        "allowed_publish_event_types": list(getattr(auth_map, "allowed_publish_event_types", []) or []),
        "bubble": {
            "enabled": cfg.bubble.enabled,
            "read_only": cfg.bubble.read_only,
            "allow_mutations": cfg.bubble.allow_mutations,
            "require_approval_for_mutations": cfg.bubble.require_approval_for_mutations,
            "default_task_slot_id": cfg.bubble.default_task_slot_id,
        },
    }
    return not errors, errors, details


def publish_mrk_event(
    report: FlowReport,
    actor: ActorContext,
    subject: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[str, str, dict[str, Any], str]:
    from agent.linz_world.event_catalog import is_formal_event
    from agent.linz_world.publisher import publish_event

    if not is_formal_event(subject, event_type):
        return STATUS_FAIL, "formal event rejected locally", {"subject": subject, "event_type": event_type}, "Event is not in the formal catalog."
    if dry_run:
        receipt = {
            "status": "planned",
            "subject": subject,
            "event_type": event_type,
            "payload": payload,
            "world_event_id": f"dry_evt_{uuid.uuid4().hex[:12]}",
        }
        report.add_receipt(actor, f"publish:{event_type}", receipt, source="dry_run")
        return STATUS_PASS, f"planned {event_type}", {"receipt": receipt}, ""

    with temporary_hermes_home(actor.profile_dir):
        receipt = publish_event(subject, event_type, payload, repository=actor.repo)
    report.add_receipt(actor, f"publish:{event_type}", receipt, source="linz_publish")
    status = getattr(receipt, "status", "")
    status_value = getattr(status, "value", str(status))
    details = {"receipt": to_plain(receipt)}
    if status_value == "published":
        return STATUS_PASS, f"published {event_type}", details, ""
    if status_value == "rejected":
        return STATUS_BLOCKED, f"rejected {event_type}", details, getattr(receipt, "message", "") or getattr(receipt, "governance_code", "")
    return STATUS_FAIL, f"failed {event_type}", details, getattr(receipt, "message", "") or status_value


def bubble_tool_call(
    report: FlowReport,
    actor: ActorContext,
    tool_name: str,
    args: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[str, str, dict[str, Any], str]:
    if dry_run:
        fake = fake_bubble_tool_result(tool_name, args, actor)
        report.add_receipt(actor, tool_name, fake.get("receipt", fake), source="dry_run")
        if fake.get("snapshot"):
            report.add_snapshot(actor, str(fake.get("bubble_id") or args.get("bubble_id") or ""), fake["snapshot"], source=f"{tool_name}:dry_run")
        return STATUS_PASS, fake.get("key_result", f"planned {tool_name}"), {"output": fake}, ""

    from tools import linz_world_bubble_tools

    handler = getattr(linz_world_bubble_tools, tool_name)
    with temporary_hermes_home(actor.profile_dir):
        raw = handler(args)
    try:
        output = json.loads(raw)
    except json.JSONDecodeError:
        return STATUS_FAIL, f"{tool_name} returned non-JSON", {"raw": raw}, "Tool returned invalid JSON."

    receipt = output.get("receipt")
    if receipt:
        report.add_receipt(actor, tool_name, receipt, source="linz_bubble_tool")
    if output.get("snapshot"):
        report.add_snapshot(actor, str(output.get("bubble_id") or args.get("bubble_id") or ""), output["snapshot"], source=tool_name)

    if output.get("success") is True:
        key = extract_key_result(tool_name, output)
        return STATUS_PASS, key, {"output": output}, ""

    governance_code = str((receipt or {}).get("governance_code") or "")
    message = str((receipt or {}).get("message") or output.get("message") or "")
    status = STATUS_BLOCKED if governance_code else STATUS_FAIL
    return status, f"{tool_name} failed", {"output": output}, message or governance_code


def fake_bubble_tool_result(tool_name: str, args: dict[str, Any], actor: ActorContext) -> dict[str, Any]:
    base = {
        "success": True,
        "status": "planned",
        "receipt": {
            "action": tool_name.replace("linz_bubble_", "bubble."),
            "status": "planned",
            "bubble_id": args.get("bubble_id") or args.get("demand_bubble_id") or args.get("task_bubble_id") or "",
            "mount_id": args.get("mount_id") or "",
            "result_summary": "dry-run planned operation",
        },
    }
    if tool_name == "linz_bubble_create_demand":
        bubble_id = f"dry_demand_{uuid.uuid4().hex[:8]}"
        base["receipt"]["bubble_id"] = bubble_id
        base["key_result"] = f"demand {bubble_id}"
    elif tool_name == "linz_bubble_accept_demand":
        bubble_id = str(args.get("demand_bubble_id") or args.get("bubble_id") or f"dry_demand_{uuid.uuid4().hex[:8]}")
        base["receipt"]["bubble_id"] = bubble_id
        base["key_result"] = f"accepted {bubble_id}"
    elif tool_name == "linz_bubble_create_task":
        bubble_id = f"dry_task_{uuid.uuid4().hex[:8]}"
        base["receipt"]["bubble_id"] = bubble_id
        base["key_result"] = f"task {bubble_id}"
    elif tool_name == "linz_bubble_request_mount":
        mount_id = f"dry_mount_{uuid.uuid4().hex[:8]}"
        base["receipt"]["bubble_id"] = str(args.get("task_bubble_id") or "")
        base["receipt"]["target_bubble_id"] = actor.os_id
        base["receipt"]["mount_id"] = mount_id
        base["key_result"] = f"mount {mount_id}"
    elif tool_name == "linz_bubble_snapshot":
        bubble_id = str(args.get("bubble_id") or "dry_bubble")
        base = {
            "success": True,
            "bubble_id": bubble_id,
            "lifecycle_state": "dry_run",
            "snapshot": {
                "bubble": {"bubble_id": bubble_id, "bubble_type": "dry", "lifecycle_state": "dry_run"},
                "children": [],
                "mounts": [],
                "mounted_bubbles": [],
                "behavior_events": [],
                "relation_events": [],
                "residues": [],
                "memory_bubbles": [],
                "memory_records": [],
                "truncated": {"behavior_events": 0, "relation_events": 0, "residues": 0},
            },
            "key_result": f"snapshot {bubble_id}",
        }
    else:
        base["key_result"] = f"planned {tool_name}"
    return base


def extract_key_result(tool_name: str, output: dict[str, Any]) -> str:
    receipt = output.get("receipt") if isinstance(output.get("receipt"), dict) else {}
    bubble_id = str(receipt.get("bubble_id") or output.get("bubble_id") or "")
    mount_id = str(receipt.get("mount_id") or "")
    lifecycle = str(receipt.get("lifecycle_state") or output.get("lifecycle_state") or "")
    if tool_name == "linz_bubble_snapshot":
        return f"snapshot {output.get('bubble_id', '')} {output.get('lifecycle_state', '')}".strip()
    if mount_id:
        return f"{tool_name} mount={mount_id}"
    if bubble_id:
        return f"{tool_name} bubble={bubble_id} {lifecycle}".strip()
    return tool_name


def receipt_bubble_id(details: dict[str, Any]) -> str:
    output = details.get("output") if isinstance(details, dict) else {}
    receipt = output.get("receipt") if isinstance(output, dict) and isinstance(output.get("receipt"), dict) else {}
    return str(receipt.get("bubble_id") or output.get("bubble_id") or "")


def receipt_mount_id(details: dict[str, Any]) -> str:
    output = details.get("output") if isinstance(details, dict) else {}
    receipt = output.get("receipt") if isinstance(output, dict) and isinstance(output.get("receipt"), dict) else {}
    return str(receipt.get("mount_id") or "")


def snapshot_children(details: dict[str, Any]) -> list[dict[str, Any]]:
    output = details.get("output") if isinstance(details, dict) else {}
    snapshot = output.get("snapshot") if isinstance(output, dict) else {}
    children = snapshot.get("children") if isinstance(snapshot, dict) else []
    return [item for item in children if isinstance(item, dict)]


def find_nested_str(value: Any, *keys: str) -> str:
    wanted = {key.lower() for key in keys}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in wanted and str(item or "").strip():
                return str(item).strip()
        for item in value.values():
            found = find_nested_str(item, *keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_nested_str(item, *keys)
            if found:
                return found
    return ""


def collect_recent_events(actor: ActorContext, run_id: str) -> list[dict[str, Any]]:
    if actor.dry_run or actor.repo is None:
        return []
    rows = []
    try:
        for record in actor.repo.recent_events(limit=100):
            plain = to_plain(record)
            text = json.dumps(plain, ensure_ascii=False, sort_keys=True, default=str)
            if run_id in text:
                rows.append(plain)
    except Exception:
        return []
    return rows


def require_confirmed_mutations(args: argparse.Namespace) -> tuple[bool, str]:
    if args.dry_run:
        return True, ""
    if not args.confirm_mutations:
        return False, "Remote MRK/Bubble mutations require --confirm-mutations."
    return True, ""


def run_flow(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"bubble-mrk-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    args.run_id = run_id
    output_dir = Path(args.output_root).expanduser() / run_id
    report = FlowReport(output_dir, run_id=run_id, command=[Path(sys.executable).name, *sys.argv], dry_run=args.dry_run)
    state = FlowState(
        requirement_id=f"REQ-{run_id}",
        order_id=f"ORD-{run_id}",
        handover_id=f"HANDOVER-{run_id}",
        settlement_id=f"SET-{run_id}",
        artifact_ref=f"hermes-session://bubble-mrk-flow/{run_id}/artifact",
        summary_ref=f"hermes-session://bubble-mrk-flow/{run_id}/summary",
    )

    publisher_profile = args.publisher_profile
    receiver_profile = args.receiver_profile or ""

    def profile_step() -> tuple[str, str, dict[str, Any], str]:
        nonlocal publisher_profile, receiver_profile
        publisher_profile, receiver_profile = select_profiles(args, report)
        details = {
            "publisher_profile": publisher_profile,
            "receiver_profile": receiver_profile,
            "available_profiles": [] if args.dry_run else list_profile_names(),
        }
        return STATUS_PASS, f"{publisher_profile} -> {receiver_profile}", details, ""

    profile_status, _ = report.step(0, "profile discovery", None, profile_step)
    if profile_status != STATUS_PASS:
        publisher = ActorContext(role="publisher", profile=publisher_profile, profile_dir=Path(""))
        receiver = ActorContext(role="receiver", profile=receiver_profile or "", profile_dir=Path(""))
        report.write(state, publisher, receiver, args=args)
        print(str(output_dir / "REPORT.md"))
        return 1
    publisher = build_actor(publisher_profile, "publisher", dry_run=args.dry_run)
    receiver = build_actor(receiver_profile, "receiver", dry_run=args.dry_run)

    def preflight_step() -> tuple[str, str, dict[str, Any], str]:
        ok_confirm, confirm_error = require_confirmed_mutations(args)
        publisher_ok, publisher_errors, publisher_details = actor_ready_details(publisher)
        receiver_ok, receiver_errors, receiver_details = actor_ready_details(receiver)
        errors = []
        if not ok_confirm:
            errors.append(confirm_error)
        if publisher.profile == receiver.profile:
            errors.append("Publisher and receiver profiles must differ.")
        if publisher.os_id and receiver.os_id and publisher.os_id == receiver.os_id:
            errors.append("Publisher and receiver os_id must differ.")
        if publisher.soul_id and receiver.soul_id and publisher.soul_id == receiver.soul_id:
            errors.append("Publisher and receiver soul_id must differ.")
        errors.extend(f"publisher: {item}" for item in publisher_errors)
        errors.extend(f"receiver: {item}" for item in receiver_errors)
        details = {"publisher": publisher_details, "receiver": receiver_details}
        if errors:
            return STATUS_BLOCKED, "preflight blocked", details, "; ".join(errors)
        return STATUS_PASS, "preflight ready", details, ""

    preflight_status, _ = report.step(1, "preflight", None, preflight_step)
    if preflight_status == STATUS_BLOCKED and not args.dry_run:
        report.add_event_rows(publisher, collect_recent_events(publisher, run_id))
        report.add_event_rows(receiver, collect_recent_events(receiver, run_id))
        report.write(state, publisher, receiver, args=args)
        return 2

    requirement_payload = {
        "requirement_id": state.requirement_id,
        "publisher_os_id": publisher.os_id,
        "publisher_os_name": publisher.os_name or publisher.profile,
        "title": f"Bubble MRK flow test {run_id}",
        "description": "End-to-end Bubble Protocol MRK flow test generated by Hermes.",
        "budget_amount": "100",
        "budget_unit": "EC",
        "deadline_at": "2026-06-01T18:00:00+08:00",
        "run_id": run_id,
    }
    requirement_publish_status, requirement_publish_details = report.step(
        2,
        "publish requirement",
        publisher,
        lambda: publish_mrk_event(
            report,
            publisher,
            "mrk.requirement.published",
            "mrk.requirement.published",
            requirement_payload,
            dry_run=args.dry_run,
        ),
    )
    state.demand_bubble_id = find_nested_str(
        requirement_publish_details,
        "demand_bubble_id",
        "demandBubbleID",
        "bubble_id",
        "BubbleID",
    )

    def demand_step() -> tuple[str, str, dict[str, Any], str]:
        if requirement_publish_status != STATUS_PASS:
            return STATUS_BLOCKED, "requirement publish missing", {}, "Requirement event was not published; demand creation is blocked."
        if state.demand_bubble_id:
            status, key, details, error = bubble_tool_call(
                report,
                publisher,
                "linz_bubble_snapshot",
                {"bubble_id": state.demand_bubble_id},
                dry_run=args.dry_run,
            )
            return status, f"MRK bridge demand {state.demand_bubble_id}", details, error
        result = bubble_tool_call(
            report,
            publisher,
            "linz_bubble_create_demand",
            {
                "name": requirement_payload["title"],
                "goal": requirement_payload["description"],
                "publisher_os_id": publisher.os_id,
                "publisher_os_name": publisher.os_name or publisher.profile,
                "budget_amount": requirement_payload["budget_amount"],
                "priority": "normal",
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )
        status, key, details, error = result
        state.demand_bubble_id = receipt_bubble_id(details)
        return status, key, details, error

    demand_status, _ = report.step(3, "create or locate DemandBubble", publisher, demand_step)

    def demand_snapshot_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.demand_bubble_id:
            return STATUS_BLOCKED, "demand bubble missing", {}, "No demand_bubble_id is available."
        return bubble_tool_call(
            report,
            publisher,
            "linz_bubble_snapshot",
            {"bubble_id": state.demand_bubble_id},
            dry_run=args.dry_run,
        )

    report.step(4, "snapshot DemandBubble", publisher, demand_snapshot_step)

    order_payload = {
        "requirement_id": state.requirement_id,
        "order_id": state.order_id,
        "requester_os_id": publisher.os_id,
        "requester_os_name": publisher.os_name or publisher.profile,
        "worker_os_id": receiver.os_id,
        "worker_os_name": receiver.os_name or receiver.profile,
        "run_id": run_id,
    }
    order_publish_status, order_publish_details = report.step(
        5,
        "publish order accepted",
        receiver,
        lambda: publish_mrk_event(
            report,
            receiver,
            "mrk.order",
            "mrk.order.accepted",
            order_payload,
            dry_run=args.dry_run,
        ),
    )
    if not state.task_bubble_id:
        state.task_bubble_id = find_nested_str(
            order_publish_details,
            "task_bubble_id",
            "taskBubbleID",
            "task_id",
            "taskBubbleId",
        )

    def accept_step() -> tuple[str, str, dict[str, Any], str]:
        if order_publish_status != STATUS_PASS:
            return STATUS_BLOCKED, "order publish missing", {}, "Order accepted event was not published; demand acceptance is blocked."
        if not state.demand_bubble_id:
            return STATUS_BLOCKED, "demand bubble missing", {}, "No demand_bubble_id is available."
        return bubble_tool_call(
            report,
            receiver,
            "linz_bubble_accept_demand",
            {
                "demand_bubble_id": state.demand_bubble_id,
                "tech_lead_os_id": receiver.os_id,
                "tech_lead_os_name": receiver.os_name or receiver.profile,
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )

    report.step(6, "accept DemandBubble", receiver, accept_step)

    def locate_or_create_task_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.demand_bubble_id:
            return STATUS_BLOCKED, "demand bubble missing", {}, "No demand_bubble_id is available."
        snap_status, snap_key, snap_details, snap_error = bubble_tool_call(
            report,
            receiver,
            "linz_bubble_snapshot",
            {"bubble_id": state.demand_bubble_id},
            dry_run=args.dry_run,
        )
        if snap_status == STATUS_PASS:
            for child in snapshot_children(snap_details):
                bubble_id = str(child.get("bubble_id") or "")
                bubble_type = str(child.get("bubble_type") or "").lower()
                if bubble_id and ("task" in bubble_type or bubble_type == ""):
                    state.task_bubble_id = bubble_id
                    return STATUS_PASS, f"task found {bubble_id}", snap_details, ""
        create_status, create_key, create_details, create_error = bubble_tool_call(
            report,
            receiver,
            "linz_bubble_create_task",
            {
                "parent_bubble_id": state.demand_bubble_id,
                "name": f"Task for {state.requirement_id}",
                "goal": "Produce and submit the test artifact for the Bubble MRK flow.",
                "tech_lead_os_id": receiver.os_id,
                "acceptance": {"mode": "manual", "reviewer_os_id": publisher.os_id},
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )
        state.task_bubble_id = receipt_bubble_id(create_details)
        return create_status, create_key, create_details, create_error

    report.step(7, "locate or create TaskBubble", receiver, locate_or_create_task_step)

    def mount_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.task_bubble_id:
            return STATUS_BLOCKED, "task bubble missing", {}, "No task_bubble_id is available."
        status, key, details, error = bubble_tool_call(
            report,
            receiver,
            "linz_bubble_request_mount",
            {
                "task_bubble_id": state.task_bubble_id,
                "mounted_bubble_id": mounted_agent_bubble_id(receiver),
                "slot_id": "slot.task.coder",
                "relation_role": "worker",
                "requester_os_id": receiver.os_id,
                "request_note": f"MRK flow test mount for {run_id}",
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )
        state.mount_id = receipt_mount_id(details)
        return status, key, details, error

    report.step(8, "mount receiver AgentBubble", receiver, mount_step)

    def review_mount_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.mount_id:
            return STATUS_SKIPPED, "mount review skipped", {}, "No mount_id is available."
        return bubble_tool_call(
            report,
            publisher,
            "linz_bubble_review_mount",
            {
                "mount_id": state.mount_id,
                "reviewer_os_id": publisher.os_id,
                "approved": True,
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )

    report.step(9, "review mount", publisher, review_mount_step)

    def artifact_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.task_bubble_id or not state.mount_id:
            return STATUS_BLOCKED, "artifact blocked", {}, "task_bubble_id or mount_id is missing."
        return bubble_tool_call(
            report,
            receiver,
            "linz_bubble_submit_artifact",
            {
                "task_bubble_id": state.task_bubble_id,
                "mount_id": state.mount_id,
                "actor_os_id": receiver.os_id,
                "artifact_ref": state.artifact_ref,
                "delivery_note": f"Artifact submitted for {run_id}.",
                "evidence_refs": [str(output_dir / "steps.jsonl"), str(output_dir / "receipts.jsonl")],
                "known_issues": "",
                "next_action": "publisher_review",
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )

    report.step(10, "submit task artifact", receiver, artifact_step)

    handover_payload = {
        "handover_id": state.handover_id,
        "order_id": state.order_id,
        "requirement_id": state.requirement_id,
        "deliverer_os_id": receiver.os_id,
        "deliverer_os_name": receiver.os_name or receiver.profile,
        "handover_version": 1,
        "file_ref": state.artifact_ref,
        "checksum": "sha256:dry-run" if args.dry_run else f"sha256:{uuid.uuid5(uuid.NAMESPACE_URL, state.artifact_ref).hex}",
        "size": 1,
        "mime_type": "text/plain",
        "version": "v1",
        "run_id": run_id,
    }
    handover_publish_status, _ = report.step(
        11,
        "publish handover delivered",
        receiver,
        lambda: publish_mrk_event(
            report,
            receiver,
            "mrk.order.handover",
            "mrk.order.handover.delivered",
            handover_payload,
            dry_run=args.dry_run,
        ),
    )

    def task_acceptance_step() -> tuple[str, str, dict[str, Any], str]:
        if handover_publish_status != STATUS_PASS:
            return STATUS_BLOCKED, "handover publish missing", {}, "Handover delivered event was not published; task acceptance is blocked."
        if not state.task_bubble_id:
            return STATUS_BLOCKED, "task bubble missing", {}, "No task_bubble_id is available."
        return bubble_tool_call(
            report,
            publisher,
            "linz_bubble_review_task_acceptance",
            {
                "task_bubble_id": state.task_bubble_id,
                "reviewer_os_id": publisher.os_id,
                "approved": True,
                "reason": f"Accepted for {run_id}.",
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )

    report.step(12, "review TaskBubble acceptance", publisher, task_acceptance_step)

    def demand_delivery_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.demand_bubble_id:
            return STATUS_BLOCKED, "demand bubble missing", {}, "No demand_bubble_id is available."
        return bubble_tool_call(
            report,
            receiver,
            "linz_bubble_submit_demand_delivery",
            {
                "demand_bubble_id": state.demand_bubble_id,
                "tech_lead_os_id": receiver.os_id,
                "summary_ref": state.summary_ref,
                "summary_note": f"Demand delivery summary for {run_id}.",
                "evidence_refs": [state.artifact_ref],
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )

    report.step(13, "submit DemandBubble delivery", receiver, demand_delivery_step)

    def demand_acceptance_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.demand_bubble_id:
            return STATUS_BLOCKED, "demand bubble missing", {}, "No demand_bubble_id is available."
        return bubble_tool_call(
            report,
            publisher,
            "linz_bubble_review_demand_acceptance",
            {
                "demand_bubble_id": state.demand_bubble_id,
                "reviewer_os_id": publisher.os_id,
                "approved": True,
                "reason": f"Demand accepted for {run_id}.",
                "confirm_mutation": bool(args.confirm_mutations or args.dry_run),
            },
            dry_run=args.dry_run,
        )

    report.step(14, "review DemandBubble acceptance", publisher, demand_acceptance_step)

    if args.skip_settlement:
        report.step(15, "settlement observation", None, lambda: (STATUS_SKIPPED, "settlement skipped", {}, ""))
    else:
        settlement_payload = {
            "settlement_id": state.settlement_id,
            "order_id": state.order_id,
            "requirement_id": state.requirement_id,
            "amount": "100",
            "transfer_event_id": f"TRANSFER-{run_id}",
            "run_id": run_id,
        }
        report.step(
            15,
            "publish settlement requested",
            publisher,
            lambda: publish_mrk_event(
                report,
                publisher,
                "mrk.settlement",
                "mrk.settlement.requested",
                settlement_payload,
                dry_run=args.dry_run,
            ),
        )

    def final_snapshot_step() -> tuple[str, str, dict[str, Any], str]:
        if not state.demand_bubble_id:
            return STATUS_SKIPPED, "final snapshot skipped", {}, "No demand_bubble_id is available."
        return bubble_tool_call(
            report,
            publisher,
            "linz_bubble_snapshot",
            {"bubble_id": state.demand_bubble_id},
            dry_run=args.dry_run,
        )

    report.step(16, "final DemandBubble snapshot", publisher, final_snapshot_step)

    report.add_event_rows(publisher, collect_recent_events(publisher, run_id))
    report.add_event_rows(receiver, collect_recent_events(receiver, run_id))
    report.write(state, publisher, receiver, args=args)
    print(str(output_dir / "REPORT.md"))
    if args.dry_run:
        return 0
    return 1 if any(row["status"] in {STATUS_FAIL, STATUS_BLOCKED} for row in report.steps) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a two-profile Linz World Bubble/MRK flow test.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the Bubble/MRK flow test.")
    run.add_argument("--publisher-profile", default="default", help="Profile used as the requirement publisher.")
    run.add_argument("--receiver-profile", default="", help="Profile used as the requirement receiver.")
    run.add_argument("--auto-create-receiver", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--receiver-agent-name", default="", help="Agent name for an auto-created receiver spirit.")
    run.add_argument("--receiver-persona-seed", default="", help="Persona seed for an auto-created receiver spirit.")
    run.add_argument("--clone-config-from-default", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--hermes-home", default="", help="Optional HERMES_HOME override for the current/default profile.")
    run.add_argument("--run-id", default="", help="Run identifier used in payloads and output paths.")
    run.add_argument("--output-root", default="experiment/results", help="Root directory for exported reports.")
    run.add_argument("--confirm-mutations", action="store_true", help="Confirm remote MRK/Bubble state mutations.")
    run.add_argument("--dry-run", action="store_true", help="Plan and report the flow without remote side effects.")
    run.add_argument("--skip-settlement", action="store_true", help="Skip settlement event publication/observation.")
    run.add_argument("--timeout-seconds", type=int, default=120, help="Reserved for future polling waits.")
    run.add_argument("--poll-interval", type=float, default=3.0, help="Reserved for future polling waits.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.hermes_home:
        os.environ["HERMES_HOME"] = str(Path(args.hermes_home).expanduser().resolve())
    if args.command == "run":
        try:
            return run_flow(args)
        except Exception as exc:
            print(f"linz_bubble_mrk_flow_test failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
