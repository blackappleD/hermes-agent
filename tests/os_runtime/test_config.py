from agent.os_runtime.config import (
    AutonomousRuntimeConfig,
    DEFAULT_OS_RUNTIME_CONFIG,
    OSRuntimeConfig,
    load_os_runtime_config,
)
from agent.os_runtime.domain import RiskLevel
from hermes_cli.config import DEFAULT_CONFIG


def test_default_os_runtime_config_is_passive_and_opt_in():
    config = OSRuntimeConfig()

    assert config.enabled is False
    assert config.mode == "passive"
    assert config.allow_tool_execution is False
    assert config.allow_auto_continuation is False
    assert config.tick_interval_seconds == 0
    assert config.max_continuation_turns == 8
    assert config.event_store == "sessiondb_side_tables"
    assert config.model_task == "os_runtime_intent"
    assert config.intent_generation == "llm"
    assert config.use_llm_intent is True
    assert config.risk.require_approval_at is RiskLevel.MEDIUM
    assert config.autonomous.enabled is False
    assert config.autonomous.apply_to_all_turns is False
    assert config.autonomous.allow_tool_execution is False
    assert config.autonomous.allow_world_publish is False
    assert config.autonomous.require_approval_for_world_publish is True


def test_default_config_dict_matches_config_contract():
    assert DEFAULT_OS_RUNTIME_CONFIG == {
        "enabled": False,
        "mode": "passive",
        "max_continuation_turns": 8,
        "tick_interval_seconds": 0,
        "allow_tool_execution": False,
        "allow_auto_continuation": False,
        "event_store": "sessiondb_side_tables",
        "model_task": "os_runtime_intent",
        "intent_generation": "llm",
        "risk": {"require_approval_at": "medium"},
        "autonomous": AutonomousRuntimeConfig().to_dict(include_extra=False),
    }


def test_load_os_runtime_config_from_dict_preserves_unknown_keys():
    config = load_os_runtime_config(
        {
            "enabled": True,
            "mode": "assisted",
            "tick_interval_seconds": 15,
            "allow_tool_execution": "false",
            "intent_generation": "llm",
            "risk": {"require_approval_at": "high"},
            "autonomous": {
                "enabled": "true",
                "apply_to_all_turns": "yes",
                "inject_self_prompt": "false",
                "allow_world_publish": "false",
                "future_autonomous": "kept",
            },
            "future_key": {"kept": True},
        }
    )

    assert config.enabled is True
    assert config.mode == "assisted"
    assert config.tick_interval_seconds == 15
    assert config.allow_tool_execution is False
    assert config.intent_generation == "llm"
    assert config.use_llm_intent is True
    assert config.risk.require_approval_at is RiskLevel.HIGH
    assert config.autonomous.enabled is True
    assert config.autonomous.apply_to_all_turns is True
    assert config.autonomous.inject_self_prompt is False
    assert config.autonomous.allow_world_publish is False
    assert config.autonomous.extra == {"future_autonomous": "kept"}
    assert config.extra == {"future_key": {"kept": True}}
    assert config.to_dict()["future_key"] == {"kept": True}
    assert config.to_dict()["autonomous"]["future_autonomous"] == "kept"


def test_hermes_default_config_includes_os_runtime_without_version_bump():
    assert DEFAULT_CONFIG["_config_version"] == 23
    assert DEFAULT_CONFIG["os_runtime"] == DEFAULT_OS_RUNTIME_CONFIG
    assert DEFAULT_CONFIG["os_runtime"]["enabled"] is False
    assert DEFAULT_CONFIG["os_runtime"]["mode"] == "passive"
    assert DEFAULT_CONFIG["os_runtime"]["allow_tool_execution"] is False
    assert DEFAULT_CONFIG["os_runtime"]["allow_auto_continuation"] is False
    assert DEFAULT_CONFIG["os_runtime"]["tick_interval_seconds"] == 0
    assert DEFAULT_CONFIG["os_runtime"]["autonomous"]["enabled"] is False


def test_import_smoke_has_no_runtime_side_effects():
    import agent.os_runtime.config as os_config
    import agent.os_runtime.domain as os_domain
    import hermes_cli.config as hermes_config

    assert os_config.DEFAULT_OS_RUNTIME_CONFIG["enabled"] is False
    assert os_config.DEFAULT_OS_RUNTIME_CONFIG["autonomous"]["allow_world_publish"] is False
    assert os_domain.ArbitrationDecision.REJECT.value == "reject"
    assert hermes_config.DEFAULT_CONFIG["os_runtime"]["enabled"] is False
