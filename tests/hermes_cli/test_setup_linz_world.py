from __future__ import annotations

from agent.linz_world.config import DEFAULT_LINZ_WORLD_NATS_URL, DEFAULT_LINZ_WORLD_SERVICE_URL
from hermes_cli import setup as setup_mod


def _unexpected_prompt(name):
    return lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(f"unexpected {name} prompt"))


def test_linz_setup_saves_persona_seed_to_config_and_soul_md(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text("Base Hermes identity.\n", encoding="utf-8")
    config = {"linz_world": {"service_url": "http://linz.test"}}
    answers = iter(["Hermes Test", "reliable, direct, and careful"])

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "_complete_linz_world_login", lambda cfg: True)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", _unexpected_prompt("yes/no"))
    monkeypatch.setattr(setup_mod, "prompt_choice", _unexpected_prompt("choice"))
    monkeypatch.setattr(
        setup_mod,
        "prompt",
        lambda question, default=None, password=False: next(answers),
    )

    setup_mod.setup_linz_world(config)

    linz = config["linz_world"]
    assert linz["enabled"] is True
    assert linz["identity_required_on_agent_load"] is True
    assert linz["service_url"] == "http://linz.test"
    assert linz["nats_url"] == DEFAULT_LINZ_WORLD_NATS_URL
    assert linz["os_name"] == "Hermes Test"
    assert linz["os_type"] == "USER"
    assert linz["runtime_type"] == "Hermes"
    assert linz["persona_seed"] == "reliable, direct, and careful"
    soul = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert soul.startswith("Base Hermes identity.\n")
    assert "<!-- LINZ_WORLD:PERSONA_SEED:START -->" in soul
    assert "## Linz World Persona Seed" in soul
    assert "reliable, direct, and careful" in soul
    assert "<!-- LINZ_WORLD:PERSONA_SEED:END -->" in soul


def test_linz_setup_enables_os_runtime_when_it_is_still_default_disabled(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text(
        "Base Hermes identity.\n\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:START -->\n"
        "## Linz World Persona Seed\n\n"
        "existing soul seed\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:END -->\n",
        encoding="utf-8",
    )
    config = {"linz_world": {"enabled": True}, "os_runtime": {"enabled": False}}

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "_complete_linz_world_login", lambda cfg: True)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", _unexpected_prompt("yes/no"))
    monkeypatch.setattr(setup_mod, "prompt_choice", _unexpected_prompt("choice"))
    monkeypatch.setattr(setup_mod, "prompt", _unexpected_prompt("persona"))

    setup_mod.setup_linz_world(config)

    runtime = config["os_runtime"]
    autonomous = runtime["autonomous"]
    assert runtime["enabled"] is True
    assert runtime["mode"] == "autonomous_low_risk"
    assert runtime["allow_auto_continuation"] is True
    assert runtime["allow_tool_execution"] is False
    assert autonomous["enabled"] is True
    assert autonomous["start_on_agent_load"] is True
    assert autonomous["start_with_gateway"] is True
    assert autonomous["apply_to_all_turns"] is True
    assert autonomous["inject_self_prompt"] is True
    assert autonomous["respond_to_world_events"] is True
    assert autonomous["allow_tool_execution"] is True
    assert autonomous["allow_world_publish"] is True
    assert autonomous["allow_chat_reply_auto_send"] is True
    assert autonomous["require_approval_for_world_publish"] is False


def test_linz_setup_preserves_custom_os_runtime_config(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text(
        "Base Hermes identity.\n\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:START -->\n"
        "## Linz World Persona Seed\n\n"
        "existing soul seed\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:END -->\n",
        encoding="utf-8",
    )
    config = {
        "linz_world": {"enabled": True},
        "os_runtime": {
            "enabled": True,
            "mode": "passive",
            "autonomous": {"enabled": False, "apply_to_all_turns": False},
        },
    }

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "_complete_linz_world_login", lambda cfg: True)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", _unexpected_prompt("yes/no"))
    monkeypatch.setattr(setup_mod, "prompt_choice", _unexpected_prompt("choice"))
    monkeypatch.setattr(setup_mod, "prompt", _unexpected_prompt("persona"))

    setup_mod.setup_linz_world(config)

    assert config["os_runtime"]["mode"] == "passive"
    assert config["os_runtime"]["autonomous"]["enabled"] is False
    assert config["os_runtime"]["autonomous"]["apply_to_all_turns"] is False


def test_linz_setup_uses_existing_linz_soul_module_when_seed_prompt_is_blank(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text(
        "Base Hermes identity.\n\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:START -->\n"
        "## Linz World Persona Seed\n\n"
        "existing soul seed\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:END -->\n",
        encoding="utf-8",
    )
    config = {"linz_world": {"enabled": True}}

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "_complete_linz_world_login", lambda cfg: True)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", _unexpected_prompt("yes/no"))
    monkeypatch.setattr(setup_mod, "prompt_choice", _unexpected_prompt("choice"))
    monkeypatch.setattr(setup_mod, "prompt", _unexpected_prompt("persona"))

    setup_mod.setup_linz_world(config)

    assert config["linz_world"]["persona_seed"] == "existing soul seed"
    assert config["linz_world"]["service_url"] == DEFAULT_LINZ_WORLD_SERVICE_URL
    assert config["linz_world"]["nats_url"] == DEFAULT_LINZ_WORLD_NATS_URL
    soul = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert soul.startswith("Base Hermes identity.\n")
    assert soul.count("<!-- LINZ_WORLD:PERSONA_SEED:START -->") == 1
    assert "existing soul seed" in soul


def test_linz_setup_preserves_existing_persona_without_prompting(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text(
        "Base Hermes identity.\n\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:START -->\n"
        "## Linz World Persona Seed\n\n"
        "old seed\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:END -->\n\n"
        "Additional hand-written instructions.\n",
        encoding="utf-8",
    )
    config = {"linz_world": {"enabled": True, "persona_seed": "old seed"}}

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "_complete_linz_world_login", lambda cfg: True)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", _unexpected_prompt("yes/no"))
    monkeypatch.setattr(setup_mod, "prompt_choice", _unexpected_prompt("choice"))
    monkeypatch.setattr(setup_mod, "prompt", _unexpected_prompt("persona"))

    setup_mod.setup_linz_world(config)

    soul = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert soul.startswith("Base Hermes identity.\n")
    assert "Additional hand-written instructions." in soul
    assert "old seed" in soul
    assert soul.count("<!-- LINZ_WORLD:PERSONA_SEED:START -->") == 1


def test_inject_linz_persona_seed_updates_only_existing_module():
    original = (
        "Base Hermes identity.\n\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:START -->\n"
        "## Linz World Persona Seed\n\n"
        "old seed\n"
        "<!-- LINZ_WORLD:PERSONA_SEED:END -->\n\n"
        "Additional hand-written instructions.\n"
    )

    updated = setup_mod._inject_linz_persona_seed(original, "new seed")

    assert updated.startswith("Base Hermes identity.\n")
    assert "Additional hand-written instructions." in updated
    assert "new seed" in updated
    assert "old seed" not in updated
    assert updated.count("<!-- LINZ_WORLD:PERSONA_SEED:START -->") == 1


def test_linz_setup_prints_success_after_login(tmp_path, monkeypatch, capsys):
    (tmp_path / "SOUL.md").write_text("Base Hermes identity.\n", encoding="utf-8")
    config = {"linz_world": {"service_url": "http://linz.test"}}
    answers = iter(["Hermes Test", "reliable, direct, and careful"])

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    def complete_login(cfg):
        setup_mod.print_success("接入灵治平台成功！")
        return True

    monkeypatch.setattr(setup_mod, "_complete_linz_world_login", complete_login)
    monkeypatch.setattr(setup_mod, "prompt", lambda question, default=None, password=False: next(answers))

    setup_mod.setup_linz_world(config)

    assert "接入灵治平台成功！" in capsys.readouterr().out
