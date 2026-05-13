"""Native Linz World CLI commands."""

from __future__ import annotations

import argparse
import json
from typing import Any

from agent.linz_world import auth, identity
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.models import LoginState, to_plain
from agent.linz_world.publisher import publish_event
from agent.linz_world.status import events_summary, status_summary


def build_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("linz", help="Manage native Linz World identity and world access")
    linz_sub = parser.add_subparsers(dest="linz_action")
    linz_sub.add_parser("status", help="Show Linz World identity and registration status")
    linz_sub.add_parser("login", help="Start or refresh a Linz World login session")
    linz_sub.add_parser("logout", help="Clear the current Linz World login session")
    linz_sub.add_parser("map", help="Refresh and show the Linz World authorization map")
    events = linz_sub.add_parser("events", help="Show recent Linz World events")
    events.add_argument("--limit", type=int, default=20)
    events.add_argument("--status", default="")
    publish = linz_sub.add_parser("publish", help="Publish a governed Linz World event")
    publish.add_argument("subject")
    publish.add_argument("event_type")
    publish.add_argument("--payload", default="{}")
    parser.set_defaults(func=linz_command)
    return parser


def _print_json(data: Any) -> None:
    print(json.dumps(to_plain(data), ensure_ascii=False, indent=2, sort_keys=True))


def linz_command(args) -> None:
    repo = LinzStateRepository()
    action = getattr(args, "linz_action", None) or "status"
    if action == "status":
        identity.ensure_original_spirit_identity(repo)
        _print_json(status_summary(repo))
        return
    if action == "login":
        session = auth.login(repo)
        _print_json({
            "success": session.state == LoginState.LOGGED_IN,
            "message": "接入灵治平台成功！" if session.state == LoginState.LOGGED_IN else session.last_error,
            "login": session,
        })
        return
    if action == "logout":
        _print_json({"success": True, "login": auth.logout(repo)})
        return
    if action == "map":
        _print_json({"success": True, "authorization": auth.refresh_authorization_map(repo)})
        return
    if action == "events":
        _print_json(events_summary(repo, limit=getattr(args, "limit", 20), status=getattr(args, "status", "") or None))
        return
    if action == "publish":
        try:
            payload = json.loads(getattr(args, "payload", "{}") or "{}")
        except json.JSONDecodeError as exc:
            _print_json({"success": False, "error": {"code": "invalid_json", "message": str(exc)}})
            return
        receipt = publish_event(args.subject, args.event_type, payload, repository=repo)
        _print_json({
            "success": receipt.status.value == "published",
            "status": receipt.status.value,
            "receipt": receipt,
        })
        return
    _print_json({"success": False, "error": {"code": "unknown_command", "message": f"Unknown linz command: {action}"}})
