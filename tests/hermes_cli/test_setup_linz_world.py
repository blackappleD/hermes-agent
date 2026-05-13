from __future__ import annotations

from hermes_cli import setup as setup_mod


def test_linz_setup_saves_persona_seed_to_config_and_soul_md(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text("Base Hermes identity.\n", encoding="utf-8")
    config = {}
    answers = iter(["http://linz.test", "Hermes Test", "reliable, direct, and careful"])

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", lambda question, default=True: True)
    monkeypatch.setattr(setup_mod, "prompt_choice", lambda question, choices, default=0, description=None: 0)
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
    answers = iter(["http://linz.test", "Hermes", ""])

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", lambda question, default=True: True)
    monkeypatch.setattr(setup_mod, "prompt_choice", lambda question, choices, default=0, description=None: 0)
    monkeypatch.setattr(
        setup_mod,
        "prompt",
        lambda question, default=None, password=False: next(answers),
    )

    setup_mod.setup_linz_world(config)

    assert config["linz_world"]["persona_seed"] == "existing soul seed"
    soul = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert soul.startswith("Base Hermes identity.\n")
    assert soul.count("<!-- LINZ_WORLD:PERSONA_SEED:START -->") == 1
    assert "existing soul seed" in soul


def test_linz_setup_updates_only_existing_linz_soul_module(tmp_path, monkeypatch):
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
    answers = iter(["http://linz.test", "Hermes", "new seed"])

    monkeypatch.setattr(setup_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)
    monkeypatch.setattr(setup_mod, "prompt_yes_no", lambda question, default=True: True)
    monkeypatch.setattr(setup_mod, "prompt_choice", lambda question, choices, default=0, description=None: 0)
    monkeypatch.setattr(
        setup_mod,
        "prompt",
        lambda question, default=None, password=False: next(answers),
    )

    setup_mod.setup_linz_world(config)

    soul = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert soul.startswith("Base Hermes identity.\n")
    assert "Additional hand-written instructions." in soul
    assert "new seed" in soul
    assert "old seed" not in soul
    assert soul.count("<!-- LINZ_WORLD:PERSONA_SEED:START -->") == 1
