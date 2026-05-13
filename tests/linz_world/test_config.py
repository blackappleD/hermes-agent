from agent.linz_world.api_client import HttpLinzWorldService, default_service
from agent.linz_world.config import (
    DEFAULT_LINZ_WORLD_CONFIG,
    DEFAULT_LINZ_WORLD_NATS_URL,
    DEFAULT_LINZ_WORLD_SERVICE_URL,
    load_linz_world_config,
    validate_no_automatic_behaviors,
)


def test_defaults_do_not_enable_automatic_behaviors():
    cfg = load_linz_world_config({"linz_world": {}})
    assert cfg.enabled is True
    assert cfg.identity_required_on_agent_load is True
    assert cfg.service_url == DEFAULT_LINZ_WORLD_SERVICE_URL
    assert cfg.nats_url == DEFAULT_LINZ_WORLD_NATS_URL
    assert validate_no_automatic_behaviors(cfg) == []


def test_linz_config_uses_single_service_url_and_login_token_compute():
    cfg = load_linz_world_config({"linz_world": {}})

    assert "server_url" not in DEFAULT_LINZ_WORLD_CONFIG
    assert "compute_api_key_ref" not in DEFAULT_LINZ_WORLD_CONFIG
    assert not hasattr(cfg, "compute_api_key_ref")


def test_retry_limit_is_capped_at_three():
    cfg = load_linz_world_config({"linz_world": {"event_retry_limit": 99}})
    assert cfg.event_retry_limit == 3


def test_blank_service_url_uses_default_linz_world_endpoint():
    cfg = load_linz_world_config({"linz_world": {"service_url": "", "nats_url": ""}})
    svc = default_service({"linz_world": {"service_url": ""}})

    assert cfg.service_url == DEFAULT_LINZ_WORLD_SERVICE_URL
    assert cfg.nats_url == DEFAULT_LINZ_WORLD_NATS_URL
    assert isinstance(svc, HttpLinzWorldService)
    assert svc.base_url == f"{DEFAULT_LINZ_WORLD_SERVICE_URL}/api/v1"


def test_persona_seed_and_registration_metadata_config():
    cfg = load_linz_world_config(
        {
            "linz_world": {
                "persona_seed": "  careful collaborator  ",
                "os_type": "sev",
                "runtime_type": "Codex",
            }
        }
    )

    assert cfg.persona_seed == "careful collaborator"
    assert cfg.os_type == "SEV"
    assert cfg.runtime_type == "Codex"
