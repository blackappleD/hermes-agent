#!/usr/bin/env python3
"""Run a two-spirit Linz World Bubble/MRK flow test and export a report."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
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


@dataclass
class GatewayHandle:
    actor: ActorContext
    process: subprocess.Popen | None
    log_path: Path
    started_by_script: bool = False
    log_handle: Any = None


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
        self.agent_runs: list[dict[str, Any]] = []
        self.gateway_records: list[dict[str, Any]] = []
        self.session_evidence: list[dict[str, Any]] = []
        self.observations: list[dict[str, Any]] = []
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

    def add_agent_run(self, actor: ActorContext, row: dict[str, Any]) -> None:
        self.agent_runs.append(
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

    def add_gateway_records(self, actor: ActorContext, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.gateway_records.append(
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

    def add_session_evidence(self, actor: ActorContext, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.session_evidence.append(
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

    def add_observation(self, row: dict[str, Any]) -> None:
        self.observations.append(redact({"run_id": self.run_id, "recorded_at": utc_now_iso(), **row}))

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
            "mode": str(getattr(args, "mode", args.command)),
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
            "script": "scripts/linz-world/linz_bubble_mrk_flow_test.py",
            "run_id": self.run_id,
            "mode": summary["mode"],
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
        write_jsonl(self.output_dir / "agent_runs.jsonl", self.agent_runs)
        write_jsonl(self.output_dir / "gateway_records.jsonl", self.gateway_records)
        write_jsonl(self.output_dir / "session_evidence.jsonl", self.session_evidence)
        write_jsonl(self.output_dir / "observations.jsonl", self.observations)
        write_json(self.output_dir / "summary.json", summary)
        write_json(self.output_dir / "anomalies.json", self.anomalies)
        self._write_markdown_report(summary)

    def _write_markdown_report(self, summary: dict[str, Any]) -> None:
        lines: list[str] = []
        lines.append("# Bubble MRK Flow Test Report")
        lines.append("")
        lines.append(f"- Run ID: `{summary['run_id']}`")
        lines.append(f"- Mode: `{summary.get('mode', '')}`")
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
        lines.append("## Real Runtime Evidence")
        lines.append("")
        lines.append(f"- Agent run rows: `{len(self.agent_runs)}`")
        lines.append(f"- Gateway record rows: `{len(self.gateway_records)}`")
        lines.append(f"- Session evidence rows: `{len(self.session_evidence)}`")
        lines.append(f"- Observation rows: `{len(self.observations)}`")
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


def fill_missing_config(target: dict[str, Any], source: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for key, value in source.items():
        if key == "linz_world":
            continue
        if key not in target:
            target[key] = value
            changes.append(key)
    return changes


def ensure_profile_clone_baseline(profile_dir: Path, source_dir: Path) -> dict[str, Any]:
    if profile_dir.resolve() == source_dir.resolve():
        return {"changed": False, "config_keys_added": [], "env_copied": False}

    result: dict[str, Any] = {"changed": False, "config_keys_added": [], "env_copied": False}
    source_config = load_yaml_config(source_dir)
    target_config = load_yaml_config(profile_dir)
    added = fill_missing_config(target_config, source_config)
    if added:
        save_yaml_config(profile_dir, target_config)
        result["changed"] = True
        result["config_keys_added"] = added

    source_env = source_dir / ".env"
    target_env = profile_dir / ".env"
    if source_env.exists() and not target_env.exists():
        shutil.copy2(source_env, target_env)
        result["changed"] = True
        result["env_copied"] = True
    return result


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


def gateway_status(actor: ActorContext, *, check_live: bool = True) -> dict[str, Any]:
    if actor.dry_run:
        return {"gateway_state": "dry_run", "gateway_linz_platform_state": "dry_run"}
    from agent.linz_world.status import status_summary

    with temporary_hermes_home(actor.profile_dir):
        return status_summary(check_live=check_live)


def is_linz_gateway_online(status: dict[str, Any]) -> bool:
    gateway_state = str(status.get("gateway_state") or "").lower()
    platform_state = str(status.get("gateway_linz_platform_state") or "").lower()
    listener_state = str(status.get("listener_state") or "").lower()
    if listener_state and listener_state not in {"connected", "online", "ready", "running"}:
        return False
    return gateway_state in {"running", "ready", "online"} and platform_state in {
        "connected",
        "online",
        "ready",
        "running",
    }


def sanitized_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "profile"


def start_gateway_for_actor(actor: ActorContext, output_dir: Path, *, replace: bool) -> GatewayHandle:
    log_path = output_dir / f"gateway-{sanitized_filename(actor.profile)}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    command = [sys.executable, "-m", "hermes_cli.main", "gateway", "run", "--accept-hooks"]
    if replace:
        command.append("--replace")
    env = os.environ.copy()
    env["HERMES_HOME"] = str(actor.profile_dir)
    env.setdefault("HERMES_ACCEPT_HOOKS", "1")
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return GatewayHandle(actor=actor, process=process, log_path=log_path, started_by_script=True, log_handle=log_handle)


def stop_gateway_handle(handle: GatewayHandle) -> None:
    proc = handle.process
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    if handle.log_handle is not None:
        try:
            handle.log_handle.close()
        except Exception:
            pass


def ensure_gateway_ready(
    report: FlowReport,
    actor: ActorContext,
    output_dir: Path,
    *,
    start_missing: bool,
    start_timeout_seconds: int,
    poll_interval: float,
) -> tuple[str, str, dict[str, Any], str, GatewayHandle | None]:
    status = gateway_status(actor, check_live=True)
    if is_linz_gateway_online(status):
        return STATUS_PASS, "gateway already online", {"status": status, "started": False}, "", None
    if not start_missing:
        return STATUS_BLOCKED, "gateway offline", {"status": status, "started": False}, "Gateway is not online and start_missing is false.", None

    handle = start_gateway_for_actor(actor, output_dir, replace=True)
    deadline = time.monotonic() + max(5, int(start_timeout_seconds))
    last_status = status
    while time.monotonic() < deadline:
        if handle.process and handle.process.poll() is not None:
            return (
                STATUS_FAIL,
                "gateway process exited",
                {
                    "status": last_status,
                    "started": True,
                    "exit_code": handle.process.returncode,
                    "log_path": str(handle.log_path),
                },
                f"Gateway exited with code {handle.process.returncode}.",
                handle,
            )
        time.sleep(max(0.5, poll_interval))
        last_status = gateway_status(actor, check_live=False)
        if is_linz_gateway_online(last_status):
            return (
                STATUS_PASS,
                "gateway started",
                {"status": last_status, "started": True, "log_path": str(handle.log_path)},
                "",
                handle,
            )
    return (
        STATUS_BLOCKED,
        "gateway start timed out",
        {"status": last_status, "started": True, "log_path": str(handle.log_path)},
        "Linz World gateway did not become online before timeout.",
        handle,
    )


def concrete_requirement_content(run_id: str) -> tuple[str, str]:
    title = f"开发 JSONL 事件统计脚本 {run_id}"
    description = (
        "请开发一个 Python 脚本 `linz_event_summary.py`，用于统计 Linz/Hermes JSONL 事件日志。"
        "功能要求：1. 支持 CLI 参数 `--input <path>` 和可选 `--output <path>`；"
        "2. 逐行读取 JSONL，跳过空行，非法 JSON 行计入 `invalid_lines`；"
        "3. 按 `event_type` 和 `subject` 分别统计数量；"
        "4. 输出 JSON 必须包含 `total_lines`、`valid_events`、`invalid_lines`、"
        "`by_event_type`、`by_subject`；"
        "5. 在交付说明中给出示例输入和运行方式。"
        "交付物必须包含完整脚本源码和简短说明；如果无法上传文件，请把完整代码和说明作为 artifact 内容提交。"
    )
    return title, description


def build_real_publisher_prompt(state: FlowState, publisher: ActorContext, receiver: ActorContext, run_id: str) -> str:
    requirement_title, requirement_description = concrete_requirement_content(run_id)
    return f"""你是 Linz World 上的需求发布方元神 `{publisher.os_name or publisher.profile}`。

这是一个真实 MRK/Bubble 协作流程测试。请你只代表自己在 Linz 平台上真实提交一个新需求，让其他元神通过 Linz World 事件/gateway 自主接收和处理。

硬性约束：
- 这是非交互测试，不要询问澄清问题。
- 必须实际调用 Linz World 工具，不要只文字说明完成。
- 远端变更由你这个元神通过工具完成；测试脚本不会替你调用任何 mutating Bubble 工具。
- 如果调用需要确认的 Bubble mutation 工具，必须显式传 `confirm_mutation: true`。
- 只完成“发布正式 MRK 需求事件”这一步，不要冒充接收方、交付方或验收方。
- 不要额外直接调用 `linz_bubble_create_demand` 创建独立 DemandBubble；Linz World MRK 模块会在处理 `mrk.requirement.published` 后桥接生成对应 DemandBubble。
- 需求和所有 payload 必须包含 run_id: `{run_id}`，便于审计。

请发布/创建的需求：
- requirement_id: `{state.requirement_id}`
- title: `{requirement_title}`
- description:
  {requirement_description}
- budget_amount: `100`
- budget_unit: `EC`
- deadline_at: `2026-06-01T18:00:00+08:00`
- publisher_os_id: `{publisher.os_id}`
- publisher_os_name: `{publisher.os_name or publisher.profile}`
- target_os_id: `{receiver.os_id}`
- target_os_name: `{receiver.os_name or receiver.profile}`

必须发布原始 MRK 需求事件：subject=`mrk.requirement.published`, event_type=`mrk.requirement.published`。
传给 `linz_publish` 的 payload 必须逐字使用下面这些键名，禁止把 `title` 改成 `name`，禁止把 `description` 改成 `goal`：
```json
{{
  "requirement_id": "{state.requirement_id}",
  "publisher_os_id": "{publisher.os_id}",
  "publisher_os_name": "{publisher.os_name or publisher.profile}",
  "target_os_id": "{receiver.os_id}",
  "target_os_name": "{receiver.os_name or receiver.profile}",
  "title": "{requirement_title}",
  "description": "{requirement_description}",
  "budget_amount": "100",
  "budget_unit": "EC",
  "deadline_at": "2026-06-01T18:00:00+08:00",
  "run_id": "{run_id}"
}}
```
不要手动发布 `mrk.requirement.published.broadcast` 或 `wsp.mrk.requirement.published`；这些派生通知必须由 Linz World MRK 模块落库后生成。

完成后只输出一个简短 JSON 摘要，包含你实际调用的工具、receipt 状态、requirement_id、world_event_id。"""


def build_real_receiver_prompt(
    state: FlowState,
    publisher: ActorContext,
    receiver: ActorContext,
    run_id: str,
    artifact_path: Path,
) -> str:
    requirement_title, requirement_description = concrete_requirement_content(run_id)
    task_bubble_id = expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id)
    accept_args = {
        "demand_bubble_id": state.requirement_id,
        "requirement_id": state.requirement_id,
        "order_id": state.order_id,
        "requester_os_id": publisher.os_id,
        "requester_os_name": publisher.os_name or publisher.profile,
        "worker_os_id": receiver.os_id,
        "worker_os_name": receiver.os_name or receiver.profile,
        "confirm_mutation": True,
    }
    artifact_args = {
        "task_bubble_id": task_bubble_id,
        "mount_id": f"mrk-default-mount-{run_id}",
        "requirement_id": state.requirement_id,
        "order_id": state.order_id,
        "handover_version": 1,
        "deliverer_os_id": receiver.os_id,
        "deliverer_os_name": receiver.os_name or receiver.profile,
        "artifact_ref": state.artifact_ref,
        "file_name": "linz_event_summary.py",
        "mime_type": "text/x-python",
        "language": "python",
        "artifact_version": "v1",
        "delivery_note": (
            f"已实现 {requirement_title}。脚本路径/引用：{state.artifact_ref}。"
            "支持 --input 与可选 --output，输出 total_lines、valid_events、invalid_lines、by_event_type、by_subject。"
        ),
        "evidence_refs": [state.artifact_ref],
        "confirm_mutation": True,
    }
    return f"""你是 Linz World 上的需求接收方元神 `{receiver.os_name or receiver.profile}`。你刚通过 gateway 收到了一个定向 MRK 需求。

这是一个真实 MRK/Bubble 协作流程测试。请代表接收方真实处理需求，不要只文字回复。

需求：
- requirement_id: `{state.requirement_id}`
- title: `{requirement_title}`
- description: {requirement_description}
- 发布方 os_id/name: `{publisher.os_id}` / `{publisher.os_name or publisher.profile}`
- 接收方 os_id/name: `{receiver.os_id}` / `{receiver.os_name or receiver.profile}`
- 预期 MRK 默认 TaskBubble: `{task_bubble_id}`
- 本次 run_id: `{run_id}`

必须按顺序完成：
1. 用 `terminal` 或 `write_file` 在 `{artifact_path}` 创建真实脚本 `linz_event_summary.py`。脚本必须能直接运行，支持 `--input` 和可选 `--output`，逐行读取 JSONL，跳过空行，非法 JSON 计入 `invalid_lines`，分别统计 `event_type` 和 `subject`，输出 JSON 字段 `total_lines`、`valid_events`、`invalid_lines`、`by_event_type`、`by_subject`。
2. 调用 `linz_bubble_accept_demand` 正式接单。必须使用下面参数，不要改字段名：
```json
{json.dumps(accept_args, ensure_ascii=False, indent=2)}
```
3. 调用 `linz_bubble_submit_artifact` 正式交付。必须提供 requirement_id 和 order_id，使工具发布 `mrk.order.handover.delivered`，不要绕过 MRK。参数使用：
```json
{json.dumps(artifact_args, ensure_ascii=False, indent=2)}
```

硬性约束：
- 不要手动发布任何 `wsp.*` 派生事件。
- 不要调用 `linz_bubble_create_task`、`linz_bubble_request_mount` 或 `linz_bubble_review_mount` 来替代正式 MRK 接单；`mrk.order.accepted` 会由 Linz World 桥接默认 TaskBubble。
- 所有远端 mutation 工具必须传 `confirm_mutation: true`。
- 完成后只输出简短 JSON，包含写入的文件路径、调用过的 Linz 工具、requirement_id、order_id、artifact_ref。"""


def build_real_publisher_task_acceptance_prompt(
    state: FlowState,
    publisher: ActorContext,
    receiver: ActorContext,
    run_id: str,
) -> str:
    task_bubble_id = expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id)
    review_args = {
        "task_bubble_id": task_bubble_id,
        "requirement_id": state.requirement_id,
        "order_id": state.order_id,
        "handover_version": 1,
        "reviewer_os_id": publisher.os_id,
        "reviewer_os_name": publisher.os_name or publisher.profile,
        "approved": True,
        "reason": f"验收通过：接收方已交付 linz_event_summary.py，run_id={run_id}。",
        "confirm_mutation": True,
    }
    return f"""你是 Linz World 上的需求发布方元神 `{publisher.os_name or publisher.profile}`。接收方 `{receiver.os_name or receiver.profile}` 已提交 MRK handover。

请真实验收接收方的任务交付。必须调用 `linz_bubble_review_task_acceptance`，并提供 requirement_id 和 order_id，使工具发布正式 `mrk.order.handover.approved` 事件。

必须使用下面参数：
```json
{json.dumps(review_args, ensure_ascii=False, indent=2)}
```

硬性约束：
- 不要手动发布任何 `wsp.*` 派生事件。
- 不要只文字说明完成，必须实际调用工具。
- 完成后只输出简短 JSON，包含调用工具、requirement_id、order_id、approved。"""


def build_real_publisher_bubble_task_acceptance_prompt(
    state: FlowState,
    publisher: ActorContext,
    run_id: str,
    task_bubble_ids: list[str],
) -> str:
    calls = [
        {
            "task_bubble_id": task_id,
            "reviewer_os_id": publisher.os_id,
            "approved": True,
            "reason": (
                "直接 Bubble 验收 reviewing TaskBubble；正式 mrk.order.handover.approved "
                f"已先发布，run_id={run_id}。"
            ),
            "confirm_mutation": True,
        }
        for task_id in task_bubble_ids
    ]
    return f"""你是 Linz World 上的需求发布方元神 `{publisher.os_name or publisher.profile}`。你已经发布正式 `mrk.order.handover.approved`。

根据当前 Linz World 后端实现，`backend/internal/modules/mrk/module.go` 目前订阅 `mrk.order.handover.submitted/delivered`，但没有订阅 `mrk.order.handover.approved` 的 Bubble 桥接；因此正式 approval 事件发布后，TaskBubble 可能仍停在 reviewing。现在请你用真实 Bubble 任务验收工具归档这些 reviewing TaskBubble。

必须对下面每个参数对象调用一次 `linz_bubble_review_task_acceptance`。注意：这些调用不要传 requirement_id/order_id，避免再次走 formal MRK publish 分支；这里要走直接 Bubble 任务验收分支。
```json
{json.dumps(calls, ensure_ascii=False, indent=2)}
```

硬性约束：
- 不要手动发布任何 `wsp.*` 派生事件。
- 不要只文字说明完成，必须实际调用工具。
- 完成后只输出简短 JSON，列出 task_bubble_id、调用工具和 approved=true。"""


def build_real_receiver_demand_delivery_prompt(
    state: FlowState,
    receiver: ActorContext,
    run_id: str,
) -> str:
    delivery_args = {
        "demand_bubble_id": state.requirement_id,
        "tech_lead_os_id": receiver.os_id,
        "summary_ref": state.summary_ref,
        "summary_note": (
            f"需求 {state.requirement_id} 已完成。交付物为 linz_event_summary.py，"
            f"artifact_ref={state.artifact_ref}，run_id={run_id}。"
        ),
        "evidence_refs": [state.artifact_ref],
        "confirm_mutation": True,
    }
    return f"""你是 Linz World 上的需求接收方元神 `{receiver.os_name or receiver.profile}`。发布方已经验收了 TaskBubble 交付。

请提交 DemandBubble 交付摘要，让需求进入最终验收。必须调用 `linz_bubble_submit_demand_delivery`。

必须使用下面参数：
```json
{json.dumps(delivery_args, ensure_ascii=False, indent=2)}
```

硬性约束：
- 不要手动发布任何 `wsp.*` 派生事件。
- 不要只文字说明完成，必须实际调用工具。
- 完成后只输出简短 JSON，包含调用工具、demand_bubble_id、summary_ref。"""


def build_real_publisher_demand_acceptance_prompt(
    state: FlowState,
    publisher: ActorContext,
    run_id: str,
) -> str:
    acceptance_args = {
        "demand_bubble_id": state.requirement_id,
        "reviewer_os_id": publisher.os_id,
        "approved": True,
        "reason": f"需求验收通过：脚本交付和交付摘要均已完成，run_id={run_id}。",
        "confirm_mutation": True,
    }
    return f"""你是 Linz World 上的需求发布方元神 `{publisher.os_name or publisher.profile}`。接收方已经提交 DemandBubble 交付摘要。

请真实完成需求最终验收并归档 DemandBubble。必须调用 `linz_bubble_review_demand_acceptance`。

必须使用下面参数：
```json
{json.dumps(acceptance_args, ensure_ascii=False, indent=2)}
```

硬性约束：
- 不要手动发布任何 `wsp.*` 派生事件。
- 不要只文字说明完成，必须实际调用工具。
- 完成后只输出简短 JSON，包含调用工具、demand_bubble_id、approved。"""


def run_agent_oneshot(
    report: FlowReport,
    actor: ActorContext,
    prompt: str,
    output_dir: Path,
    *,
    timeout_seconds: int,
    toolsets: str = "linz_world,linz_bubble",
) -> tuple[str, str, dict[str, Any], str]:
    prompt_path = output_dir / f"external-input-{sanitized_filename(actor.profile)}.txt"
    stdout_path = output_dir / f"agent-{sanitized_filename(actor.profile)}-stdout.txt"
    stderr_path = output_dir / f"agent-{sanitized_filename(actor.profile)}-stderr.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "hermes_cli.main",
        "--toolsets",
        toolsets,
        "--oneshot",
        prompt,
    ]
    env = os.environ.copy()
    env["HERMES_HOME"] = str(actor.profile_dir)
    env.setdefault("HERMES_ACCEPT_HOOKS", "1")
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=max(30, timeout_seconds),
        )
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        duration_ms = int((time.perf_counter() - started) * 1000)
        row = {
            "kind": "external_prompt",
            "command": [Path(command[0]).name, *command[1:4], "<prompt>"],
            "prompt_path": str(prompt_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "toolsets": toolsets,
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "stdout_preview": (completed.stdout or "")[:1200],
            "stderr_preview": (completed.stderr or "")[:1200],
        }
        report.add_agent_run(actor, row)
        if completed.returncode == 0:
            return STATUS_PASS, f"{actor.role} agent accepted external input", row, ""
        return STATUS_FAIL, f"{actor.role} agent failed", row, f"Agent exited with code {completed.returncode}."
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        row = {
            "kind": "external_prompt",
            "prompt_path": str(prompt_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "timeout_seconds": timeout_seconds,
        }
        report.add_agent_run(actor, row)
        return STATUS_FAIL, f"{actor.role} agent timed out", row, f"Agent did not finish within {timeout_seconds}s."


def collect_gateway_records(profile_dir: Path, run_id: str) -> list[dict[str, Any]]:
    try:
        from gateway.event_projection_store import EventProjectionStore

        store = EventProjectionStore(root=profile_dir)
        try:
            listed = store.list_records(limit=500, q=run_id)
            rows = []
            for record in listed.get("records") or []:
                full = store.get_record(str(record.get("record_id") or "")) or {"record": record}
                rows.append(full)
            return rows
        finally:
            store.close()
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}: {exc}", "record": {"consume_status": "read_failed"}}]


BUBBLE_ID_RE = re.compile(r"\b(?:(?:bub_demand|bub_task)_[A-Za-z0-9_.:-]+|(?:task_REQ|REQ)-[A-Za-z0-9_.:-]+)\b")


def sanitize_bubble_id_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")


def expected_mrk_task_bubble_id(requirement_id: str, worker_os_id: str) -> str:
    """Mirror linz-world backend defaultMRKTaskBubbleID()."""
    return f"task_{sanitize_bubble_id_part(requirement_id)}_{sanitize_bubble_id_part(worker_os_id)}"


def extract_tool_names_from_message(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for call in item.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = str(function.get("name") or call.get("name") or "").strip()
        if name:
            names.append(name)
    name = str(item.get("name") or "").strip()
    if item.get("role") == "tool" and name:
        names.append(name)
    return names


def collect_session_evidence(profile_dir: Path, run_id: str) -> list[dict[str, Any]]:
    sessions_dir = profile_dir / "sessions"
    if not sessions_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    session_paths = sorted(
        [*sessions_dir.glob("*.jsonl"), *sessions_dir.glob("*.json")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for path in session_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if run_id not in text:
            continue

        if path.suffix == ".json":
            try:
                session_payload = json.loads(text)
            except json.JSONDecodeError:
                messages: list[tuple[int, dict[str, Any]]] = []
            else:
                raw_messages = (session_payload.get("messages") if isinstance(session_payload, dict) else []) or []
                messages = [
                    (index, message)
                    for index, message in enumerate(raw_messages, start=1)
                    if isinstance(message, dict)
                ]
        else:
            messages = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                if run_id not in line and "linz_bubble_" not in line and "linz_publish" not in line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    item = {"role": "raw", "content": line}
                if isinstance(item, dict):
                    messages.append((line_no, item))

        for line_no, item in messages:
            tool_names = extract_tool_names_from_message(item) if isinstance(item, dict) else []
            raw_text = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) if isinstance(item, dict) else str(item)
            if run_id not in raw_text and not any(name.startswith(("linz_", "linz_bubble_")) for name in tool_names):
                continue
            rows.append(
                {
                    "path": str(path),
                    "line": line_no,
                    "role": item.get("role") if isinstance(item, dict) else "raw",
                    "tool_names": tool_names,
                    "bubble_ids": sorted(set(BUBBLE_ID_RE.findall(raw_text))),
                    "preview": raw_text[:1200],
                }
            )
    return rows


def row_contains(row: dict[str, Any], *needles: str) -> bool:
    text = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    return all(needle in text for needle in needles)


def session_has_tool(rows: list[dict[str, Any]], tool_name: str) -> bool:
    return any(tool_name in [str(item) for item in row.get("tool_names") or []] for row in rows)


def session_has_linz_publish_event(rows: list[dict[str, Any]], event_type: str) -> bool:
    return any("linz_publish" in [str(item) for item in row.get("tool_names") or []] and row_contains(row, event_type) for row in rows)


def session_has_formal_mrk_event(rows: list[dict[str, Any]], event_type: str) -> bool:
    return any(row_contains(row, event_type, "mrk_publish") or row_contains(row, event_type, "linz_publish") for row in rows)


def gateway_event_rows(
    rows: list[dict[str, Any]],
    event_type: str,
    *,
    consume_status: str = "",
    subject: str = "",
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        record = row.get("record") if isinstance(row.get("record"), dict) else {}
        if str(record.get("event_type") or "") != event_type:
            continue
        if consume_status and str(record.get("consume_status") or "") != consume_status:
            continue
        if subject and str(record.get("subject") or "") != subject:
            continue
        matches.append(row)
    return matches


def candidate_bubble_ids(state: FlowState, evidence_rows: list[dict[str, Any]]) -> list[str]:
    candidates: list[str] = []
    for item in [state.demand_bubble_id, state.requirement_id]:
        if item and item not in candidates:
            candidates.append(item)
    for row in evidence_rows:
        for bubble_id in row.get("bubble_ids") or []:
            if bubble_id not in candidates:
                candidates.append(str(bubble_id))
    return candidates


def read_bubble_snapshot(actor: ActorContext, bubble_id: str) -> dict[str, Any]:
    if not bubble_id:
        return {"success": False, "message": "bubble_id is empty"}
    from tools import linz_world_bubble_tools

    with temporary_hermes_home(actor.profile_dir):
        raw = linz_world_bubble_tools.linz_bubble_snapshot({"bubble_id": bubble_id})
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "raw": raw, "message": "snapshot returned non-JSON"}
    return data if isinstance(data, dict) else {"success": False, "raw": data}


def summarize_snapshot(snapshot_output: dict[str, Any]) -> dict[str, Any]:
    snapshot = snapshot_output.get("snapshot") if isinstance(snapshot_output.get("snapshot"), dict) else {}
    bubble = snapshot.get("bubble") if isinstance(snapshot.get("bubble"), dict) else {}
    children = [item for item in snapshot.get("children") or [] if isinstance(item, dict)]
    mounts = [item for item in snapshot.get("mounts") or [] if isinstance(item, dict)]
    return {
        "success": bool(snapshot_output.get("success")),
        "bubble_id": snapshot_output.get("bubble_id") or bubble.get("bubble_id"),
        "bubble_type": bubble.get("bubble_type"),
        "lifecycle_state": snapshot_output.get("lifecycle_state") or bubble.get("lifecycle_state"),
        "children": [
            {
                "bubble_id": child.get("bubble_id"),
                "bubble_type": child.get("bubble_type"),
                "lifecycle_state": child.get("lifecycle_state"),
                "owner_os_id": child.get("owner_os_id"),
            }
            for child in children
        ],
        "mount_count": len(mounts),
    }


def real_completion_evidence(
    state: FlowState,
    publisher: ActorContext,
    receiver: ActorContext,
) -> dict[str, Any]:
    publisher_gateway = collect_gateway_records(publisher.profile_dir, state.requirement_id)
    receiver_gateway = collect_gateway_records(receiver.profile_dir, state.requirement_id)
    publisher_sessions = collect_session_evidence(publisher.profile_dir, state.requirement_id)
    receiver_sessions = collect_session_evidence(receiver.profile_dir, state.requirement_id)
    session_rows = [*publisher_sessions, *receiver_sessions]
    snapshots: list[dict[str, Any]] = []
    demand_summary: dict[str, Any] = {}
    for bubble_id in candidate_bubble_ids(state, session_rows):
        output = read_bubble_snapshot(publisher, bubble_id)
        summary = summarize_snapshot(output)
        if summary.get("success"):
            snapshots.append(summary)
            if str(summary.get("bubble_type") or "").lower() == "demand" or bubble_id == state.requirement_id:
                demand_summary = summary
                state.demand_bubble_id = str(summary.get("bubble_id") or bubble_id)
                break
    if not demand_summary and snapshots:
        demand_summary = snapshots[0]
    task_ids = []
    for child in demand_summary.get("children") or []:
        if "task" in str(child.get("bubble_type") or "").lower() or str(child.get("bubble_id") or "").startswith("task_"):
            task_ids.append(str(child.get("bubble_id") or ""))
    if task_ids and not state.task_bubble_id:
        state.task_bubble_id = task_ids[0]
    receiver_gateway_handled = any(
        ((row.get("record") or {}).get("consume_status") == "handled")
        and "mrk.requirement.published" in str((row.get("record") or {}).get("event_type") or "")
        for row in receiver_gateway
    )
    publisher_gateway_handled = any((row.get("record") or {}).get("consume_status") == "handled" for row in publisher_gateway)
    receiver_tool_names = sorted(
        {
            name
            for row in receiver_sessions
            for name in row.get("tool_names") or []
            if str(name).startswith(("linz_", "linz_bubble_"))
        }
    )
    publisher_tool_names = sorted(
        {
            name
            for row in publisher_sessions
            for name in row.get("tool_names") or []
            if str(name).startswith(("linz_", "linz_bubble_"))
        }
    )
    demand_archived = str(demand_summary.get("lifecycle_state") or "").lower() == "archived"
    return {
        "complete": demand_archived and receiver_gateway_handled and bool(receiver_tool_names),
        "demand_archived": demand_archived,
        "demand": demand_summary,
        "task_ids": task_ids,
        "publisher_gateway_records": publisher_gateway,
        "receiver_gateway_records": receiver_gateway,
        "publisher_session_evidence": publisher_sessions,
        "receiver_session_evidence": receiver_sessions,
        "publisher_gateway_handled": publisher_gateway_handled,
        "receiver_gateway_handled": receiver_gateway_handled,
        "publisher_tool_names": publisher_tool_names,
        "receiver_tool_names": receiver_tool_names,
        "snapshots": snapshots,
    }


def directed_completion_evidence(
    state: FlowState,
    publisher: ActorContext,
    receiver: ActorContext,
) -> dict[str, Any]:
    publisher_gateway = collect_gateway_records(publisher.profile_dir, state.requirement_id)
    receiver_gateway = collect_gateway_records(receiver.profile_dir, state.requirement_id)
    publisher_sessions = collect_session_evidence(publisher.profile_dir, state.requirement_id)
    receiver_sessions = collect_session_evidence(receiver.profile_dir, state.requirement_id)

    snapshot_output = read_bubble_snapshot(publisher, state.demand_bubble_id or state.requirement_id)
    demand_summary = summarize_snapshot(snapshot_output)
    expected_task_id = expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id)
    child_task_ids = [
        str(child.get("bubble_id") or "")
        for child in demand_summary.get("children") or []
        if str(child.get("bubble_id") or "")
    ]
    if expected_task_id in child_task_ids:
        state.task_bubble_id = expected_task_id
    elif child_task_ids and not state.task_bubble_id:
        state.task_bubble_id = child_task_ids[0]

    receiver_requirement_rows = gateway_event_rows(
        receiver_gateway,
        "wsp.mrk.requirement.published",
        consume_status="handled",
        subject=f"wsp.{receiver.os_id}",
    )
    publisher_requirement_rows = gateway_event_rows(
        publisher_gateway,
        "wsp.mrk.requirement.published",
        subject=f"wsp.{publisher.os_id}",
    )
    publisher_handover_rows = gateway_event_rows(
        publisher_gateway,
        "wsp.mrk.order.handover.delivered",
        consume_status="handled",
        subject=f"wsp.{publisher.os_id}",
    )
    receiver_formal_accept = session_has_linz_publish_event(receiver_sessions, "mrk.order.accepted") or session_has_formal_mrk_event(
        receiver_sessions,
        "mrk.order.accepted",
    )
    receiver_direct_accept = session_has_tool(receiver_sessions, "linz_bubble_accept_demand") and not session_has_formal_mrk_event(
        receiver_sessions,
        "mrk.order.accepted",
    )
    receiver_formal_handover = session_has_linz_publish_event(receiver_sessions, "mrk.order.handover.delivered") or session_has_formal_mrk_event(
        receiver_sessions,
        "mrk.order.handover.delivered",
    )
    default_task_present = expected_task_id in child_task_ids

    return {
        "complete": bool(receiver_requirement_rows)
        and not bool(publisher_requirement_rows)
        and receiver_formal_accept
        and not receiver_direct_accept
        and default_task_present
        and receiver_formal_handover
        and bool(publisher_handover_rows),
        "receiver_gateway_handled": bool(receiver_requirement_rows),
        "publisher_received_own_requirement": bool(publisher_requirement_rows),
        "receiver_formal_accept": receiver_formal_accept,
        "receiver_direct_bubble_accept": receiver_direct_accept,
        "receiver_formal_handover": receiver_formal_handover,
        "publisher_handover_notification": bool(publisher_handover_rows),
        "default_task_present": default_task_present,
        "expected_task_bubble_id": expected_task_id,
        "child_task_ids": child_task_ids,
        "demand": demand_summary,
        "publisher_gateway_records": publisher_gateway,
        "receiver_gateway_records": receiver_gateway,
        "publisher_session_evidence": publisher_sessions,
        "receiver_session_evidence": receiver_sessions,
        "snapshots": [demand_summary] if demand_summary.get("success") else [],
    }


def merge_unique_rows(target: list[dict[str, Any]], rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> None:
    seen = {tuple(str(row.get(field) or "") for field in key_fields) for row in target}
    for row in rows:
        key = tuple(str(row.get(field) or "") for field in key_fields)
        if key not in seen:
            target.append(row)
            seen.add(key)


def require_confirmed_mutations(args: argparse.Namespace) -> tuple[bool, str]:
    if args.dry_run:
        return True, ""
    if not args.confirm_mutations:
        return False, "Remote MRK/Bubble mutations require --confirm-mutations."
    return True, ""


def add_directed_backend_rule_observations(report: FlowReport) -> None:
    report.add_observation(
        {
            "kind": "linz_world_backend_rule",
            "rule": "mrk.requirement.published with target_os_id dispatches wsp.mrk.requirement.published to wsp.<target_os_id>.",
            "source": "D:/workspace/linz-world/backend/internal/modules/mrk/service/requirement_service.go:dispatchDirected",
        }
    )
    report.add_observation(
        {
            "kind": "linz_world_backend_rule",
            "rule": "mrk.order.accepted is the formal receiver action; it bridges DemandBubble activation and creates the default MRK TaskBubble.",
            "source": "D:/workspace/linz-world/backend/internal/modules/mrk/service/requirement_service.go:ProcessOrderAccepted",
        }
    )
    report.add_observation(
        {
            "kind": "linz_world_backend_rule",
            "rule": "Default MRK TaskBubble ID is task_<requirement_id>_<worker_os_id> after backend sanitization.",
            "source": "D:/workspace/linz-world/backend/internal/modules/bubble/service/helpers.go:defaultMRKTaskBubbleID",
        }
    )


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

    requirement_title, requirement_description = concrete_requirement_content(run_id)
    requirement_payload = {
        "requirement_id": state.requirement_id,
        "publisher_os_id": publisher.os_id,
        "publisher_os_name": publisher.os_name or publisher.profile,
        "target_os_id": receiver.os_id,
        "target_os_name": receiver.os_name or receiver.profile,
        "title": requirement_title,
        "description": requirement_description,
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
    if requirement_publish_status == STATUS_PASS and not state.demand_bubble_id and not args.dry_run:
        state.demand_bubble_id = state.requirement_id

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
                "requirement_id": state.requirement_id,
                "name": requirement_payload["title"],
                "goal": requirement_payload["description"],
                "publisher_os_id": publisher.os_id,
                "publisher_os_name": publisher.os_name or publisher.profile,
                "target_os_id": receiver.os_id,
                "target_os_name": receiver.os_name or receiver.profile,
                "budget_amount": requirement_payload["budget_amount"],
                "budget_unit": requirement_payload["budget_unit"],
                "deadline_at": requirement_payload["deadline_at"],
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
            "linz_bubble_snapshot",
            {"bubble_id": state.demand_bubble_id},
            dry_run=args.dry_run,
        )

    report.step(6, "observe DemandBubble activation", receiver, accept_step)

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


def run_directed_flow(args: argparse.Namespace) -> int:
    args.dry_run = bool(getattr(args, "dry_run", False))
    run_id = args.run_id or f"directed-mrk-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    args.run_id = run_id
    args.mode = "directed"
    output_dir = Path(args.output_root).expanduser() / run_id
    report = FlowReport(output_dir, run_id=run_id, command=[Path(sys.executable).name, *sys.argv], dry_run=args.dry_run)
    state = FlowState(
        requirement_id=f"REQ-{run_id}",
        order_id=f"ORD-{run_id}",
        handover_id=f"HANDOVER-{run_id}",
        settlement_id=f"SET-{run_id}",
        demand_bubble_id=f"REQ-{run_id}",
        artifact_ref=f"hermes-session://directed-mrk-flow/{run_id}/artifact",
        summary_ref=f"hermes-session://directed-mrk-flow/{run_id}/summary",
    )
    gateway_handles: list[GatewayHandle] = []
    publisher_profile = args.publisher_profile
    receiver_profile = args.receiver_profile or ""

    def profile_step() -> tuple[str, str, dict[str, Any], str]:
        nonlocal publisher_profile, receiver_profile
        publisher_profile, receiver_profile = select_profiles(args, report)
        return (
            STATUS_PASS,
            f"{publisher_profile} -> {receiver_profile}",
            {"publisher_profile": publisher_profile, "receiver_profile": receiver_profile, "available_profiles": [] if args.dry_run else list_profile_names()},
            "",
        )

    try:
        profile_status, _ = report.step(0, "profile discovery", None, profile_step)
        if profile_status != STATUS_PASS:
            publisher = ActorContext(role="publisher", profile=publisher_profile, profile_dir=Path(""))
            receiver = ActorContext(role="receiver", profile=receiver_profile or "", profile_dir=Path(""))
            report.write(state, publisher, receiver, args=args)
            print(str(output_dir / "REPORT.md"))
            return 1

        publisher = build_actor(publisher_profile, "publisher", dry_run=args.dry_run)
        receiver = build_actor(receiver_profile, "receiver", dry_run=args.dry_run)
        if not args.dry_run:
            baseline = ensure_profile_clone_baseline(receiver.profile_dir, resolve_profile_dir("default"))
            if baseline.get("changed"):
                report.add_observation(
                    {
                        "kind": "profile_clone_baseline",
                        "actor_profile": receiver.profile,
                        "source_profile": "default",
                        **baseline,
                    }
                )
                receiver = build_actor(receiver_profile, "receiver", dry_run=False)
        add_directed_backend_rule_observations(report)

        def directed_preflight_step() -> tuple[str, str, dict[str, Any], str]:
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
            errors.extend(f"publisher: {item}" for item in publisher_errors)
            errors.extend(f"receiver: {item}" for item in receiver_errors)
            details = {
                "publisher": publisher_details,
                "receiver": receiver_details,
                "directed_policy": {
                    "script_mutations": ["publish mrk.requirement.published only"],
                    "observed_agent_actions": [
                        "receiver publishes mrk.order.accepted",
                        "receiver publishes mrk.order.handover.delivered",
                    ],
                    "forbidden_receiver_shortcut": "direct Bubble acceptance without an mrk.order.accepted publish bridge",
                },
            }
            if errors:
                return STATUS_BLOCKED, "directed preflight blocked", details, "; ".join(errors)
            return STATUS_PASS, "directed preflight ready", details, ""

        preflight_status, _ = report.step(1, "directed preflight", None, directed_preflight_step)
        if preflight_status != STATUS_PASS and not args.dry_run:
            report.write(state, publisher, receiver, args=args)
            return 2

        def dry_gateway_step(label: str) -> tuple[str, str, dict[str, Any], str]:
            return STATUS_PASS, f"{label} gateway planned", {"dry_run": True}, ""

        if args.dry_run:
            report.step(2, "publisher gateway ready", publisher, lambda: dry_gateway_step("publisher"))
            report.step(3, "receiver gateway ready", receiver, lambda: dry_gateway_step("receiver"))
        else:
            def publisher_gateway_step() -> tuple[str, str, dict[str, Any], str]:
                status, key, details, error, handle = ensure_gateway_ready(
                    report,
                    publisher,
                    output_dir,
                    start_missing=args.start_missing_gateways,
                    start_timeout_seconds=args.gateway_start_timeout,
                    poll_interval=args.poll_interval,
                )
                if handle is not None:
                    gateway_handles.append(handle)
                return status, key, details, error

            report.step(2, "publisher gateway ready", publisher, publisher_gateway_step)

            def receiver_gateway_step() -> tuple[str, str, dict[str, Any], str]:
                status, key, details, error, handle = ensure_gateway_ready(
                    report,
                    receiver,
                    output_dir,
                    start_missing=args.start_missing_gateways,
                    start_timeout_seconds=args.gateway_start_timeout,
                    poll_interval=args.poll_interval,
                )
                if handle is not None:
                    gateway_handles.append(handle)
                return status, key, details, error

            report.step(3, "receiver gateway ready", receiver, receiver_gateway_step)

        if any(row["status"] in {STATUS_FAIL, STATUS_BLOCKED} for row in report.steps):
            report.write(state, publisher, receiver, args=args)
            return 3

        requirement_title, requirement_description = concrete_requirement_content(run_id)
        requirement_payload = {
            "requirement_id": state.requirement_id,
            "publisher_os_id": publisher.os_id,
            "publisher_os_name": publisher.os_name or publisher.profile,
            "target_os_id": receiver.os_id,
            "target_os_name": receiver.os_name or receiver.profile,
            "title": requirement_title,
            "description": requirement_description,
            "budget_amount": "100",
            "budget_unit": "EC",
            "deadline_at": "2026-06-01T18:00:00+08:00",
            "run_id": run_id,
        }
        report.step(
            4,
            "publish directed MRK requirement",
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

        if args.dry_run:
            state.task_bubble_id = expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id)
            report.step(
                5,
                "receiver gateway consumes directed requirement",
                receiver,
                lambda: (STATUS_PASS, "planned receiver directed WSP consumption", {"dry_run": True}, ""),
            )
            report.step(
                6,
                "verify directed MRK order path",
                None,
                lambda: (
                    STATUS_PASS,
                    "planned formal MRK order path verification",
                    {"expected_task_bubble_id": expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id), "dry_run": True},
                    "",
                ),
            )
            report.write(state, publisher, receiver, args=args)
            print(str(output_dir / "REPORT.md"))
            return 0

        def wait_receiver_directed_step() -> tuple[str, str, dict[str, Any], str]:
            deadline = time.monotonic() + max(1, args.gateway_event_timeout)
            last_records: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                last_records = collect_gateway_records(receiver.profile_dir, state.requirement_id)
                if gateway_event_rows(
                    last_records,
                    "wsp.mrk.requirement.published",
                    consume_status="handled",
                    subject=f"wsp.{receiver.os_id}",
                ):
                    report.add_gateway_records(receiver, last_records)
                    return STATUS_PASS, "receiver consumed directed requirement", {"records": last_records}, ""
                time.sleep(max(1.0, args.poll_interval))
            report.add_gateway_records(receiver, last_records)
            return (
                STATUS_FAIL,
                "receiver did not consume directed requirement",
                {"records": last_records},
                "No handled receiver gateway record for wsp.mrk.requirement.published before timeout.",
            )

        report.step(5, "receiver gateway consumes directed requirement", receiver, wait_receiver_directed_step)

        def wait_directed_completion_step() -> tuple[str, str, dict[str, Any], str]:
            deadline = time.monotonic() + max(1, args.timeout_seconds)
            last: dict[str, Any] = {}
            while time.monotonic() < deadline:
                last = directed_completion_evidence(state, publisher, receiver)
                report.add_observation(
                    {
                        "receiver_gateway_handled": last.get("receiver_gateway_handled"),
                        "publisher_received_own_requirement": last.get("publisher_received_own_requirement"),
                        "receiver_formal_accept": last.get("receiver_formal_accept"),
                        "receiver_direct_bubble_accept": last.get("receiver_direct_bubble_accept"),
                        "default_task_present": last.get("default_task_present"),
                        "receiver_formal_handover": last.get("receiver_formal_handover"),
                        "publisher_handover_notification": last.get("publisher_handover_notification"),
                        "expected_task_bubble_id": last.get("expected_task_bubble_id"),
                        "child_task_ids": last.get("child_task_ids"),
                    }
                )
                if last.get("complete"):
                    report.add_gateway_records(publisher, last.get("publisher_gateway_records") or [])
                    report.add_gateway_records(receiver, last.get("receiver_gateway_records") or [])
                    report.add_session_evidence(publisher, last.get("publisher_session_evidence") or [])
                    report.add_session_evidence(receiver, last.get("receiver_session_evidence") or [])
                    for snap in last.get("snapshots") or []:
                        report.snapshots.append(redact({"run_id": run_id, "source": "directed_observer", "snapshot": snap, "recorded_at": utc_now_iso()}))
                    return STATUS_PASS, "directed formal MRK flow completed", last, ""
                time.sleep(max(1.0, args.poll_interval))

            if last:
                report.add_gateway_records(publisher, last.get("publisher_gateway_records") or [])
                report.add_gateway_records(receiver, last.get("receiver_gateway_records") or [])
                report.add_session_evidence(publisher, last.get("publisher_session_evidence") or [])
                report.add_session_evidence(receiver, last.get("receiver_session_evidence") or [])
                for snap in last.get("snapshots") or []:
                    report.snapshots.append(redact({"run_id": run_id, "source": "directed_observer", "snapshot": snap, "recorded_at": utc_now_iso()}))
            missing = []
            if not last.get("receiver_gateway_handled"):
                missing.append("receiver consumed wsp.mrk.requirement.published")
            if last.get("publisher_received_own_requirement"):
                missing.append("publisher did not receive own directed requirement")
            if not last.get("receiver_formal_accept"):
                missing.append("receiver published mrk.order.accepted")
            if last.get("receiver_direct_bubble_accept"):
                missing.append("receiver avoided direct linz_bubble_accept_demand shortcut")
            if not last.get("default_task_present"):
                missing.append(f"default TaskBubble {last.get('expected_task_bubble_id') or expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id)}")
            if not last.get("receiver_formal_handover"):
                missing.append("receiver published mrk.order.handover.delivered")
            if not last.get("publisher_handover_notification"):
                missing.append("publisher received wsp.mrk.order.handover.delivered")
            return (
                STATUS_FAIL,
                "directed formal MRK flow incomplete",
                last,
                "Missing evidence: " + ", ".join(missing),
            )

        report.step(6, "verify directed MRK order path", None, wait_directed_completion_step)

        report.add_event_rows(publisher, collect_recent_events(publisher, run_id))
        report.add_event_rows(receiver, collect_recent_events(receiver, run_id))
        report.write(state, publisher, receiver, args=args)
        print(str(output_dir / "REPORT.md"))
        return 1 if any(row["status"] in {STATUS_FAIL, STATUS_BLOCKED} for row in report.steps) else 0
    finally:
        if not getattr(args, "keep_started_gateways", False):
            for handle in gateway_handles:
                if handle.started_by_script:
                    stop_gateway_handle(handle)


def run_real_flow(args: argparse.Namespace) -> int:
    args.dry_run = False
    run_id = args.run_id or f"real-bubble-mrk-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    args.run_id = run_id
    args.mode = "real"
    output_dir = Path(args.output_root).expanduser() / run_id
    report = FlowReport(output_dir, run_id=run_id, command=[Path(sys.executable).name, *sys.argv], dry_run=False)
    state = FlowState(
        requirement_id=f"REQ-{run_id}",
        order_id=f"ORD-{run_id}",
        handover_id=f"HANDOVER-{run_id}",
        settlement_id=f"SET-{run_id}",
        demand_bubble_id=f"REQ-{run_id}",
        artifact_ref=f"hermes-session://real-bubble-mrk-flow/{run_id}/artifact",
        summary_ref=f"hermes-session://real-bubble-mrk-flow/{run_id}/summary",
    )
    artifact_path = output_dir / "receiver-work" / "linz_event_summary.py"
    state.artifact_ref = f"file://{artifact_path}"
    gateway_handles: list[GatewayHandle] = []
    publisher_profile = args.publisher_profile
    receiver_profile = args.receiver_profile or ""

    def profile_step() -> tuple[str, str, dict[str, Any], str]:
        nonlocal publisher_profile, receiver_profile
        publisher_profile, receiver_profile = select_profiles(args, report)
        return (
            STATUS_PASS,
            f"{publisher_profile} -> {receiver_profile}",
            {"publisher_profile": publisher_profile, "receiver_profile": receiver_profile, "available_profiles": list_profile_names()},
            "",
        )

    try:
        profile_status, _ = report.step(0, "profile discovery", None, profile_step)
        if profile_status != STATUS_PASS:
            publisher = ActorContext(role="publisher", profile=publisher_profile, profile_dir=Path(""))
            receiver = ActorContext(role="receiver", profile=receiver_profile or "", profile_dir=Path(""))
            report.write(state, publisher, receiver, args=args)
            print(str(output_dir / "REPORT.md"))
            return 1

        publisher = build_actor(publisher_profile, "publisher", dry_run=False)
        receiver = build_actor(receiver_profile, "receiver", dry_run=False)
        baseline = ensure_profile_clone_baseline(receiver.profile_dir, resolve_profile_dir("default"))
        if baseline.get("changed"):
            report.add_observation(
                {
                    "kind": "profile_clone_baseline",
                    "actor_profile": receiver.profile,
                    "source_profile": "default",
                    **baseline,
                }
            )
            receiver = build_actor(receiver_profile, "receiver", dry_run=False)

        def real_preflight_step() -> tuple[str, str, dict[str, Any], str]:
            ok_confirm, confirm_error = require_confirmed_mutations(args)
            publisher_ok, publisher_errors, publisher_details = actor_ready_details(publisher)
            receiver_ok, receiver_errors, receiver_details = actor_ready_details(receiver)
            errors = []
            if not ok_confirm:
                errors.append(confirm_error)
            if publisher.profile == receiver.profile:
                errors.append("Publisher and receiver profiles must differ.")
            if publisher.os_id == receiver.os_id:
                errors.append("Publisher and receiver os_id must differ.")
            errors.extend(f"publisher: {item}" for item in publisher_errors)
            errors.extend(f"receiver: {item}" for item in receiver_errors)
            details = {
                "publisher": publisher_details,
                "receiver": receiver_details,
                "real_mode_policy": {
                    "script_mutations": "forbidden",
                    "allowed_script_side_effects": ["external_prompt", "gateway_process_start"],
                    "allowed_script_reads": ["gateway_ledger", "session_jsonl", "bubble_snapshot"],
                },
            }
            if errors:
                return STATUS_BLOCKED, "real preflight blocked", details, "; ".join(errors)
            return STATUS_PASS, "real preflight ready", details, ""

        preflight_status, _ = report.step(1, "real preflight", None, real_preflight_step)
        if preflight_status != STATUS_PASS:
            report.write(state, publisher, receiver, args=args)
            return 2

        def publisher_gateway_step() -> tuple[str, str, dict[str, Any], str]:
            status, key, details, error, handle = ensure_gateway_ready(
                report,
                publisher,
                output_dir,
                start_missing=args.start_missing_gateways,
                start_timeout_seconds=args.gateway_start_timeout,
                poll_interval=args.poll_interval,
            )
            if handle is not None:
                gateway_handles.append(handle)
            return status, key, details, error

        report.step(2, "publisher gateway ready", publisher, publisher_gateway_step)

        def receiver_gateway_step() -> tuple[str, str, dict[str, Any], str]:
            status, key, details, error, handle = ensure_gateway_ready(
                report,
                receiver,
                output_dir,
                start_missing=args.start_missing_gateways,
                start_timeout_seconds=args.gateway_start_timeout,
                poll_interval=args.poll_interval,
            )
            if handle is not None:
                gateway_handles.append(handle)
            return status, key, details, error

        report.step(3, "receiver gateway ready", receiver, receiver_gateway_step)

        if any(row["status"] in {STATUS_FAIL, STATUS_BLOCKED} for row in report.steps):
            report.write(state, publisher, receiver, args=args)
            return 3

        prompt = build_real_publisher_prompt(state, publisher, receiver, run_id)
        report.step(
            4,
            "external requirement input to publisher",
            publisher,
            lambda: run_agent_oneshot(report, publisher, prompt, output_dir, timeout_seconds=args.agent_timeout_seconds),
        )

        def wait_for_receiver_gateway_step() -> tuple[str, str, dict[str, Any], str]:
            deadline = time.monotonic() + max(1, args.gateway_event_timeout)
            last_records: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                last_records = collect_gateway_records(receiver.profile_dir, state.requirement_id)
                if any(
                    ((row.get("record") or {}).get("consume_status") == "handled")
                    and "mrk.requirement.published" in str((row.get("record") or {}).get("event_type") or "")
                    for row in last_records
                ):
                    report.add_gateway_records(receiver, last_records)
                    return STATUS_PASS, "receiver gateway consumed requirement", {"records": last_records}, ""
                time.sleep(max(1.0, args.poll_interval))
            report.add_gateway_records(receiver, last_records)
            return (
                STATUS_FAIL,
                "receiver gateway did not consume requirement",
                {"records": last_records},
                "No handled receiver gateway record for mrk.requirement.published before timeout.",
            )

        report.step(5, "receiver gateway consumes requirement", receiver, wait_for_receiver_gateway_step)

        receiver_delivery_prompt = build_real_receiver_prompt(state, publisher, receiver, run_id, artifact_path)
        report.step(
            6,
            "receiver agent accepts and delivers",
            receiver,
            lambda: run_agent_oneshot(
                report,
                receiver,
                receiver_delivery_prompt,
                output_dir,
                timeout_seconds=args.agent_timeout_seconds,
                toolsets="linz_world,linz_bubble,file,terminal",
            ),
        )

        def wait_for_publisher_handover_step() -> tuple[str, str, dict[str, Any], str]:
            deadline = time.monotonic() + max(1, args.gateway_event_timeout)
            last_records: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                last_records = collect_gateway_records(publisher.profile_dir, state.requirement_id)
                rows = gateway_event_rows(
                    last_records,
                    "wsp.mrk.order.handover.delivered",
                    consume_status="handled",
                    subject=f"wsp.{publisher.os_id}",
                )
                if rows:
                    report.add_gateway_records(publisher, last_records)
                    return STATUS_PASS, "publisher gateway consumed handover", {"records": last_records}, ""
                time.sleep(max(1.0, args.poll_interval))
            report.add_gateway_records(publisher, last_records)
            return (
                STATUS_FAIL,
                "publisher gateway did not consume handover",
                {"records": last_records},
                "No handled publisher gateway record for wsp.mrk.order.handover.delivered before timeout.",
            )

        report.step(7, "publisher gateway consumes handover", publisher, wait_for_publisher_handover_step)

        publisher_task_acceptance_prompt = build_real_publisher_task_acceptance_prompt(state, publisher, receiver, run_id)
        report.step(
            8,
            "publisher agent reviews task handover",
            publisher,
            lambda: run_agent_oneshot(
                report,
                publisher,
                publisher_task_acceptance_prompt,
                output_dir,
                timeout_seconds=args.agent_timeout_seconds,
            ),
        )

        def publisher_bubble_task_acceptance_step() -> tuple[str, str, dict[str, Any], str]:
            snapshot_output = read_bubble_snapshot(publisher, state.demand_bubble_id or state.requirement_id)
            summary = summarize_snapshot(snapshot_output)
            reviewing_task_ids = [
                str(child.get("bubble_id") or "")
                for child in summary.get("children") or []
                if str(child.get("bubble_id") or "")
                and ("task" in str(child.get("bubble_type") or "").lower() or str(child.get("bubble_id") or "").startswith("task_"))
                and str(child.get("lifecycle_state") or "").lower() == "reviewing"
            ]
            if not reviewing_task_ids:
                return STATUS_SKIPPED, "no reviewing task bubbles", {"snapshot": summary}, ""
            prompt = build_real_publisher_bubble_task_acceptance_prompt(state, publisher, run_id, reviewing_task_ids)
            status, key, details, error = run_agent_oneshot(
                report,
                publisher,
                prompt,
                output_dir,
                timeout_seconds=args.agent_timeout_seconds,
            )
            details = {**details, "reviewing_task_ids": reviewing_task_ids, "pre_acceptance_snapshot": summary}
            return status, key, details, error

        report.step(9, "publisher agent archives task bubbles", publisher, publisher_bubble_task_acceptance_step)

        def wait_for_demand_reviewing_step() -> tuple[str, str, dict[str, Any], str]:
            deadline = time.monotonic() + max(1, args.gateway_event_timeout)
            expected_task_id = expected_mrk_task_bubble_id(state.requirement_id, receiver.os_id)
            last_summary: dict[str, Any] = {}
            while time.monotonic() < deadline:
                snapshot_output = read_bubble_snapshot(publisher, state.demand_bubble_id or state.requirement_id)
                last_summary = summarize_snapshot(snapshot_output)
                task_archived = any(
                    str(child.get("bubble_id") or "") == expected_task_id
                    and str(child.get("lifecycle_state") or "").lower() == "archived"
                    for child in last_summary.get("children") or []
                )
                demand_reviewing = str(last_summary.get("lifecycle_state") or "").lower() == "reviewing"
                report.add_observation(
                    {
                        "demand_reviewing": demand_reviewing,
                        "default_task_archived": task_archived,
                        "demand": last_summary,
                    }
                )
                if demand_reviewing and task_archived:
                    report.snapshots.append(
                        redact(
                            {
                                "run_id": run_id,
                                "source": "wait_for_demand_reviewing",
                                "snapshot": last_summary,
                                "recorded_at": utc_now_iso(),
                            }
                        )
                    )
                    return STATUS_PASS, "demand ready for final delivery", last_summary, ""
                time.sleep(max(1.0, args.poll_interval))
            return (
                STATUS_FAIL,
                "demand not ready for final delivery",
                last_summary,
                "DemandBubble did not reach reviewing with archived default TaskBubble before timeout.",
            )

        report.step(10, "demand ready for final delivery", None, wait_for_demand_reviewing_step)

        receiver_demand_delivery_prompt = build_real_receiver_demand_delivery_prompt(state, receiver, run_id)
        report.step(
            11,
            "receiver agent submits demand delivery",
            receiver,
            lambda: run_agent_oneshot(
                report,
                receiver,
                receiver_demand_delivery_prompt,
                output_dir,
                timeout_seconds=args.agent_timeout_seconds,
            ),
        )

        publisher_demand_acceptance_prompt = build_real_publisher_demand_acceptance_prompt(state, publisher, run_id)
        report.step(
            12,
            "publisher agent reviews demand",
            publisher,
            lambda: run_agent_oneshot(
                report,
                publisher,
                publisher_demand_acceptance_prompt,
                output_dir,
                timeout_seconds=args.agent_timeout_seconds,
            ),
        )

        def wait_for_real_completion_step() -> tuple[str, str, dict[str, Any], str]:
            deadline = time.monotonic() + max(1, args.timeout_seconds)
            last: dict[str, Any] = {}
            best_receiver_tools: list[str] = []
            best_publisher_tools: list[str] = []
            while time.monotonic() < deadline:
                last = real_completion_evidence(state, publisher, receiver)
                best_receiver_tools = sorted(set([*best_receiver_tools, *last.get("receiver_tool_names", [])]))
                best_publisher_tools = sorted(set([*best_publisher_tools, *last.get("publisher_tool_names", [])]))
                report.add_observation(
                    {
                        "demand_archived": last.get("demand_archived"),
                        "demand": last.get("demand"),
                        "receiver_gateway_handled": last.get("receiver_gateway_handled"),
                        "publisher_gateway_handled": last.get("publisher_gateway_handled"),
                        "receiver_tool_names": last.get("receiver_tool_names"),
                        "publisher_tool_names": last.get("publisher_tool_names"),
                    }
                )
                if last.get("complete"):
                    report.add_gateway_records(publisher, last.get("publisher_gateway_records") or [])
                    report.add_gateway_records(receiver, last.get("receiver_gateway_records") or [])
                    report.add_session_evidence(publisher, last.get("publisher_session_evidence") or [])
                    report.add_session_evidence(receiver, last.get("receiver_session_evidence") or [])
                    for snap in last.get("snapshots") or []:
                        report.snapshots.append(redact({"run_id": run_id, "source": "real_observer", "snapshot": snap, "recorded_at": utc_now_iso()}))
                    return STATUS_PASS, "real autonomous flow completed", last, ""
                time.sleep(max(1.0, args.poll_interval))

            if last:
                report.add_gateway_records(publisher, last.get("publisher_gateway_records") or [])
                report.add_gateway_records(receiver, last.get("receiver_gateway_records") or [])
                report.add_session_evidence(publisher, last.get("publisher_session_evidence") or [])
                report.add_session_evidence(receiver, last.get("receiver_session_evidence") or [])
                for snap in last.get("snapshots") or []:
                    report.snapshots.append(redact({"run_id": run_id, "source": "real_observer", "snapshot": snap, "recorded_at": utc_now_iso()}))
            missing = []
            if not last.get("demand_archived"):
                missing.append("DemandBubble archived")
            if not last.get("receiver_gateway_handled"):
                missing.append("receiver gateway handled requirement")
            if not best_receiver_tools:
                missing.append("receiver LLM/tool activity")
            return (
                STATUS_FAIL,
                "real autonomous flow incomplete",
                {**last, "best_receiver_tool_names": best_receiver_tools, "best_publisher_tool_names": best_publisher_tools},
                "Missing evidence: " + ", ".join(missing),
            )

        report.step(13, "wait for real agent completion", None, wait_for_real_completion_step)

        report.add_event_rows(publisher, collect_recent_events(publisher, run_id))
        report.add_event_rows(receiver, collect_recent_events(receiver, run_id))
        report.write(state, publisher, receiver, args=args)
        print(str(output_dir / "REPORT.md"))
        return 1 if any(row["status"] in {STATUS_FAIL, STATUS_BLOCKED} for row in report.steps) else 0
    finally:
        if not getattr(args, "keep_started_gateways", False):
            for handle in gateway_handles:
                if handle.started_by_script:
                    stop_gateway_handle(handle)


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

    real = sub.add_parser("real", help="Run the real agent/gateway MRK flow test.")
    real.add_argument("--publisher-profile", default="default", help="Profile used as the requirement publisher.")
    real.add_argument("--receiver-profile", default="", help="Profile used as the requirement receiver.")
    real.add_argument("--auto-create-receiver", action=argparse.BooleanOptionalAction, default=True)
    real.add_argument("--receiver-agent-name", default="", help="Agent name for an auto-created receiver spirit.")
    real.add_argument("--receiver-persona-seed", default="", help="Persona seed for an auto-created receiver spirit.")
    real.add_argument("--clone-config-from-default", action=argparse.BooleanOptionalAction, default=True)
    real.add_argument("--hermes-home", default="", help="Optional HERMES_HOME override for the current/default profile.")
    real.add_argument("--run-id", default="", help="Run identifier used in payloads and output paths.")
    real.add_argument("--output-root", default="experiment/results", help="Root directory for exported reports.")
    real.add_argument("--confirm-mutations", action="store_true", help="Allow the agent prompt to perform real MRK/Bubble mutations.")
    real.add_argument("--start-missing-gateways", action=argparse.BooleanOptionalAction, default=True)
    real.add_argument("--keep-started-gateways", action="store_true", help="Leave gateways started by this script running after the test.")
    real.add_argument("--gateway-start-timeout", type=int, default=90, help="Seconds to wait for a started gateway to become online.")
    real.add_argument("--gateway-event-timeout", type=int, default=180, help="Seconds to wait for receiver gateway to consume the requirement.")
    real.add_argument("--agent-timeout-seconds", type=int, default=600, help="Seconds to allow the publisher agent one-shot turn.")
    real.add_argument("--timeout-seconds", type=int, default=900, help="Seconds to wait for autonomous completion.")
    real.add_argument("--poll-interval", type=float, default=10.0, help="Polling interval for gateway/session/Bubble evidence.")

    directed = sub.add_parser("directed", help="Run the directed MRK requirement/gateway flow test.")
    directed.add_argument("--publisher-profile", default="default", help="Profile used as the requirement publisher.")
    directed.add_argument("--receiver-profile", default="", help="Profile used as the requirement receiver.")
    directed.add_argument("--auto-create-receiver", action=argparse.BooleanOptionalAction, default=True)
    directed.add_argument("--receiver-agent-name", default="", help="Agent name for an auto-created receiver spirit.")
    directed.add_argument("--receiver-persona-seed", default="", help="Persona seed for an auto-created receiver spirit.")
    directed.add_argument("--clone-config-from-default", action=argparse.BooleanOptionalAction, default=True)
    directed.add_argument("--hermes-home", default="", help="Optional HERMES_HOME override for the current/default profile.")
    directed.add_argument("--run-id", default="", help="Run identifier used in payloads and output paths.")
    directed.add_argument("--output-root", default="experiment/results", help="Root directory for exported reports.")
    directed.add_argument("--confirm-mutations", action="store_true", help="Allow the script to publish the directed MRK requirement.")
    directed.add_argument("--dry-run", action="store_true", help="Plan and report the directed flow without remote side effects.")
    directed.add_argument("--start-missing-gateways", action=argparse.BooleanOptionalAction, default=True)
    directed.add_argument("--keep-started-gateways", action="store_true", help="Leave gateways started by this script running after the test.")
    directed.add_argument("--gateway-start-timeout", type=int, default=90, help="Seconds to wait for a started gateway to become online.")
    directed.add_argument("--gateway-event-timeout", type=int, default=180, help="Seconds to wait for receiver gateway to consume the directed requirement.")
    directed.add_argument("--timeout-seconds", type=int, default=900, help="Seconds to wait for receiver formal MRK accept/handover evidence.")
    directed.add_argument("--poll-interval", type=float, default=10.0, help="Polling interval for gateway/session/Bubble evidence.")
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
    if args.command == "real":
        args.dry_run = False
        try:
            return run_real_flow(args)
        except Exception as exc:
            print(f"linz_bubble_mrk_flow_test real failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    if args.command == "directed":
        try:
            return run_directed_flow(args)
        except Exception as exc:
            print(f"linz_bubble_mrk_flow_test directed failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
