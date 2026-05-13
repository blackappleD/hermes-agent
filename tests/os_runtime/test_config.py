from agent.os_runtime.config import (
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
    assert config.risk.require_approval_at is RiskLevel.MEDIUM


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
        "risk": {"require_approval_at": "medium"},
    }


def test_load_os_runtime_config_from_dict_preserves_unknown_keys():
    config = load_os_runtime_config(
        {
            "enabled": True,
            "mode": "assisted",
            "tick_interval_seconds": 15,
            "allow_tool_execution": "false",
            "risk": {"require_approval_at": "high"},
            "future_key": {"kept": True},
        }
    )

    assert config.enabled is True
    assert config.mode == "assisted"
    assert config.tick_interval_seconds == 15
    assert config.allow_tool_execution is False
    assert config.risk.require_approval_at is RiskLevel.HIGH
    assert config.extra == {"future_key": {"kept": True}}
    assert config.to_dict()["future_key"] == {"kept": True}


def test_hermes_default_config_includes_os_runtime_without_version_bump():
    assert DEFAULT_CONFIG["_config_version"] == 23
    assert DEFAULT_CONFIG["os_runtime"] == DEFAULT_OS_RUNTIME_CONFIG
    assert DEFAULT_CONFIG["os_runtime"]["enabled"] is False
    assert DEFAULT_CONFIG["os_runtime"]["mode"] == "passive"
    assert DEFAULT_CONFIG["os_runtime"]["allow_tool_execution"] is False
    assert DEFAULT_CONFIG["os_runtime"]["allow_auto_continuation"] is False
    assert DEFAULT_CONFIG["os_runtime"]["tick_interval_seconds"] == 0


def test_import_smoke_has_no_runtime_side_effects():
    import agent.os_runtime.config as os_config
    import agent.os_runtime.domain as os_domain
    import hermes_cli.config as hermes_config

    assert os_config.DEFAULT_OS_RUNTIME_CONFIG["enabled"] is False
    assert os_domain.ArbitrationDecision.REJECT.value == "reject"
    assert hermes_config.DEFAULT_CONFIG["os_runtime"]["enabled"] is False
