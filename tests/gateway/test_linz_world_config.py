from gateway.config import Platform, load_gateway_config


def test_linz_world_top_level_config_enables_gateway_adapter(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "linz_world:\n"
        "  enabled: true\n"
        "  persona_seed: stable seed\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = load_gateway_config()
    platform = Platform("linz_world")

    assert platform in config.platforms
    assert config.platforms[platform].enabled is True


def test_linz_world_explicit_platform_config_can_disable_gateway_adapter(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "linz_world:\n"
        "  enabled: true\n"
        "  persona_seed: stable seed\n"
        "platforms:\n"
        "  linz_world:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = load_gateway_config()
    platform = Platform("linz_world")

    assert platform in config.platforms
    assert config.platforms[platform].enabled is False
