import argparse
import json

from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.identity import ensure_original_spirit_identity
from hermes_cli.commands import resolve_command
from hermes_cli.linz import linz_command
from toolsets import get_toolset, resolve_toolset


def test_linz_command_is_discoverable():
    command = resolve_command("linz")
    assert command is not None
    assert "status" in command.subcommands


def test_linz_toolset_is_discoverable():
    toolset = get_toolset("linz_world")
    assert toolset is not None
    assert "linz_status" in toolset["tools"]
    assert "linz_chat_send" in toolset["tools"]
    assert "linz_publish" in resolve_toolset("linz_world")


def test_linz_login_outputs_resolved_token(linz_home, FakeLinzService, monkeypatch, capsys):
    svc = FakeLinzService()
    repo = LinzStateRepository(root=linz_home / "linz_world", profile_id="test-profile")
    ensure_original_spirit_identity(
        repo,
        svc,
        config={"linz_world": {"persona_seed": "stable persona seed"}},
    )
    monkeypatch.setattr("agent.linz_world.auth.default_service", lambda config=None: svc)

    linz_command(argparse.Namespace(linz_action="login"))

    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["token"] == "event-token-secret"
    assert output["login"]["token_ref"].startswith("linz_secret:event_token:")
