from agent.linz_world.config import load_linz_world_config, validate_no_automatic_behaviors
from agent.linz_world.api_client import LinzWorldServiceError, default_service

import pytest


def test_defaults_do_not_enable_automatic_behaviors():
    cfg = load_linz_world_config({"linz_world": {}})
    assert cfg.enabled is True
    assert cfg.identity_required_on_agent_load is True
    assert validate_no_automatic_behaviors(cfg) == []


def test_retry_limit_is_capped_at_three():
    cfg = load_linz_world_config({"linz_world": {"event_retry_limit": 99}})
    assert cfg.event_retry_limit == 3


def test_missing_service_url_is_actionable_configuration_error():
    with pytest.raises(LinzWorldServiceError, match="service_url"):
        default_service({"linz_world": {"service_url": ""}})


def test_server_url_is_only_compatibility_input():
    cfg = load_linz_world_config({"linz_world": {"server_url": "http://linz.test"}})
    assert cfg.service_url == "http://linz.test"
