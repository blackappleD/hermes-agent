from agent.linz_world.api_client import HttpLinzWorldService, default_service
from agent.linz_world.config import (
    DEFAULT_LINZ_WORLD_CONFIG,
    DEFAULT_LINZ_WORLD_NATS_URL,
    DEFAULT_LINZ_WORLD_SERVICE_URL,
    load_linz_world_config,
    validate_no_automatic_behaviors,
)


def test_defaults_enable_linz_bubble_flow_controls():
    cfg = load_linz_world_config({"linz_world": {}})
    assert cfg.enabled is True
    assert cfg.identity_required_on_agent_load is True
    assert cfg.service_url == DEFAULT_LINZ_WORLD_SERVICE_URL
    assert cfg.nats_url == DEFAULT_LINZ_WORLD_NATS_URL
    assert cfg.bubble.enabled is True
    assert cfg.bubble.read_only is False
    assert cfg.bubble.allow_mutations is True
    assert cfg.bubble.allow_autonomous_create_demand is True
    assert cfg.bubble.allow_autonomous_accept_demand is True
    assert cfg.bubble.allow_autonomous_create_task is True
    assert cfg.bubble.allow_autonomous_mount is True
    assert cfg.bubble.allow_autonomous_submit_artifact is True
    assert cfg.bubble.allow_autonomous_review is True
    assert validate_no_automatic_behaviors(cfg) == [
        "bubble.allow_autonomous_create_demand",
        "bubble.allow_autonomous_accept_demand",
        "bubble.allow_autonomous_create_task",
        "bubble.allow_autonomous_mount",
        "bubble.allow_autonomous_submit_artifact",
        "bubble.allow_autonomous_review",
    ]


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


def test_bubble_config_is_nested_and_bounded():
    cfg = load_linz_world_config(
        {
            "linz_world": {
                "bubble": {
                    "read_only": False,
                    "allow_mutations": True,
                    "snapshot_context_max_events": 999,
                    "snapshot_context_max_residues": 0,
                    "default_task_slot_id": "slot.task.agent",
                }
            }
        }
    )

    assert cfg.bubble.read_only is False
    assert cfg.bubble.allow_mutations is True
    assert cfg.bubble.snapshot_context_max_events == 200
    assert cfg.bubble.snapshot_context_max_residues == 1
    assert cfg.bubble.default_task_slot_id == "slot.task.agent"
