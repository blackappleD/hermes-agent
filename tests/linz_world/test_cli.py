from hermes_cli.commands import resolve_command
from toolsets import get_toolset, resolve_toolset


def test_linz_command_is_discoverable():
    command = resolve_command("linz")
    assert command is not None
    assert "status" in command.subcommands


def test_linz_toolset_is_discoverable():
    toolset = get_toolset("linz_world")
    assert toolset is not None
    assert "linz_status" in toolset["tools"]
    assert "linz_publish" in resolve_toolset("linz_world")
