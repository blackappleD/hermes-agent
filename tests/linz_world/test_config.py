from agent.linz_world.config import load_linz_world_config, validate_no_automatic_behaviors


def test_defaults_do_not_enable_automatic_behaviors():
    cfg = load_linz_world_config({"linz_world": {}})
    assert cfg.enabled is True
    assert cfg.identity_required_on_agent_load is False
    assert validate_no_automatic_behaviors(cfg) == []


def test_retry_limit_is_capped_at_three():
    cfg = load_linz_world_config({"linz_world": {"event_retry_limit": 99}})
    assert cfg.event_retry_limit == 3
