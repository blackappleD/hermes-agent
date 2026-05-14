from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.os_runtime.adapters.session_store import OSRuntimeEventRepository
from agent.os_runtime.config import OSRuntimeConfig
from agent.os_runtime.domain import (
    ActionPotential,
    ArbitrationDecision,
    ArbitrationResult,
    EventSource,
    OpenActionFamily,
    OpenIntent,
    OpenSpace,
    RiskLevel,
    SelfPrompt,
    TargetDirection,
)
from agent.os_runtime.driver import OS_RUNTIME_CONTINUATION_MARKER, OSRuntimeDriver, OSRuntimeState


@pytest.fixture()
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    from agent.os_runtime import driver

    driver._DB_CACHE.clear()
    yield home
    driver._DB_CACHE.clear()


def test_state_json_round_trip_defaults_and_profile_isolation(hermes_home, tmp_path, monkeypatch):
    state = OSRuntimeState(status="assisted", goal="draft note")
    restored = OSRuntimeState.from_json(state.to_json())
    assert restored.status == "assisted"
    assert restored.goal == "draft note"
    assert restored.max_turns == 8

    cfg = OSRuntimeConfig(enabled=True, mode="passive")
    driver_a = OSRuntimeDriver("session-1", config=cfg)
    driver_a.set_passive()

    other_home = tmp_path / ".hermes-other"
    other_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(other_home))
    from agent.os_runtime import driver as driver_mod

    driver_mod._DB_CACHE.clear()
    assert OSRuntimeDriver("session-1", config=cfg).state is None


def test_disabled_and_passive_do_not_continue(hermes_home):
    disabled = OSRuntimeDriver("s-disabled", config=OSRuntimeConfig(enabled=False, mode="assisted"))
    disabled.set_goal("write docs")
    decision = disabled.evaluate_after_turn("done", recent_event=_event("s-disabled"))
    assert decision.should_continue is False
    assert decision.reason == "os_runtime.enabled=false"

    passive = OSRuntimeDriver("s-passive", config=OSRuntimeConfig(enabled=True, mode="passive"))
    passive.set_passive()
    decision = passive.evaluate_after_turn("done", recent_event=_event("s-passive"))
    assert decision.should_continue is False
    assert passive.state.last_intent_id
    assert passive.state.last_arbitration


def test_recent_event_missing_and_engine_error_fail_closed(hermes_home):
    driver = OSRuntimeDriver("s-missing", config=OSRuntimeConfig(enabled=True, mode="assisted"))
    driver.set_goal("draft note")
    decision = driver.evaluate_after_turn("assistant response")
    assert decision.should_continue is False
    assert "recent event missing" in decision.reason

    class BrokenSignals:
        def interpret(self, **kwargs):
            raise RuntimeError("boom")

    broken = OSRuntimeDriver(
        "s-broken",
        config=OSRuntimeConfig(enabled=True, mode="assisted"),
        signal_interpreter=BrokenSignals(),
    )
    broken.set_goal("draft note")
    decision = broken.evaluate_after_turn("assistant response", recent_event=_event("s-broken"))
    assert decision.should_continue is False
    assert "driver error" in decision.reason


def test_assisted_report_only_continuation_and_budget_stop(hermes_home):
    cfg = OSRuntimeConfig(enabled=True, mode="assisted", max_continuation_turns=1)
    runtime = OSRuntimeDriver(
        "s-assisted",
        config=cfg,
        intent_generator=_IntentGenerator(),
        arbiter=_Arbiter(ArbitrationDecision.REPORT_ONLY),
    )
    runtime.set_goal("draft a changelog")

    decision = runtime.evaluate_after_turn("assistant response", recent_event=_event("s-assisted"))
    assert decision.should_continue is True
    assert decision.continuation_prompt.startswith(OS_RUNTIME_CONTINUATION_MARKER)
    assert "Do not call tools" in decision.continuation_prompt
    assert runtime.state.turns_used == 1

    next_decision = runtime.evaluate_after_turn("assistant response", recent_event=_event("s-assisted", "evt-2"))
    assert next_decision.should_continue is False
    assert "turn budget exhausted" in next_decision.reason


def test_assisted_reject_stops(hermes_home):
    runtime = OSRuntimeDriver(
        "s-reject",
        config=OSRuntimeConfig(enabled=True, mode="assisted"),
        intent_generator=_IntentGenerator(),
        arbiter=_Arbiter(ArbitrationDecision.REQUIRE_APPROVAL),
    )
    runtime.set_goal("publish event")

    decision = runtime.evaluate_after_turn("assistant response", recent_event=_event("s-reject"))
    assert decision.should_continue is False
    assert "arbitration denied" in decision.reason


def test_event_repository_profile_scope_for_driver(hermes_home, tmp_path):
    repo = OSRuntimeEventRepository(root=tmp_path / "profile-a")
    runtime = OSRuntimeDriver(
        "s-repo",
        config=OSRuntimeConfig(enabled=True, mode="assisted"),
        event_repository=repo,
        intent_generator=_IntentGenerator(),
        arbiter=_Arbiter(ArbitrationDecision.REPORT_ONLY),
    )
    try:
        runtime.set_goal("draft note")
        runtime.evaluate_after_turn("assistant response", recent_event=_event("s-repo"))
        events = repo.list_by_session("s-repo")
        assert any(event.event_type == "os_runtime_continuation" for event in events)
    finally:
        repo.close()


def test_driver_emits_os_runtime_pipeline_debug_steps(hermes_home, monkeypatch):
    monkeypatch.setenv("HERMES_OS_RUNTIME_LOG", "1")
    runtime = OSRuntimeDriver(
        "s-debug",
        config=OSRuntimeConfig(enabled=True, mode="passive"),
    )
    runtime.set_passive()

    runtime.evaluate_after_turn("assistant response", recent_event=_event("s-debug"))

    files = sorted((hermes_home / "logs").glob("os_runtime_*.log"))
    assert files
    records = [
        json.loads(line)
        for line in files[-1].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    steps = [
        record["step"]
        for record in records
        if record["session_id"] == "s-debug" and record["surface"] == "driver"
    ]
    assert steps == [
        "goal_event",
        "signal_set",
        "life_state",
        "tension_operation",
        "tension_set",
        "action_potential",
        "self_prompt",
        "open_intent",
        "arbiter",
    ]


class _IntentGenerator:
    def generate(self, **kwargs):
        return OpenIntent(
            intent_id="intent-low",
            action_family=OpenActionFamily.COMMUNICATE,
            action_type="draft_message",
            why_now="low-risk draft can continue",
            open_space=OpenSpace(available_action_families=[OpenActionFamily.COMMUNICATE]),
            target_direction=TargetDirection(
                description="continue draft",
                success_condition="draft next paragraph",
                stop_condition="stop before tools",
            ),
            tools_needed=[],
            success_condition="draft next paragraph",
            stop_condition="stop before tools",
            risk_level=RiskLevel.LOW,
        )


class _Arbiter:
    def __init__(self, decision):
        self.decision = decision

    def arbitrate(self, *, intent, **kwargs):
        return ArbitrationResult(
            intent_id=intent.intent_id,
            decision=self.decision,
            risk_level=RiskLevel.LOW,
            rationale="test arbitration",
        )


def _event(session_id: str, event_id: str = "evt-1"):
    return {
        "event_id": event_id,
        "event_type": "human_request",
        "source": EventSource.HERMES_CONVERSATION.value,
        "session_id": session_id,
        "summary": "please continue this goal",
        "metadata": {"goal": "draft"},
    }
